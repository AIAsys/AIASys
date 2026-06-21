const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const {
  resolveNpmCommand,
  validatePythonExecutable,
  getVenvSitePackages,
  fixPyvenvHomeIfNeeded,
  canReuseService: canReuseServiceUtil,
  resolveDesiredPort: resolveDesiredPortUtil,
  probeFreePort,
  findAvailablePort,
  probeUrl,
} = require("./utils.cjs");

const HOST = process.env.AIASYS_DESKTOP_HOST || "127.0.0.1";
const DEFAULT_FRONTEND_PORT = 13010;
const DEFAULT_BACKEND_PORT = 13011;
const FRONTEND_PORT = Number(
  process.env.AIASYS_DESKTOP_FRONTEND_PORT || String(DEFAULT_FRONTEND_PORT),
);
const BACKEND_PORT = Number(
  process.env.AIASYS_DESKTOP_BACKEND_PORT || String(DEFAULT_BACKEND_PORT),
);
const FRONTEND_PORT_LOCKED = Object.prototype.hasOwnProperty.call(
  process.env,
  "AIASYS_DESKTOP_FRONTEND_PORT",
);
const BACKEND_PORT_LOCKED = Object.prototype.hasOwnProperty.call(
  process.env,
  "AIASYS_DESKTOP_BACKEND_PORT",
);

function resolveRepoRoot() {
  return path.resolve(__dirname, "..", "..", "..");
}

/**
 * macOS 上尝试移除复制后的 .venv 的 com.apple.quarantine 扩展属性。
 * 首次启动时从 app bundle 复制到用户目录的二进制仍可能携带隔离属性，
 * 导致 Gatekeeper / AMFI 在第一次执行 Python 时拦截或延迟验证，表现为白屏或启动失败。
 * 此处作为最佳 effort 兜底，失败不阻塞启动。
 */
function removeMacVenvQuarantine(writableVenv) {
  if (process.platform !== "darwin") {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    console.log(
      `[aiasys-desktop] 正在尝试移除 .venv 的 quarantine 属性: ${writableVenv}`,
    );
    const child = spawn("xattr", ["-r", "-d", "com.apple.quarantine", writableVenv], {
      stdio: "ignore",
      detached: true,
    });
    child.once("error", (error) => {
      console.warn(`[aiasys-desktop] 移除 quarantine 属性失败: ${error.message}`);
      resolve();
    });
    child.once("exit", (code) => {
      if (code === 0) {
        console.log(`[aiasys-desktop] 已移除 .venv 的 quarantine 属性`);
      } else {
        console.warn(`[aiasys-desktop] 移除 quarantine 属性退出码: ${code}`);
      }
      resolve();
    });
    // 最多等待 10 秒，避免首次启动长时间卡住
    setTimeout(() => {
      try {
        child.kill();
      } catch {
        // ignore
      }
      resolve();
    }, 10_000);
  });
}

/**
 * 将 AppImage 只读目录中的 .venv 复制到可写运行时目录，
 * 然后修复 pyvenv.cfg 和符号链接。
 */
async function preparePackagedVenv(backendRoot, runtimeStateRoot) {
  const writableVenv = path.join(runtimeStateRoot, ".venv");
  if (fs.existsSync(writableVenv)) {
    return; // 已复制过，直接复用
  }

  const readOnlyVenv = path.join(backendRoot, ".venv");
  if (!fs.existsSync(readOnlyVenv)) {
    return;
  }

  console.log(`[aiasys-desktop] 复制 .venv 到可写目录: ${writableVenv}`);
  const copyStart = Date.now();
  fs.cpSync(readOnlyVenv, writableVenv, { recursive: true, dereference: true });
  console.log(
    `[aiasys-desktop] .venv 复制完成，耗时 ${Date.now() - copyStart}ms`,
  );
  fixPyvenvHomeIfNeeded(writableVenv);
  console.log(`[aiasys-desktop] .venv 就绪（可写副本）`);

  // macOS: 复制后的 Mach-O 二进制可能仍携带 quarantine 属性，尝试清理
  await removeMacVenvQuarantine(writableVenv);
}

