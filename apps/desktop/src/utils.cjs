/**
 * Desktop service-manager 的可测试工具函数。
 *
 * 所有函数不依赖 Electron 模块，可在纯 Node.js 环境中运行和测试。
 */

const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawnSync } = require("child_process");

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function commandIncludesPath(command, expectedPath) {
  const normalizedPath = expectedPath.replace(/[\\/]+$/, "");
  const pattern = new RegExp(
    `${escapeRegExp(normalizedPath)}(?:[\\\\/\\s'"]|$)`,
  );
  return pattern.test(command);
}

function resolveNpmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

/**
 * 验证 Python 可执行文件是否能正常执行。
 *
 * @param {string} pythonPath
 * @returns {{ok: true, version: string} | {ok: false, error: string}}
 */
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

/**
 * 动态查找 venv 的 site-packages 目录。
 * Windows: .venv/Lib/site-packages
 * macOS/Linux: .venv/lib/pythonX.Y/site-packages
 *
 * @param {string} backendRoot
 * @returns {string | null}
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
 * 修复 pyvenv.cfg 的 home 路径为嵌入目录，并修复 venv 符号链接。
 * 前提是目标目录可写（已在调用侧确认）。
 *
 * @param {string} backendRoot
 */
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

async function probeUrl(url, timeoutMs = 1500) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
      redirect: "manual",
    });
    return response.ok || response.status === 304;
  } catch {
    return false;
  } finally {
    clearTimeout(timeoutId);
  }
}

/**
 * 判断指定端口上的服务是否可以复用。
 *
 * @param {Object} params
 * @param {string} params.url - 健康检查 URL
 * @param {number} params.port - 端口号
 * @param {string} params.label - 服务标签（用于报错信息）
 * @param {string[]} params.expectedPaths - 判断进程是否属于当前 checkout 的路径列表
 * @param {function(number): {pid:string,command:string}|null} params.readListeningProcess - 读取端口进程信息的函数
 * @param {function(string): Promise<boolean>} params.probeUrl - URL 健康探测函数
 */
async function canReuseService({
  url,
  port,
  label,
  expectedPaths,
  readListeningProcess,
  probeUrl,
}) {
  const processInfo = readListeningProcess(port);
  const healthy = await probeUrl(url);

  if (!healthy) {
    if (!processInfo) {
      return {
        reusable: false,
        reason: "not_running",
        processInfo: null,
      };
    }

    if (!processInfo.command) {
      return {
        reusable: false,
        reason: "occupied_unknown",
        processInfo,
      };
    }

    const belongsToCurrentCheckout = expectedPaths.some((expectedPath) =>
      commandIncludesPath(processInfo.command, expectedPath),
    );
    return {
      reusable: false,
      reason: belongsToCurrentCheckout ? "occupied_current" : "occupied_foreign",
      processInfo,
    };
  }

  if (!processInfo || !processInfo.command) {
    return {
      reusable: true,
      reason: "healthy_unknown",
      processInfo,
    };
  }

  const belongsToCurrentCheckout = expectedPaths.some((expectedPath) =>
    commandIncludesPath(processInfo.command, expectedPath),
  );
  if (belongsToCurrentCheckout) {
    return {
      reusable: true,
      reason: "healthy_current",
      processInfo,
    };
  }

  return {
    reusable: false,
    reason: "healthy_foreign",
    processInfo,
  };
}

/**
 * 解析期望端口，处理复用、占用、回退等场景。
 *
 * @param {Object} params
 * @param {number} params.requestedPort - 请求的端口
 * @param {boolean} params.locked - 是否锁定（不允许回退）
 * @param {string} params.label - 服务标签
 * @param {string[]} params.expectedPaths - 判断归属的路径列表
 * @param {function(number): string} params.urlFactory - 根据端口生成 URL
 * @param {number[]} params.excludePorts - 排除的端口列表
 * @param {function(string, number, number[]): Promise<number>} params.findAvailablePort - 查找可用端口
 * @param {function(Object): Promise<Object>} params.canReuseService - canReuseService 函数
 * @param {function(number): {pid:string,command:string}|null} params.readListeningProcess
 * @param {function(string): Promise<boolean>} params.probeUrl
 */
async function resolveDesiredPort({
  requestedPort,
  locked,
  label,
  expectedPaths,
  urlFactory,
  excludePorts = [],
  host,
  findAvailablePort,
  canReuseService: canReuseServiceFn,
  readListeningProcess,
  probeUrl,
}) {
  const inspection = await canReuseServiceFn({
    url: urlFactory(requestedPort),
    port: requestedPort,
    label,
    expectedPaths,
    readListeningProcess,
    probeUrl,
  });

  if (inspection.reusable) {
    return {
      port: requestedPort,
      reuse: true,
    };
  }

  if (inspection.reason === "not_running") {
    return {
      port: requestedPort,
      reuse: false,
    };
  }

  const processCommand =
    inspection.processInfo?.command ||
    `pid=${inspection.processInfo?.pid || "unknown"}`;

  if (inspection.reason === "occupied_current") {
    throw new Error(
      `${label} 端口 ${requestedPort} 上存在当前 checkout 的异常进程，但健康检查未通过: ${processCommand}`,
    );
  }

  if (locked) {
    throw new Error(
      `${label} 端口 ${requestedPort} 已被占用，且当前通过环境变量锁定了该端口: ${processCommand}`,
    );
  }

  const fallbackPort = await findAvailablePort(
    host,
    requestedPort + 1,
    excludePorts,
  );
  console.warn(
    `[aiasys-desktop] ${label} 端口 ${requestedPort} 不可直接复用，自动切换到 ${fallbackPort}: ${processCommand}`,
  );
  return {
    port: fallbackPort,
    reuse: false,
  };
}

function probeFreePort(host, port) {
  return new Promise((resolve) => {
    const server = net.createServer();
    server.unref();
    server.once("error", () => resolve(false));
    server.listen(port, host, () => {
      server.close(() => resolve(true));
    });
  });
}

async function findAvailablePort(host, startPort, excludePorts = []) {
  const blocked = new Set(excludePorts);
  for (let candidate = startPort; candidate < startPort + 200; candidate += 1) {
    if (blocked.has(candidate)) {
      continue;
    }
    if (await probeFreePort(host, candidate)) {
      return candidate;
    }
  }

  throw new Error(`无法为 desktop 找到可用端口，起始端口: ${startPort}`);
}

module.exports = {
  escapeRegExp,
  commandIncludesPath,
  resolveNpmCommand,
  validatePythonExecutable,
  getVenvSitePackages,
  fixPyvenvHomeIfNeeded,
  probeUrl,
  canReuseService,
  resolveDesiredPort,
  probeFreePort,
  findAvailablePort,
};
