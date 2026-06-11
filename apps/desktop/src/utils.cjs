/**
 * Desktop service-manager 的可测试工具函数。
 *
 * 所有函数不依赖 Electron 模块，可在纯 Node.js 环境中运行和测试。
 */

const net = require("net");

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
  probeUrl,
  canReuseService,
  resolveDesiredPort,
  probeFreePort,
  findAvailablePort,
};