function resolvePythonExecutable(backendRoot) {
  const platformCandidates =
    process.platform === "win32"
      ? [
          // 优先使用嵌入的完整 Python 运行时
          path.join(backendRoot, ".venv", "python", "python.exe"),
          path.join(backendRoot, ".venv", "Scripts", "python.exe"),
          path.join(backendRoot, ".venv", "Scripts", "python"),
        ]
      : [
          // macOS/Linux: 优先使用 venv 入口点（.venv/bin/python3）
          // venv 入口点能找到 pyvenv.cfg，从而正确加载 site-packages。
          // 嵌入 Python（.venv/python/bin/python3）直接启动会找不到 site-packages。
          path.join(backendRoot, ".venv", "bin", "python3"),
          path.join(backendRoot, ".venv", "bin", "python"),
          // fallback: 嵌入的完整 Python 运行时
          path.join(backendRoot, ".venv", "python", "bin", "python3"),
          path.join(backendRoot, ".venv", "python", "bin", "python"),
        ];

  for (const candidate of platformCandidates) {
    if (fs.existsSync(candidate)) {
      const validation = validatePythonExecutable(candidate);
      if (validation.ok) {
        console.log(`[aiasys-desktop] Python 解释器验证通过: ${candidate} (${validation.version})`);
        return candidate;
      }
      console.warn(
        `[aiasys-desktop] Python 解释器存在但无法执行: ${candidate}\n` +
          `  错误: ${validation.error}\n` +
          `  提示: macOS/Linux 上请使用 "uv python install 3.12" 安装 python-build-standalone，` +
          `避免使用依赖系统框架的 Python 发行版。`,
      );
    }
  }

  const wrongPlatformCandidates =
    process.platform === "win32"
      ? [
          path.join(backendRoot, ".venv", "bin", "python"),
          path.join(backendRoot, ".venv", "bin", "python3"),
        ]
      : [
          path.join(backendRoot, ".venv", "Scripts", "python.exe"),
          path.join(backendRoot, ".venv", "Scripts", "python"),
        ];
  const wrongPlatformPython = wrongPlatformCandidates.find((candidate) =>
    fs.existsSync(candidate),
  );
  if (wrongPlatformPython) {
    throw new Error(
      `backend Python 虚拟环境平台不匹配。当前平台=${process.platform}，` +
        `找到的是其他平台解释器: ${wrongPlatformPython}。` +
        `请在目标系统重新准备 backend .venv 和依赖。`,
    );
  }

  // 诊断信息：打印每个候选路径的详细状态
  const diagnostics = platformCandidates.map((candidate) => {
    let status = "不存在";
    try {
      const lstat = fs.lstatSync(candidate);
      if (lstat.isSymbolicLink()) {
        const target = fs.readlinkSync(candidate);
        status = `符号链接 -> ${target}${fs.existsSync(candidate) ? "" : " (broken)"}`;
      } else if (lstat.isFile()) {
        status = `文件${lstat.mode & 0o111 ? " (可执行)" : " (不可执行)"}`;
      } else {
        status = `其他类型 (${lstat.mode.toString(8)})`;
      }
    } catch {
      status = "不存在或无法访问";
    }
    return `  ${candidate}: ${status}`;
  });

  throw new Error(
    `找不到 backend Python 解释器，请确认已准备好虚拟环境。\n` +
      `候选路径:\n${diagnostics.join("\n")}`,
  );
}


/**
 * 读取监听指定端口的进程信息。
 * Linux/macOS 用 lsof + ps；Windows 用 netstat -ano + tasklist。
 */
function readListeningProcess(port) {
  if (process.platform === "win32") {
    return readListeningProcessWindows(port);
  }
  return readListeningProcessUnix(port);
}

