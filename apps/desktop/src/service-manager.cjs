const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const {
  resolveNpmCommand,
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

function fixPyvenvHomeIfNeeded(backendRoot) {
  const pyvenvPath = path.join(backendRoot, ".venv", "pyvenv.cfg");
  if (!fs.existsSync(pyvenvPath)) {
    return;
  }
  const embedPythonDir = path.join(backendRoot, ".venv", "python");
  if (!fs.existsSync(embedPythonDir)) {
    return;
  }

  let content;
  try {
    content = fs.readFileSync(pyvenvPath, "utf-8");
  } catch {
    return;
  }

  const homeMatch = content.match(/^home\s*=\s*(.+)$/m);
  const currentHome = homeMatch ? homeMatch[1].trim() : null;
  const expectedHome = embedPythonDir;

  // 如果 home 已经正确，无需修改
  if (currentHome && path.resolve(currentHome) === path.resolve(expectedHome)) {
    return;
  }

  // home 不正确或缺失，强制修复为嵌入目录
  // 不依赖 fs.existsSync 判断，避免目标机器上恰好存在构建机同名路径时漏修
  const newContent = content.replace(/^home\s*=\s*.+$/m, `home = ${expectedHome}`);
  try {
    fs.writeFileSync(pyvenvPath, newContent, "utf-8");
    console.log(`[aiasys-desktop] 已修复 pyvenv.cfg home 路径: ${expectedHome}`);
  } catch (error) {
    console.warn("[aiasys-desktop] 修复 pyvenv.cfg 失败:", error);
  }

  // 修复 .venv/bin/python 符号链接，使其指向嵌入的 Python
  const venvBinDir = path.join(backendRoot, ".venv", "bin");
  const embedBinDir = path.join(embedPythonDir, "bin");
  if (fs.existsSync(venvBinDir) && fs.existsSync(embedBinDir)) {
    for (const name of ["python", "python3"]) {
      const linkPath = path.join(venvBinDir, name);
      let isSymlink = false;
      try {
        isSymlink = fs.lstatSync(linkPath).isSymbolicLink();
      } catch {
        continue;
      }
      if (!isSymlink) continue;

      const target = fs.readlinkSync(linkPath);
      const needsFix = path.isAbsolute(target) || !fs.existsSync(linkPath);
      if (!needsFix) continue;

      const embedPython = path.join(embedBinDir, name);
      if (!fs.existsSync(embedPython)) continue;

      fs.unlinkSync(linkPath);
      const relativeTarget = path.relative(venvBinDir, embedPython);
      fs.symlinkSync(relativeTarget, linkPath);
      console.log(`[aiasys-desktop] 已修复 venv 符号链接: ${name} -> ${relativeTarget}`);
    }
  }
}

function validatePythonExecutable(pythonPath) {
  try {
    const result = spawnSync(pythonPath, ["-V"], {
      encoding: "utf-8",
      timeout: 5000,
    });
    if (result.status === 0) {
      return { ok: true, version: result.stdout.trim() };
    }
    return { ok: false, error: result.stderr || result.stdout || "未知错误" };
  } catch (error) {
    return { ok: false, error: error.message };
  }
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
 * 动态查找 venv 的 site-packages 目录。
 * Windows: .venv/Lib/site-packages
 * macOS/Linux: .venv/lib/pythonX.Y/site-packages
 */
function getVenvSitePackages(backendRoot) {
  // Windows
  const winSitePackages = path.join(backendRoot, ".venv", "Lib", "site-packages");
  if (fs.existsSync(winSitePackages)) {
    return winSitePackages;
  }

  // macOS/Linux: 遍历 .venv/lib/ 找 pythonX.Y/site-packages
  const libDir = path.join(backendRoot, ".venv", "lib");
  if (fs.existsSync(libDir)) {
    try {
      for (const entry of fs.readdirSync(libDir)) {
        if (/^python\d+\.\d+$/.test(entry)) {
          const candidate = path.join(libDir, entry, "site-packages");
          if (fs.existsSync(candidate)) {
            return candidate;
          }
        }
      }
    } catch {
      // ignore
    }
  }

  return null;
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
    { encoding: "utf-8" },
  );

  if (lsofResult.status !== 0) {
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

function logToBoth(stream, prefix, data) {
  const lines = String(data).split("\n");
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
    if (code === 0 || signal === "SIGTERM") {
      if (logStream && !logStream.destroyed) {
        logStream.end(`[${name}] 正常退出: code=${code} signal=${signal}\n`);
      }
      return;
    }
    console.error(
      `[aiasys-desktop] ${name} 提前退出: code=${code ?? "null"} signal=${signal ?? "null"}`,
    );
    if (logStream && !logStream.destroyed) {
      logStream.write(
        `[${name}] 提前退出: code=${code ?? "null"} signal=${signal ?? "null"}\n`,
      );
    }
  });

  // 附加日志流引用，供外部关闭
  child.__logStream = logStream;

  return child;
}

async function terminateChild(child) {
  if (!child || child.killed || child.exitCode !== null) {
    return;
  }

  if (child.__logStream && !child.__logStream.destroyed) {
    child.__logStream.end(`[terminate] 进程被终止\n`);
  }

  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        stdio: "ignore",
        windowsHide: true,
      });
      killer.once("exit", () => resolve());
      killer.once("error", () => resolve());
    });
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

    const sitePackages = getVenvSitePackages(this.backendRoot);
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
  buildBackendEnv(extraEnv = {}) {
    return this._buildPythonEnv({
      AIASYS_DESKTOP_MODE: "1",
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
    while (this.managedChildren.length > 0) {
      const child = this.managedChildren.pop();
      await terminateChild(child);
    }
  }

  async ensureBackend() {
    this.preparePackagedRuntimeState();

    // 打包环境：修复 pyvenv.cfg 的 home 路径为嵌入目录
    // 避免 venv 的 python 符号链接指向 runner 上的原始路径
    if (this.isPackaged) {
      fixPyvenvHomeIfNeeded(this.backendRoot);
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

    const pythonExecutable = resolvePythonExecutable(this.backendRoot);
    console.log("[aiasys-desktop] 启动 backend ...");
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
      },
    );
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
      const pythonExecutable = resolvePythonExecutable(this.backendRoot);
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
