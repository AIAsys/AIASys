const fs = require("fs");
const net = require("net");
const path = require("path");
const crypto = require("crypto");
const { spawn, spawnSync } = require("child_process");
const tar = require("tar");
const iconv = require("iconv-lite");

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
  terminateProcessTreeSync,
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
      `[aiasys] 正在尝试移除 .venv 的 quarantine 属性: ${writableVenv}`,
    );
    const child = spawn("xattr", ["-r", "-d", "com.apple.quarantine", writableVenv], {
      stdio: "ignore",
      detached: true,
    });
    child.once("error", (error) => {
      console.warn(`[aiasys] 移除 quarantine 属性失败: ${error.message}`);
      resolve();
    });
    child.once("exit", (code) => {
      if (code === 0) {
        console.log(`[aiasys] 已移除 .venv 的 quarantine 属性`);
      } else {
        console.warn(`[aiasys] 移除 quarantine 属性退出码: ${code}`);
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
 * 预热复制的 .venv 中的 Python 解释器。
 *
 * 首次启动时，从 app bundle 复制到用户目录的 Python 二进制会触发系统安全软件
 *（macOS Gatekeeper、Windows Defender / AMSI）的首次扫描。直接在后台服务启动时
 * 才第一次执行 Python，可能导致子进程被挂起或扫描耗时过长，进而出现白屏。
 * 此处先执行一次轻量命令，强制完成扫描，同时验证解释器可用。
 */
function prewarmVenvPython(pythonExecutable) {
  return new Promise((resolve) => {
    if (!pythonExecutable || !fs.existsSync(pythonExecutable)) {
      return resolve();
    }
    console.log(`[aiasys] 正在预热 Python 解释器: ${pythonExecutable}`);
    const start = Date.now();
    const child = spawn(pythonExecutable, ["-c", "import sys; print(sys.version)"], {
      stdio: "ignore",
      windowsHide: process.platform === "win32",
      detached: true,
    });
    child.once("error", (error) => {
      console.warn(`[aiasys] Python 预热失败: ${error.message}`);
      resolve();
    });
    child.once("exit", (code) => {
      if (code === 0) {
        console.log(
          `[aiasys] Python 预热完成，耗时 ${Date.now() - start}ms`,
        );
      } else {
        console.warn(
          `[aiasys] Python 预热退出码: ${code}，耗时 ${Date.now() - start}ms`,
        );
      }
      resolve();
    });
    // 最多等待 30 秒；安全软件首次扫描可能较长
    setTimeout(() => {
      try {
        child.kill();
      } catch {
        // ignore
      }
      resolve();
    }, 30_000);
  });
}

/**
 * 读取构建时生成的 .venv manifest，获取条目总数用于解压进度。
 */
function readVenvManifest(backendRoot) {
  const manifestPath = path.join(backendRoot, ".venv.manifest.json");
  try {
    const content = fs.readFileSync(manifestPath, "utf-8");
    const parsed = JSON.parse(content);
    if (typeof parsed.entries === "number" && parsed.entries > 0) {
      return parsed;
    }
  } catch {
    // ignore
  }
  return null;
}

/**
 * 从压缩包解压 .venv 到可写运行时目录，并报告进度。
 */
async function extractVenvArchive(archivePath, runtimeStateRoot, totalEntries, onProgress) {
  const start = Date.now();
  let extracted = 0;
  let lastReportedPercent = -1;

  function reportProgress(force = false) {
    if (!onProgress) return;
    const percent = totalEntries > 0
      ? Math.min(100, Math.round((extracted / totalEntries) * 100))
      : 0;
    if (force || percent !== lastReportedPercent) {
      lastReportedPercent = percent;
      onProgress({ extracted, total: totalEntries, percent });
    }
  }

  console.log(`[aiasys] 解压 .venv: ${archivePath} -> ${runtimeStateRoot}`);
  await tar.extract({
    file: archivePath,
    cwd: runtimeStateRoot,
    preserveOwner: false,
    noMtime: true,
    onentry: () => {
      extracted++;
      reportProgress();
    },
  });

  // 确保最终进度为 100%，即使 manifest entries 与实际不一致
  reportProgress(true);

  console.log(
    `[aiasys] .venv 解压完成，${extracted} 个条目，耗时 ${Date.now() - start}ms`,
  );
}

/**
 * 降级路径：无压缩包时逐文件复制 .venv。
 * 使用异步复制避免阻塞主进程事件循环。
 */
async function copyVenvFallback(backendRoot, runtimeStateRoot) {
  const writableVenv = path.join(runtimeStateRoot, ".venv");
  const readOnlyVenv = path.join(backendRoot, ".venv");
  if (!fs.existsSync(readOnlyVenv)) {
    return;
  }

  console.log(`[aiasys] 复制 .venv 到可写目录: ${writableVenv}`);
  const copyStart = Date.now();
  await fs.promises.cp(readOnlyVenv, writableVenv, { recursive: true, dereference: true });
  console.log(
    `[aiasys] .venv 复制完成，耗时 ${Date.now() - copyStart}ms`,
  );
}

/**
 * 检查可写目录中的 .venv 是否完整可用。
 * 通过校验平台相关的 Python 解释器入口是否存在来判断。
 */
function isVenvReady(writableVenv) {
  if (!fs.existsSync(writableVenv)) {
    return false;
  }
  const candidates =
    process.platform === "win32"
      ? [
          path.join(writableVenv, "python", "python.exe"),
          path.join(writableVenv, "Scripts", "python.exe"),
        ]
      : [
          path.join(writableVenv, "bin", "python3"),
          path.join(writableVenv, "bin", "python"),
        ];
  return candidates.some((candidate) => fs.existsSync(candidate));
}

/**
 * 根据平台与架构解析 backendRoot 下 bundled uv 的绝对路径。
 * 与 DesktopServiceManager._bundledUvPath() 逻辑一致，但以独立函数形式
 * 供 preparePackagedVenv / bootstrapVenvFromScratch 等静态函数复用。
 */
function resolveBundledUvPath(backendRoot) {
  if (!backendRoot) {
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
    console.warn(`[aiasys] 未支持的内置 uv 平台: ${key}`);
    return null;
  }
  const uvName = process.platform === "win32" ? "uv.exe" : "uv";
  return path.join(backendRoot, "vendor", "uv", dir, uvName);
}

/**
 * Light/Portable 模式：从零创建 Python 虚拟环境。
 *
 * 使用 bundled uv 依次执行：
 * 1. uv python install 3.12  — 下载 python-build-standalone
 * 2. uv venv               — 在 runtimeStateRoot 下创建 .venv
 * 3. uv sync               — 安装 pyproject.toml 中声明的全部依赖
 *
 * 每一步通过 onProgress 回调报告进度，供 splash 界面展示。
 */
async function bootstrapVenvFromScratch(backendRoot, runtimeStateRoot, onProgress) {
  const bundledUv = resolveBundledUvPath(backendRoot);
  if (!bundledUv || !fs.existsSync(bundledUv)) {
    throw new Error(
      "Light/Portable 模式需要 bundled uv 来创建 Python 环境，" +
        "但未找到 uv 二进制。请确认 vendor/uv 目录已正确打包。",
    );
  }

  const writableVenv = path.join(runtimeStateRoot, ".venv");
  const isWindows = process.platform === "win32";
  const spawnOpts = {
    encoding: "utf-8",
    stdio: "pipe",
    windowsHide: isWindows,
  };

  // 允许 uv 使用项目级缓存加速后续 workspace 环境创建
  const uvEnv = { ...process.env };
  // 清除可能干扰 bootstrap 的虚拟环境变量
  delete uvEnv.VIRTUAL_ENV;
  delete uvEnv.PYTHONHOME;

  // Step 1: 下载 Python 运行时
  console.log("[aiasys] Light 模式: 正在下载 Python 3.12...");
  onProgress?.({ message: "正在下载 Python 运行时...", step: "python", percent: 5 });

  const pythonInstallResult = spawnSync(
    bundledUv,
    ["python", "install", "3.12"],
    { ...spawnOpts, timeout: 300_000, env: uvEnv },
  );
  if (pythonInstallResult.status !== 0) {
    const detail = pythonInstallResult.stderr || pythonInstallResult.error || `exit ${pythonInstallResult.status}`;
    throw new Error(`uv python install 3.12 失败: ${detail}`);
  }
  console.log("[aiasys] Python 3.12 下载完成");

  // Step 2: 创建 venv
  console.log(`[aiasys] Light 模式: 正在创建虚拟环境: ${writableVenv}`);
  onProgress?.({ message: "正在创建虚拟环境...", step: "venv", percent: 35 });

  const venvResult = spawnSync(
    bundledUv,
    ["venv", writableVenv, "--python", "3.12"],
    { ...spawnOpts, timeout: 120_000, env: uvEnv },
  );
  if (venvResult.status !== 0) {
    const detail = venvResult.stderr || venvResult.error || `exit ${venvResult.status}`;
    throw new Error(`uv venv 失败: ${detail}`);
  }
  console.log("[aiasys] 虚拟环境创建完成");

  // Step 3: 安装依赖
  console.log("[aiasys] Light 模式: 正在安装 Python 依赖...");
  onProgress?.({ message: "正在安装 Python 依赖...", step: "deps", percent: 65 });

  const syncEnv = { ...uvEnv, VIRTUAL_ENV: writableVenv };
  const syncResult = spawnSync(
    bundledUv,
    ["sync"],
    { ...spawnOpts, timeout: 600_000, cwd: backendRoot, env: syncEnv },
  );
  if (syncResult.status !== 0) {
    const detail = syncResult.stderr || syncResult.error || `exit ${syncResult.status}`;
    throw new Error(`uv sync 失败: ${detail}`);
  }

  const elapsed = Date.now();
  console.log(`[aiasys] Python 依赖安装完成`);

  onProgress?.({ message: "Python 环境就绪", step: "done", percent: 100 });
}

/**
 * 将 app bundle 中的 .venv 准备到可写运行时目录。
 * 级联降级策略：
 *   1. Full 模式：优先解压 .venv.tar.gz
 *   2. 降级兜底：逐文件复制 backendRoot/.venv
 *   3. Light/Portable 模式：前两步都失败时，用 bundled uv 从零创建
 *
 * 每步失败后自动尝试下一级，确保最终一定能得到一个可用的 .venv。
 */
async function preparePackagedVenv(backendRoot, runtimeStateRoot, onProgress) {
  const writableVenv = path.join(runtimeStateRoot, ".venv");
  if (isVenvReady(writableVenv)) {
    return; // 已存在且完整，直接复用
  }

  // 如果目录存在但不完整，清理后重新准备
  if (fs.existsSync(writableVenv)) {
    console.warn(
      `[aiasys] .venv 目录存在但不完整，将重新准备: ${writableVenv}`,
    );
    try {
      fs.rmSync(writableVenv, { recursive: true, force: true });
    } catch (error) {
      console.warn(`[aiasys] 清理不完整 .venv 失败: ${error.message}`);
    }
  }

  const archivePath = path.join(backendRoot, ".venv.tar.gz");
  const hasArchive = fs.existsSync(archivePath);
  const readOnlyVenv = path.join(backendRoot, ".venv");
  const hasReadOnlyVenv = fs.existsSync(readOnlyVenv);

  // Step 1: 尝试解压 .venv.tar.gz（Full 模式主路径）
  if (hasArchive) {
    const manifest = readVenvManifest(backendRoot);
    const totalEntries = manifest ? manifest.entries : 0;
    try {
      await extractVenvArchive(
        archivePath,
        runtimeStateRoot,
        totalEntries,
        onProgress,
      );
    } catch (error) {
      console.warn(
        `[aiasys] .venv 解压失败: ${error.message}`,
      );
      // 清理可能不完整的解压产物，但不阻塞后续降级
      try {
        if (fs.existsSync(writableVenv)) {
          fs.rmSync(writableVenv, { recursive: true, force: true });
        }
      } catch {
        // ignore
      }
    }
  }

  // Step 2: 解压失败或不存在压缩包时，尝试逐文件复制（Full 模式降级路径）
  if (!isVenvReady(writableVenv) && hasReadOnlyVenv) {
    await copyVenvFallback(backendRoot, runtimeStateRoot);
  }

  // Step 3: 前两步都失败时，从零创建（Light/Portable 模式）
  // 包括：无压缩包且无 .venv 目录，或压缩包解压失败且无 .venv 目录可降级
  if (!isVenvReady(writableVenv)) {
    console.log("[aiasys] Light/Portable 模式: 未找到内嵌 .venv，将从零创建 Python 环境");
    await bootstrapVenvFromScratch(backendRoot, runtimeStateRoot, onProgress);
  }

  fixPyvenvHomeIfNeeded(writableVenv);
  console.log(`[aiasys] .venv 就绪（可写副本）`);

  // macOS: 复制/解压后的 Mach-O 二进制可能仍携带 quarantine 属性，尝试清理
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
        console.log(`[aiasys] Python 解释器验证通过: ${candidate} (${validation.version})`);
        return candidate;
      }
      console.warn(
        `[aiasys] Python 解释器存在但无法执行: ${candidate}\n` +
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
  // 尝试多种 Unix 端口探测工具，兼容不同发行版/容器环境
  const pid =
    readListeningProcessUnixLsof(port) ||
    readListeningProcessUnixSs(port) ||
    readListeningProcessUnixFuser(port);

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

function readListeningProcessUnixLsof(port) {
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
  return pidLine ? pidLine.slice(1).trim() : null;
}

function readListeningProcessUnixSs(port) {
  const ssResult = spawnSync(
    "ss",
    ["-ltnp", `sport = :${port}`],
    { encoding: "utf-8", timeout: 5000 },
  );

  if (ssResult.status !== 0 || ssResult.error) {
    return null;
  }

  // 输出格式：LISTEN 0  128  127.0.0.1:13011  0.0.0.0:*  users:(("python",pid=12345,fd=3))
  const match = ssResult.stdout.match(/pid=(\d+)/);
  return match ? match[1] : null;
}

function readListeningProcessUnixFuser(port) {
  const fuserResult = spawnSync(
    "fuser",
    [`${port}/tcp`],
    { encoding: "utf-8", timeout: 5000 },
  );

  if (fuserResult.status !== 0 || fuserResult.error) {
    return null;
  }

  const pid = fuserResult.stdout.trim().split(/\s+/)[0];
  return pid || null;
}

/**
 * 解码 Windows 子进程输出。
 * 中文 Windows 上 powershell/netstat/tasklist 可能返回 GBK(cp936)，
 * 直接按 utf-8 解码会出现乱码；这里优先 utf-8，出现替换字符时回退到 gbk。
 */
function decodeProcessOutput(buffer) {
  if (!buffer || buffer.length === 0) {
    return "";
  }
  const utf8 = iconv.decode(buffer, "utf-8");
  if (!utf8.includes("\uFFFD")) {
    return utf8;
  }
  return iconv.decode(buffer, "gbk");
}

function readListeningProcessWindows(port) {
  const portNum = Number(port);
  if (!Number.isInteger(portNum) || portNum <= 0 || portNum > 65535) {
    return null;
  }

  // 优先使用 PowerShell Get-NetTCPConnection：状态枚举值不受系统语言影响
  const psResult = spawnSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-Command",
      `Get-NetTCPConnection -LocalPort ${portNum} -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1 | ForEach-Object { $_.OwningProcess }`,
    ],
    { windowsHide: true, timeout: 5000 },
  );

  let pid = null;
  if (psResult.status === 0 && psResult.stdout) {
    pid = decodeProcessOutput(psResult.stdout).trim();
  }

  // PowerShell 不可用或没有结果时，回退到 netstat -ano
  // netstat 状态列随 Windows 语言变化，因此只通过固定列位置匹配，不依赖状态文本
  if (!pid || pid === "0") {
    const netstatResult = spawnSync("netstat", ["-ano"], {
      windowsHide: true,
    });

    if (netstatResult.status === 0 && netstatResult.stdout) {
      const output = decodeProcessOutput(netstatResult.stdout);
      const lines = output.split("\r\n").join("\n").split("\n");
      for (const rawLine of lines) {
        const line = rawLine.trim();
        // 格式: TCP    <local>    <foreign>    <state>    <pid>
        if (!line.startsWith("TCP")) {
          continue;
        }
        const parts = line.split(/\s+/);
        if (parts.length < 5) {
          continue;
        }
        const localAddress = parts[1];
        const candidatePid = parts[parts.length - 1];
        // PID 应为纯数字；状态列不是数字，可作为额外校验
        if (!/^\d+$/.test(candidatePid)) {
          continue;
        }
        // 精确匹配端口
        const localPort = localAddress.split(":").pop();
        if (localPort === String(portNum)) {
          pid = candidatePid;
          break;
        }
      }
    }
  }

  if (!pid || pid === "0") {
    return null;
  }

  // 获取进程命令行，用于 canReuseService 判断进程是否属于当前 checkout
  // tasklist /FO CSV 默认只返回 Image Name，无法做路径匹配；
  // 改用 PowerShell Get-CimInstance Win32_Process 取 CommandLine
  const psCommandResult = spawnSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-Command",
      `Get-CimInstance Win32_Process -Filter "ProcessId=${pid}" | Select-Object -ExpandProperty CommandLine`,
    ],
    { windowsHide: true, timeout: 5000 },
  );

  if (psCommandResult.status === 0 && psCommandResult.stdout) {
    const commandLine = decodeProcessOutput(psCommandResult.stdout).trim();
    if (commandLine) {
      return { pid, command: commandLine };
    }
  }

  // 降级：用 tasklist 取进程名，至少能判断是否有进程占用
  const tasklistResult = spawnSync(
    "tasklist",
    ["/FI", `PID eq ${pid}`, "/FO", "CSV", "/NH"],
    { windowsHide: true },
  );

  if (tasklistResult.status !== 0 || !tasklistResult.stdout) {
    return { pid, command: "" };
  }

  const tasklistOutput = decodeProcessOutput(tasklistResult.stdout);
  const csvLine = tasklistOutput.trim().split("\r\n").join("\n").split("\n")[0];
  if (!csvLine) {
    return { pid, command: "" };
  }

  const match = csvLine.match(/^"([^"]+)"/);
  const processName = match ? match[1] : csvLine.split(",")[0];

  return {
    pid,
    command: processName || "",
  };
}