function readListeningProcessUnix(port) {
  const lsofResult = spawnSync(
    "lsof",
    ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-Fp"],
    { encoding: "utf-8", timeout: 5000 },
  );

  if (lsofResult.status !== 0 || lsofResult.error) {
    return null;
  }

  const pidLine = lsofResult.stdout
    .split("\n")
    .find((line) => line.startsWith("p"));
  if (!pidLine) {
    return null;
  }

  const pid = pidLine.slice(1).trim();
  if (!pid) {
    return null;
  }

  const psResult = spawnSync("ps", ["-o", "command=", "-p", pid], {
    encoding: "utf-8",
  });
  if (psResult.status !== 0) {
    return { pid, command: "" };
  }

  return {
    pid,
    command: psResult.stdout.trim(),
  };
}

function readListeningProcessWindows(port) {
  // 步骤 1: netstat -ano 找 PID
  const netstatResult = spawnSync("netstat", ["-ano"], {
    encoding: "utf-8",
    windowsHide: true,
  });

  if (netstatResult.status !== 0 || !netstatResult.stdout) {
    return null;
  }

  // 解析 netstat 输出，匹配 "127.0.0.1:PORT" 或 "0.0.0.0:PORT" 的 LISTENING 行
  const lines = netstatResult.stdout.split("\r\n").join("\n").split("\n");
  let pid = null;

  for (const rawLine of lines) {
    const line = rawLine.trim();
    // 格式类似: TCP    127.0.0.1:13011    0.0.0.0:0    LISTENING    12345
    if (!line.startsWith("TCP")) {
      continue;
    }
    const parts = line.split(/\s+/);
    if (parts.length < 5) {
      continue;
    }
    const localAddress = parts[1];
    const state = parts[3];
    const candidatePid = parts[parts.length - 1];

    if (
      state === "LISTENING" &&
      (localAddress === `${HOST}:${port}` || localAddress.endsWith(`:${port}`))
    ) {
      pid = candidatePid;
      break;
    }
  }

  if (!pid || pid === "0") {
    return null;
  }

  // 步骤 2: tasklist /FI "PID eq xxx" /FO CSV 获取进程名
  const tasklistResult = spawnSync(
    "tasklist",
    ["/FI", `PID eq ${pid}`, "/FO", "CSV", "/NH"],
    { encoding: "utf-8", windowsHide: true },
  );

  if (tasklistResult.status !== 0 || !tasklistResult.stdout) {
    return { pid, command: "" };
  }

  // CSV 格式: "python.exe","12345","Console","1","12,345 K"
  const csvLine = tasklistResult.stdout.trim().split("\r\n").join("\n").split("\n")[0];
  if (!csvLine) {
    return { pid, command: "" };
  }

  // 简单解析 CSV：取第一个引号内的值为进程名
  const match = csvLine.match(/^"([^"]+)"/);
  const processName = match ? match[1] : csvLine.split(",")[0];

  return {
    pid,
    command: processName || "",
  };
}



/**
 * 等待 URL 就绪，同时监控子进程是否已崩溃退出。
 * 如果子进程在轮询期间崩溃，提前抛出错误，避免 90 秒干等。
 */
async function waitForUrl(url, label, timeoutMs = 90_000, childProcesses = []) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    // 检查是否有子进程已崩溃
    for (const child of childProcesses) {
      if (child && child.exitCode !== null) {
        throw new Error(
          `${label} 子进程已崩溃退出（exitCode=${child.exitCode}），` +
            `无法继续等待服务就绪: ${url}`,
        );
      }
    }

    if (await probeUrl(url)) {
      console.log(
        `[aiasys-desktop] ${label} 已就绪，耗时 ${Date.now() - start}ms: ${url}`,
      );
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(`${label} 在 ${timeoutMs}ms 内未就绪: ${url}`);
}

/**
 * 创建日志写入流，同时输出到控制台。
 */
function createLogStream(logFilePath) {
  fs.mkdirSync(path.dirname(logFilePath), { recursive: true });
  const stream = fs.createWriteStream(logFilePath, { flags: "a" });
  const now = new Date().toISOString();
  stream.write(`\n[${now}] === 日志开始 ===\n`);
  return stream;
}

function decodeProcessOutput(data) {
  if (Buffer.isBuffer(data)) {
    // Try UTF-8 first, fall back to latin1 (never fails, preserves raw bytes)
    try {
      const str = data.toString("utf-8");
      // Quick check: if it contains replacement characters, it might be a different encoding
      if (!str.includes('\uFFFD')) return str;
      // Fall through to latin1 which preserves all bytes
      return data.toString("latin1");
    } catch {
      return data.toString("latin1");
    }
  }
  return String(data);
}

function logToBoth(stream, prefix, data) {
  const lines = decodeProcessOutput(data).split("\n");
  for (const line of lines) {
    if (line.trim() === "") {
      continue;
    }
    const formatted = `[${prefix}] ${line}`;
    console.log(formatted);
    if (stream && !stream.destroyed) {
      stream.write(`${formatted}\n`);
    }
  }
}

function spawnManagedProcess(name, command, args, options) {
  const isWindows = process.platform === "win32";
  const autoRestart = options?.autoRestart !== false;
  const maxRestarts = 3;
  const canRestart =
    typeof options?.canRestart === "function" ? options.canRestart : () => true;
  let restartCount = 0;

  const spawnOnce = () => {
    const child = spawn(command, args, {
      ...options,
      detached: !isWindows,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: isWindows,
    });

    // 日志流
    let logStream = null;
    if (options?.__logFilePath) {
      try {
        logStream = createLogStream(options.__logFilePath);
      } catch (error) {
        console.error(`[aiasys-desktop] 无法创建日志文件 ${options.__logFilePath}:`, error);
      }
    }

    if (child.stdout) {
      child.stdout.on("data", (data) => {
        logToBoth(logStream, name, data);
      });
    }

    if (child.stderr) {
      child.stderr.on("data", (data) => {
        logToBoth(logStream, `${name}:stderr`, data);
      });
    }

    child.once("error", (error) => {
      console.error(`[aiasys-desktop] ${name} 启动失败:`, error);
      if (logStream && !logStream.destroyed) {
        logStream.write(`[${name}] 启动失败: ${error.message}\n`);
      }
    });

    child.once("exit", (code, signal) => {
      const isExpectedExit =
        code === 0 || signal === "SIGTERM" || child.__terminatedByUs;

      if (logStream && !logStream.destroyed) {
        logStream.end(
          `[${name}] ${isExpectedExit ? "正常退出" : "提前退出"}: code=${code ?? "null"} signal=${signal ?? "null"}\n`,
        );
      }

      if (isExpectedExit) {
        return;
      }

      console.error(
        `[aiasys-desktop] ${name} 提前退出: code=${code ?? "null"} signal=${signal ?? "null"}`,
      );

      // 通知崩溃
      if (typeof options?.onCrash === "function") {
        options.onCrash({ code, signal, restartCount, maxRestarts });
      }

      // 自动重启
      if (autoRestart && restartCount < maxRestarts && canRestart()) {
        restartCount++;
        console.log(
          `[aiasys-desktop] ${name} 将在 2 秒后自动重启 (${restartCount}/${maxRestarts})...`,
        );
        if (logStream && !logStream.destroyed) {
          logStream.write(
            `[${name}] 将在 2 秒后自动重启 (${restartCount}/${maxRestarts})...\n`,
          );
        }

        setTimeout(() => {
          if (!canRestart()) {
            console.log(`[aiasys-desktop] ${name} 重启已取消（正在关闭）`);
            return;
          }
          const newChild = spawnOnce();
          if (typeof options?.onRestart === "function") {
            options.onRestart(newChild);
          }
        }, 2000);
      } else if (autoRestart) {
        console.error(
          `[aiasys-desktop] ${name} 已达最大重启次数 (${maxRestarts})，不再重启`,
        );
        if (typeof options?.onCrash === "function") {
          options.onCrash({ code, signal, restartCount, maxRestarts, exhausted: true });
        }
      }
    });

    // 附加日志流引用，供外部关闭
    child.__logStream = logStream;

    return child;
  };

  return spawnOnce();
}