function createAbortToken() {
  const token = { aborted: false };
  token.cancel = () => {
    token.aborted = true;
  };
  return token;
}

/**
 * 等待 URL 就绪，同时监控子进程是否已崩溃退出。
 * 如果子进程在轮询期间崩溃，提前抛出错误，避免 90 秒干等。
 *
 * 支持两种模式：
 * - 静态 childProcesses 数组（向后兼容）
 * - options.getChildProcesses 动态获取当前子进程列表，便于追踪重启后的新进程
 * - options.signal 取消令牌，用于重启时中止旧的等待 Promise
 */
async function waitForUrl(url, label, timeoutMs = 90_000, childProcesses = [], options = {}) {
  const start = Date.now();
  const getChildren =
    typeof options.getChildProcesses === "function"
      ? options.getChildProcesses
      : () => childProcesses;
  const signal = options.signal || null;
  while (Date.now() - start < timeoutMs) {
    if (signal && signal.aborted) {
      throw new Error(`__CANCELLED__: ${label} 等待已取消`);
    }

    // 检查是否有子进程已崩溃或被终止
    for (const child of getChildren()) {
      if (!child) continue;
      if (child.__spawnFailed) {
        throw new Error(
          `${label} 子进程启动失败，无法继续等待服务就绪: ${url}`,
        );
      }
      if (child.exitCode !== null || child.signalCode !== null || child.killed) {
        // 若子进程配置了自动重启且未耗尽，继续等待重启后的新进程替换旧引用
        if (child.__autoRestart && !child.__restartExhausted) {
          console.warn(
            `[aiasys] ${label} 子进程已退出，但配置了自动重启，继续等待服务就绪: ${url}`,
          );
          continue;
        }
        throw new Error(
          `${label} 子进程已退出（exitCode=${child.exitCode}, signal=${child.signalCode}），` +
            `无法继续等待服务就绪: ${url}`,
        );
      }
    }

    if (await probeUrl(url)) {
      console.log(
        `[aiasys] ${label} 已就绪，耗时 ${Date.now() - start}ms: ${url}`,
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
const MAX_LOG_FILE_BYTES = 10 * 1024 * 1024; // 10MB

function rotateLogFile(logFilePath, maxBytes = MAX_LOG_FILE_BYTES) {
  try {
    const stat = fs.statSync(logFilePath);
    if (stat.size < maxBytes) {
      return;
    }
    const backupPath = `${logFilePath}.1`;
    if (fs.existsSync(backupPath)) {
      fs.rmSync(backupPath, { force: true });
    }
    fs.renameSync(logFilePath, backupPath);
  } catch {
    // ignore rotation errors
  }
}

function createLogStream(logFilePath) {
  fs.mkdirSync(path.dirname(logFilePath), { recursive: true });
  rotateLogFile(logFilePath);
  const stream = fs.createWriteStream(logFilePath, { flags: "a" });
  stream.on("error", (error) => {
    console.error(`[aiasys] 日志流写入失败 ${logFilePath}:`, error);
  });
  const now = new Date().toISOString();
  stream.write(`\n[${now}] === 日志开始 ===\n`);
  return stream;
}

function decodeProcessOutput(data) {
  if (!Buffer.isBuffer(data)) {
    return String(data);
  }

  // UTF-8 优先；出现替换字符时尝试中文 Windows 常见编码 GBK/cp936
  const utf8 = data.toString("utf-8");
  if (!utf8.includes("\uFFFD")) {
    return utf8;
  }

  try {
    const gbk = iconv.decode(data, "gbk");
    if (!gbk.includes("\uFFFD")) {
      return gbk;
    }
  } catch {
    // ignore decoding errors
  }

  // 最后兜底：按字节保留原始内容，永不出错
  return data.toString("latin1");
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

    // 附加元数据，供 waitForUrl 等调用方判断重启策略
    child.__autoRestart = autoRestart;
    child.__restartExhausted = false;

    // 日志流
    let logStream = null;
    if (options?.__logFilePath) {
      try {
        logStream = createLogStream(options.__logFilePath);
      } catch (error) {
        console.error(`[aiasys] 无法创建日志文件 ${options.__logFilePath}:`, error);
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
      console.error(`[aiasys] ${name} 启动失败:`, error);
      child.__spawnFailed = true;
      if (logStream && !logStream.destroyed) {
        logStream.write(`[${name}] 启动失败: ${error.message}\n`);
      }
      // 通知崩溃，让 waitForUrl 等调用方提前失败
      if (typeof options?.onCrash === "function") {
        options.onCrash({ error: error.message, restartCount, maxRestarts });
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
        `[aiasys] ${name} 提前退出: code=${code ?? "null"} signal=${signal ?? "null"}`,
      );

      // 通知崩溃
      if (typeof options?.onCrash === "function") {
        options.onCrash({ code, signal, restartCount, maxRestarts });
      }

      // 自动重启前确保旧进程树（包括可能残留的孙子进程）被清理，避免端口/资源泄漏
      if (child.pid) {
        terminateProcessTreeSync(child.pid, 1000);
      }

      // 自动重启
      if (autoRestart && restartCount < maxRestarts && canRestart()) {
        restartCount++;
        console.log(
          `[aiasys] ${name} 将在 2 秒后自动重启 (${restartCount}/${maxRestarts})...`,
        );
        if (logStream && !logStream.destroyed) {
          logStream.write(
            `[${name}] 将在 2 秒后自动重启 (${restartCount}/${maxRestarts})...\n`,
          );
        }

        setTimeout(() => {
          if (!canRestart()) {
            console.log(`[aiasys] ${name} 重启已取消（正在关闭）`);
            child.__restartExhausted = true;
            return;
          }
          const newChild = spawnOnce();
          if (typeof options?.onRestart === "function") {
            options.onRestart(newChild);
          }
        }, 2000);
      } else if (autoRestart) {
        console.error(
          `[aiasys] ${name} 已达最大重启次数 (${maxRestarts})，不再重启`,
        );
        child.__restartExhausted = true;
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
  if (!child || !child.pid || child.killed || child.exitCode !== null) {
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

  // 等待进程退出，若仍未退出则发送 SIGKILL 兜底
  const graceMs = 5000;
  const pollMs = 200;
  const start = Date.now();
  while (Date.now() - start < graceMs) {
    if (child.killed || child.exitCode !== null) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, pollMs));
  }

  if (!child.killed && child.exitCode === null) {
    console.warn(`[aiasys] 子进程 SIGTERM 未退出，发送 SIGKILL: ${child.pid}`);
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      // ignore
    }
  }
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
    this.onStatusUpdate = null;
  }

  /**
   * 向外部（main.cjs -> splash）报告启动进度。
   * 失败不阻塞启动。
   */
  _emitStatus(status) {
    try {
      if (typeof this.onStatusUpdate === "function") {
        this.onStatusUpdate(status);
      }
    } catch (e) {
      // ignore
    }
  }

  async preparePackagedRuntimeState() {
    if (!this.isPackaged) {
      return;
    }

    fs.mkdirSync(this.runtimeStateRoot, { recursive: true });

    const packagedDataRoot = path.join(this.backendRoot, "data");
    if (fs.existsSync(packagedDataRoot) && !fs.existsSync(this.backendDataRoot)) {
      this._emitStatus({ message: "正在复制初始数据...", step: 1, total: 5 });
      await fs.promises.cp(packagedDataRoot, this.backendDataRoot, {
        recursive: true,
        preserveTimestamps: true,
      });
    }

    // 用户导入的 skill / capability 源必须位于可写运行时目录（AppImage 等资源目录只读）
    const writableSourceDirs = [
      { src: path.join(this.backendRoot, "skills", "store"), dst: path.join(this.runtimeStateRoot, "skills", "store") },
      { src: path.join(this.backendRoot, "capability_sources", "store"), dst: path.join(this.runtimeStateRoot, "capability_sources", "store") },
    ];
    for (const { src, dst } of writableSourceDirs) {
      if (fs.existsSync(src) && !fs.existsSync(dst)) {
        this._emitStatus({ message: `正在复制 ${path.basename(path.dirname(src))}...`, step: 2, total: 5 });
        await fs.promises.cp(src, dst, { recursive: true, preserveTimestamps: true });
      }
      fs.mkdirSync(dst, { recursive: true });
    }

    fs.mkdirSync(this.backendDataRoot, { recursive: true });
    fs.mkdirSync(this.backendLogsRoot, { recursive: true });
    fs.mkdirSync(this.backendWorkspacesRoot, { recursive: true });

    console.log(
      `[aiasys] packaged runtime root: ${this.runtimeStateRoot}`,
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
   * 确保有一个 persisted JWT Secret 供后端认证使用。
   * 桌面打包版的 config.toml 位于只读资源目录，无法写入真实 secret，
   * 因此通过环境变量注入，并把 secret 持久化到运行时目录，避免每次重启失效。
   */
  _ensureJwtSecret() {
    const secretDir = path.join(this.runtimeStateRoot, ".aiasys");
    const secretPath = path.join(secretDir, "jwt-secret");
    try {
      if (fs.existsSync(secretPath)) {
        return fs.readFileSync(secretPath, "utf-8").trim();
      }
    } catch (error) {
      console.warn(`[aiasys] 读取 JWT secret 失败: ${error.message}`);
    }

    const secret = crypto.randomBytes(32).toString("hex");
    try {
      fs.mkdirSync(secretDir, { recursive: true });
      fs.writeFileSync(secretPath, secret, "utf-8");
      // 限制文件权限（Unix 上仅所有者可读写）
      try {
        fs.chmodSync(secretPath, 0o600);
      } catch {
        // ignore on Windows
      }
    } catch (error) {
      console.warn(`[aiasys] 持久化 JWT secret 失败: ${error.message}`);
    }
    return secret;
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
      console.log(`[aiasys] PYTHONPATH: ${sitePackages}`);
    }

    return { ...env, ...extraEnv };
  }

  /**
   * 构建 backend 子进程环境变量，附加桌面模式标识。
   */
  _bundledUvPath() {
    return resolveBundledUvPath(this.backendRoot);
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
      console.warn(`[aiasys] 未支持的内置 fnm 平台: ${key}`);
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
      AIASYS_AUTH_JWT_SECRET: this._ensureJwtSecret(),
      ELECTRON_DISABLE_SANDBOX: process.env.ELECTRON_DISABLE_SANDBOX || "1",
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
    this._emitStatus({ message: "正在准备运行环境...", step: 1, total: 5 });
    await this.preparePackagedRuntimeState();

    // 构建时已按平台修复（dylib/shebang/pyvenv.cfg）。
    // 运行时：打包模式下 backendRoot 只读，需复制 .venv 到可写运行时目录并修复。
    if (this.isPackaged) {
      this._emitStatus({ message: "正在准备 Python 运行环境...", step: 1, total: 5 });
      await preparePackagedVenv(
        this.backendRoot,
        this.runtimeStateRoot,
        (event) => {
          // 使用 bootstrap 提供的消息文本，兜底用解压消息
          const message = event.message || `正在解压 Python 运行环境... ${event.percent || 0}%`;
          this._emitStatus({
            message,
            step: 1,
            total: 5,
            percent: event.percent,
          });
        },
      );
    }

    this._emitStatus({ message: "正在初始化本地工作区...", step: 2, total: 5 });

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
      console.log(`[aiasys] 复用现有 backend: ${backendHealthUrl}`);
      return;
    }

    const pythonExecutable = resolvePythonExecutable(this._getVenvRoot());

    // 首次复制 .venv 后预热 Python，强制系统安全软件（Gatekeeper / Defender）完成首次扫描，
    // 避免 backend 子进程启动时被挂起或延迟。
    this._emitStatus({ message: "正在预热 Python 运行环境...", step: 2, total: 5 });
    await prewarmVenvPython(pythonExecutable);

    this._emitStatus({ message: "正在启动本地服务...", step: 3, total: 5 });
    console.log("[aiasys] 启动 backend ...");

    // 用于跟踪当前 backend 子进程引用，重启后更新
    let currentBackendChild = null;
    // 每次新的 backend 等待对应一个取消令牌，连续崩溃时先取消旧等待，避免并发/过期 Promise 误报
    let backendReadyToken = null;

    const child = spawnManagedProcess(
      "backend",
      pythonExecutable,
      ["-m", "uvicorn", "app.main:app", "--host", this.host, "--port", String(this.backendPort)],
      {
        cwd: fs.existsSync(this.backendRoot) ? this.backendRoot : this.runtimeStateRoot,
        env: this.buildBackendEnv({
          AIASYS_RUNTIME_ROOT: this.runtimeStateRoot || this.backendRoot,
        }),
        __logFilePath: this.getLogFilePath("backend"),
        autoRestart: true,
        canRestart: () => !this.isShuttingDown,
        onCrash: (info) => {
          console.error(`[aiasys] backend 崩溃: ${JSON.stringify(info)}`);
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

          // 取消上一个等待 Promise（如果还在进行），避免多次重启产生并发或过期通知
          if (backendReadyToken) {
            backendReadyToken.cancel();
          }
          backendReadyToken = createAbortToken();

          // 等待 backend 健康检查通过后通知渲染进程
          // 只关注 backend 子进程，避免 frontend 退出干扰判断
          waitForUrl(backendHealthUrl, "backend", 90_000, [], {
            getChildProcesses: () => [currentBackendChild],
            signal: backendReadyToken,
          })
            .then(() => {
              console.log("[aiasys] backend 重启后已就绪");
              if (typeof this.onBackendReady === "function") {
                this.onBackendReady();
              }
            })
            .catch((err) => {
              if (err && err.message && err.message.startsWith("__CANCELLED__")) {
                // 旧的等待被新的重启取消，属于正常流程，不通知前端
                return;
              }
              console.error("[aiasys] backend 重启后健康检查失败:", err);
              if (typeof this.onBackendCrash === "function") {
                this.onBackendCrash({ exitCode: null, signal: null, error: err.message });
              }
            });
        },
      },
    );
    currentBackendChild = child;
    this.managedChildren.push(child);
    await waitForUrl(backendHealthUrl, "backend", 90_000, [], {
      getChildProcesses: () => this.managedChildren,
    });
  }

  async ensureFrontend() {
    this._emitStatus({ message: "正在启动前端界面...", step: 4, total: 5 });

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
      console.log(`[aiasys] 复用现有 frontend: ${frontendUrl}`);
      return;
    }

    if (this.mode === "preview") {
      this.ensureBuiltRenderer();
      console.log("[aiasys] 启动 preview frontend ...");
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
          autoRestart: false,
          __logFilePath: this.getLogFilePath("frontend"),
        },
      );
      this.managedChildren.push(child);
      await waitForUrl(frontendUrl, "frontend-preview", 90_000, [], {
        getChildProcesses: () => this.managedChildren,
      });
      return;
    }

    console.log("[aiasys] 启动 Vite frontend ...");
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
        autoRestart: false,
        // Windows 上 spawn 需要 shell 才能执行 .cmd 文件
        shell: process.platform === "win32",
        __logFilePath: this.getLogFilePath("frontend"),
      },
    );
    this.managedChildren.push(child);
    await waitForUrl(frontendUrl, "frontend-dev", 90_000, [], {
      getChildProcesses: () => this.managedChildren,
    });
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
  // 以下导出仅用于测试
  _readVenvManifest: readVenvManifest,
  _extractVenvArchive: extractVenvArchive,
  _preparePackagedVenv: preparePackagedVenv,
  _bootstrapVenvFromScratch: bootstrapVenvFromScratch,
  _resolveBundledUvPath: resolveBundledUvPath,
};