async function terminateChild(child) {
  if (!child || child.killed || child.exitCode !== null) {
    return;
  }

  // 标记为主动终止，防止 exit handler 触发自动重启
  child.__terminatedByUs = true;

  if (child.__logStream && !child.__logStream.destroyed) {
    child.__logStream.end(`[terminate] 进程被终止\n`);
  }

  if (process.platform === "win32") {
    // 先尝试优雅终止，等待后再强制终止
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/t"], {
        stdio: "ignore",
        windowsHide: true,
      });
      killer.once("exit", () => resolve());
      killer.once("error", () => resolve());
      setTimeout(() => resolve(), 2000);
    });

    if (!child.killed && child.exitCode === null) {
      await new Promise((resolve) => {
        const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
          stdio: "ignore",
          windowsHide: true,
        });
        killer.once("exit", () => resolve());
        killer.once("error", () => resolve());
      });
    }
    return;
  }

  try {
    process.kill(-child.pid, "SIGTERM");
  } catch {
    return;
  }

  await new Promise((resolve) => setTimeout(resolve, 500));
}

class DesktopServiceManager {
  constructor({
    mode,
    isPackaged = false,
    resourcesPath = null,
    runtimeStateRoot = null,
  }) {
    this.mode = mode;
    this.isPackaged = isPackaged;
    this.resourcesPath = resourcesPath;
    this.runtimeStateRoot = runtimeStateRoot;
    this.host = HOST;
    if (this.isPackaged) {
      if (!this.resourcesPath) {
        throw new Error("packaged desktop 缺少 resourcesPath，无法解析运行时资源目录");
      }
      if (!this.runtimeStateRoot) {
        throw new Error("packaged desktop 缺少 runtimeStateRoot，无法外置运行时数据目录");
      }
      this.repoRoot = null;
      this.webRoot = path.join(this.resourcesPath, "web");
      this.backendRoot = path.join(this.resourcesPath, "backend");
      this.backendDataRoot = path.join(this.runtimeStateRoot, "data");
      this.backendLogsRoot = path.join(this.runtimeStateRoot, "logs");
      this.backendWorkspacesRoot = path.join(this.backendDataRoot, "workspaces");
    } else {
      this.repoRoot = resolveRepoRoot();
      this.webRoot = path.join(this.repoRoot, "apps", "web");
      this.backendRoot = path.join(this.repoRoot, "apps", "backend");
      this.backendDataRoot = path.join(this.backendRoot, "data");
      this.backendLogsRoot = path.join(this.backendRoot, "logs");
      this.backendWorkspacesRoot = path.join(this.backendDataRoot, "workspaces");
    }
    this.frontendPort = FRONTEND_PORT;
    this.backendPort = BACKEND_PORT;
    this.frontendPortLocked = FRONTEND_PORT_LOCKED;
    this.backendPortLocked = BACKEND_PORT_LOCKED;
    this.managedChildren = [];
    this.isShuttingDown = false;
    // 外部回调，由 main.cjs 设置
    this.onBackendCrash = null;
    this.onBackendReady = null;
  }

  preparePackagedRuntimeState() {
    if (!this.isPackaged) {
      return;
    }

    fs.mkdirSync(this.runtimeStateRoot, { recursive: true });

    const packagedDataRoot = path.join(this.backendRoot, "data");
    if (fs.existsSync(packagedDataRoot) && !fs.existsSync(this.backendDataRoot)) {
      fs.cpSync(packagedDataRoot, this.backendDataRoot, {
        recursive: true,
        preserveTimestamps: true,
      });
    }

    fs.mkdirSync(this.backendDataRoot, { recursive: true });
    fs.mkdirSync(this.backendLogsRoot, { recursive: true });
    fs.mkdirSync(this.backendWorkspacesRoot, { recursive: true });

    console.log(
      `[aiasys-desktop] packaged runtime root: ${this.runtimeStateRoot}`,
    );
  }

  get rendererBaseUrl() {
    return `http://${this.host}:${this.frontendPort}`;
  }

  get backendBaseUrl() {
    return `http://${this.host}:${this.backendPort}`;
  }

  /**
   * 获取日志文件路径
   */
  getLogFilePath(name) {
    const logsDir = this.isPackaged
      ? this.backendLogsRoot
      : path.join(this.backendRoot, "logs");
    return path.join(logsDir, `${name}-spawn.log`);
  }

  /**
   * 返回可用的 .venv 根目录。
   * AppImage 只读环境下指向 runtimeStateRoot 下的可写副本，
   * 其他环境直接使用 backendRoot。
   */
  _getVenvRoot() {
    // 构建时已按平台修复 pyvenv.cfg / dylib / shebang
    // 运行时：打包模式下 backendRoot 位于只读资源目录（AppImage squashfs、
    // Windows Program Files、macOS app bundle），需把 .venv 复制到可写运行时目录。
    if (this.isPackaged) {
      return this.runtimeStateRoot;
    }
    return this.backendRoot;
  }

  /**
   * 构建 Python 子进程的环境变量。
   * 自动注入 PYTHONPATH 指向 venv 的 site-packages，
   * 作为 venv 机制失效时的兜底保障（尤其 macOS 嵌入 Python 场景）。
   */
  _buildPythonEnv(extraEnv = {}) {
    const env = {
      ...process.env,
      PYTHONUNBUFFERED: "1",
      PYTHONIOENCODING: "utf-8",
      PYTHONUTF8: "1",
    };

    // 清除可能干扰嵌入 Python 的虚拟环境变量
    delete env.VIRTUAL_ENV;
    delete env.PYTHONHOME;

    const sitePackages = getVenvSitePackages(this._getVenvRoot());
    if (sitePackages) {
      const sep = process.platform === "win32" ? ";" : ":";
      const existing = process.env.PYTHONPATH || "";
      env.PYTHONPATH = existing ? `${sitePackages}${sep}${existing}` : sitePackages;
      console.log(`[aiasys-desktop] PYTHONPATH: ${sitePackages}`);
    }

    return { ...env, ...extraEnv };
  }

  /**
   * 构建 backend 子进程环境变量，附加桌面模式标识。
   */
  _bundledUvPath() {
    if (!this.backendRoot) {
      return null;
    }
    const platformDirMap = {
      "darwin-arm64": "darwin-arm64",
      "darwin-x64": "darwin-x64",
      "linux-arm64": "linux-arm64",
      "linux-x64": "linux-x64",
      "win32-x64": "windows-x64",
    };
    const key = `${process.platform}-${process.arch}`;
    const dir = platformDirMap[key];
    if (!dir) {
      console.warn(`[aiasys-desktop] 未支持的内置 uv 平台: ${key}`);
      return null;
    }
    const uvName = process.platform === "win32" ? "uv.exe" : "uv";
    return path.join(this.backendRoot, "vendor", "uv", dir, uvName);
  }

  _bundledFnmPath() {
    if (!this.backendRoot) {
      return null;
    }
    const platformDirMap = {
      "darwin-arm64": "darwin-arm64",
      "darwin-x64": "darwin-x64",
      "linux-arm64": "linux-arm64",
      "linux-x64": "linux-x64",
      "win32-x64": "win-x64",
    };
    const key = `${process.platform}-${process.arch}`;
    const dir = platformDirMap[key];
    if (!dir) {
      console.warn(`[aiasys-desktop] 未支持的内置 fnm 平台: ${key}`);
      return null;
    }
    const fnmName = process.platform === "win32" ? "fnm.exe" : "fnm";
    return path.join(this.backendRoot, "vendor", "node", dir, fnmName);
  }

  _fnmDataDir() {
    if (this.runtimeStateRoot) {
      return path.join(this.runtimeStateRoot, "fnm");
    }
    if (this.backendRoot) {
      return path.join(this.backendRoot, "fnm");
    }
    return null;
  }

  buildBackendEnv(extraEnv = {}) {
    const bundledUv = this._bundledUvPath();
    const bundledUvEnv = bundledUv ? { AIASYS_BUNDLED_UV_PATH: bundledUv } : {};
    const bundledFnm = this._bundledFnmPath();
    const bundledFnmEnv = bundledFnm ? { AIASYS_BUNDLED_FNM_PATH: bundledFnm } : {};
    const fnmDataDir = this._fnmDataDir();
    const fnmDataEnv = fnmDataDir ? { AIASYS_FNM_DIR: fnmDataDir } : {};
    return this._buildPythonEnv({
      AIASYS_DESKTOP_MODE: "1",
      ...bundledUvEnv,
      ...bundledFnmEnv,
      ...fnmDataEnv,
      ...extraEnv,
    });
  }

  async resolveDesiredPort({
    requestedPort,
    locked,
    label,
    expectedPaths,
    urlFactory,
    excludePorts = [],
  }) {
    return resolveDesiredPortUtil({
      requestedPort,
      locked,
      label,
      expectedPaths,
      urlFactory,
      excludePorts,
      host: this.host,
      findAvailablePort,
      canReuseService: canReuseServiceUtil,
      readListeningProcess,
      probeUrl,
    });
  }

  async start() {
    await this.ensureBackend();
    await this.ensureFrontend();
    return this.rendererBaseUrl;
  }

  async stop() {
    this.isShuttingDown = true;
    while (this.managedChildren.length > 0) {
      const child = this.managedChildren.pop();
      await terminateChild(child);
    }
  }

  async ensureBackend() {
    this.preparePackagedRuntimeState();

    // 构建时已按平台修复（dylib/shebang/pyvenv.cfg）。
    // 运行时：打包模式下 backendRoot 只读，需复制 .venv 到可写运行时目录并修复。
    if (this.isPackaged) {
      await preparePackagedVenv(this.backendRoot, this.runtimeStateRoot);
      fixPyvenvHomeIfNeeded(this.runtimeStateRoot);
    }

    const backendResolution = await this.resolveDesiredPort({
      requestedPort: this.backendPort,
      locked: this.backendPortLocked,
      label: "backend",
      expectedPaths: [this.backendRoot],
      urlFactory: (port) => `http://${this.host}:${port}/health`,
    });
    this.backendPort = backendResolution.port;
    const backendHealthUrl = `${this.backendBaseUrl}/health`;

    if (backendResolution.reuse) {
      console.log(`[aiasys-desktop] 复用现有 backend: ${backendHealthUrl}`);
      return;
    }

    const pythonExecutable = resolvePythonExecutable(this._getVenvRoot());
    console.log("[aiasys-desktop] 启动 backend ...");

    // 用于跟踪当前 backend 子进程引用，重启后更新
    let currentBackendChild = null;

    const child = spawnManagedProcess(
      "backend",
      pythonExecutable,
      ["-m", "uvicorn", "app.main:app", "--host", this.host, "--port", String(this.backendPort)],
      {
        cwd: this.backendRoot,
        env: this.buildBackendEnv({
          AIASYS_RUNTIME_ROOT: this.runtimeStateRoot || this.backendRoot,
        }),
        __logFilePath: this.getLogFilePath("backend"),
        autoRestart: true,
        canRestart: () => !this.isShuttingDown,
        onCrash: (info) => {
          console.error(`[aiasys-desktop] backend 崩溃: ${JSON.stringify(info)}`);
          if (typeof this.onBackendCrash === "function") {
            this.onBackendCrash(info);
          }
        },
        onRestart: (newChild) => {
          // 替换 managedChildren 中的旧引用
          const idx = this.managedChildren.indexOf(currentBackendChild);
          if (idx !== -1) {
            this.managedChildren[idx] = newChild;
          }
          currentBackendChild = newChild;

          // 等待 backend 健康检查通过后通知渲染进程
          waitForUrl(backendHealthUrl, "backend", 90_000, this.managedChildren)
            .then(() => {
              console.log("[aiasys-desktop] backend 重启后已就绪");
              if (typeof this.onBackendReady === "function") {
                this.onBackendReady();
              }
            })
            .catch((err) => {
              console.error("[aiasys-desktop] backend 重启后健康检查失败:", err);
              if (typeof this.onBackendCrash === "function") {
                this.onBackendCrash({ exitCode: null, signal: null, error: err.message });
              }
            });
        },
      },
    );
    currentBackendChild = child;
    this.managedChildren.push(child);
    await waitForUrl(backendHealthUrl, "backend", 90_000, this.managedChildren);
  }

  async ensureFrontend() {
    const frontendResolution = await this.resolveDesiredPort({
      requestedPort: this.frontendPort,
      locked: this.frontendPortLocked,
      label: "frontend",
      expectedPaths: [this.webRoot, path.join(this.webRoot, "scripts", "local_preview_server.py")],
      urlFactory: (port) => `http://${this.host}:${port}/`,
      excludePorts: [this.backendPort],
    });
    this.frontendPort = frontendResolution.port;
    const frontendUrl = `${this.rendererBaseUrl}/`;

    if (frontendResolution.reuse) {
      console.log(`[aiasys-desktop] 复用现有 frontend: ${frontendUrl}`);
      return;
    }

    if (this.mode === "preview") {
      this.ensureBuiltRenderer();
      console.log("[aiasys-desktop] 启动 preview frontend ...");
      const pythonExecutable = resolvePythonExecutable(this._getVenvRoot());
      const child = spawnManagedProcess(
        "frontend-preview",
        pythonExecutable,
        [path.join(this.webRoot, "scripts", "committed", "local_preview_server.py")],
        {
          cwd: this.webRoot,
          env: this._buildPythonEnv({
            AIASYS_PREVIEW_HOST: this.host,
            AIASYS_PREVIEW_PORT: String(this.frontendPort),
            AIASYS_PREVIEW_BACKEND_URL: this.backendBaseUrl,
          }),
          __logFilePath: this.getLogFilePath("frontend"),
        },
      );
      this.managedChildren.push(child);
      await waitForUrl(frontendUrl, "frontend-preview", 90_000, this.managedChildren);
      return;
    }

    console.log("[aiasys-desktop] 启动 Vite frontend ...");
    const npmCommand = resolveNpmCommand();
    const child = spawnManagedProcess(
      "frontend-dev",
      npmCommand,
      ["run", "dev", "--", "--host", this.host, "--port", String(this.frontendPort)],
      {
        cwd: this.webRoot,
        env: {
          ...process.env,
          BROWSER: "none",
          VITE_API_TARGET: this.backendBaseUrl,
        },
        __logFilePath: this.getLogFilePath("frontend"),
      },
    );
    this.managedChildren.push(child);
    await waitForUrl(frontendUrl, "frontend-dev", 90_000, this.managedChildren);
  }

  ensureBuiltRenderer() {
    const distIndexPath = path.join(this.webRoot, "dist", "index.html");
    if (fs.existsSync(distIndexPath)) {
      return;
    }

    throw new Error(
      `未找到 ${distIndexPath}。请先准备 web dist，再启动 desktop preview。`,
    );
  }
}

module.exports = {
  DesktopServiceManager,
};
