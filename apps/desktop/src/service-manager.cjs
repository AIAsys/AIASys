const fs = require("fs");
const net = require("net");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const HOST = process.env.AIASYS_DESKTOP_HOST || "127.0.0.1";
const DEFAULT_FRONTEND_PORT = 13000;
const DEFAULT_BACKEND_PORT = 13001;
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

function resolvePythonExecutable(backendRoot) {
  const platformCandidates =
    process.platform === "win32"
      ? [
          path.join(backendRoot, ".venv", "Scripts", "python.exe"),
          path.join(backendRoot, ".venv", "Scripts", "python"),
        ]
      : [
          path.join(backendRoot, ".venv", "bin", "python"),
          path.join(backendRoot, ".venv", "bin", "python3"),
        ];

  for (const candidate of platformCandidates) {
    if (fs.existsSync(candidate)) {
      return candidate;
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

  throw new Error(
    `找不到 backend Python 解释器，请确认已准备好虚拟环境: ${platformCandidates.join(", ")}`,
  );
}

function resolveNpmCommand() {
  return process.platform === "win32" ? "npm.cmd" : "npm";
}

async function probeUrl(url) {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 1500);

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

function readListeningProcess(port) {
  if (process.platform === "win32") {
    return null;
  }

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

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function commandIncludesPath(command, expectedPath) {
  const normalizedPath = expectedPath.replace(/[\\/]+$/, "");
  const pattern = new RegExp(`${escapeRegExp(normalizedPath)}(?:[\\\\/\\s'"]|$)`);
  return pattern.test(command);
}

async function canReuseService({ url, port, label, expectedPaths }) {
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

async function waitForUrl(url, label, timeoutMs = 90_000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await probeUrl(url)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(`${label} 在 ${timeoutMs}ms 内未就绪: ${url}`);
}

function spawnManagedProcess(name, command, args, options) {
  const child = spawn(command, args, {
    ...options,
    detached: process.platform !== "win32",
    stdio: "inherit",
  });

  child.once("error", (error) => {
    console.error(`[aiasys-desktop] ${name} 启动失败:`, error);
  });

  child.once("exit", (code, signal) => {
    if (code === 0 || signal === "SIGTERM") {
      return;
    }
    console.error(
      `[aiasys-desktop] ${name} 提前退出: code=${code ?? "null"} signal=${signal ?? "null"}`,
    );
  });

  return child;
}

async function terminateChild(child) {
  if (!child || child.killed || child.exitCode !== null) {
    return;
  }

  if (process.platform === "win32") {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        stdio: "ignore",
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

  async resolveDesiredPort({
    requestedPort,
    locked,
    label,
    expectedPaths,
    urlFactory,
    excludePorts = [],
  }) {
    const inspection = await canReuseService({
      url: urlFactory(requestedPort),
      port: requestedPort,
      label,
      expectedPaths,
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
      this.host,
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
        env: {
          ...process.env,
          PYTHONUNBUFFERED: "1",
          AIASYS_RUNTIME_ROOT: this.runtimeStateRoot || this.backendRoot,
          AIASYS_RUNTIME_DATA_DIR: this.backendDataRoot,
          AIASYS_RUNTIME_LOGS_DIR: this.backendLogsRoot,
          AIASYS_RUNTIME_WORKSPACES_DIR: this.backendWorkspacesRoot,
        },
      },
    );
    this.managedChildren.push(child);
    await waitForUrl(backendHealthUrl, "backend");
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
        [path.join(this.webRoot, "scripts", "local_preview_server.py")],
        {
          cwd: this.webRoot,
          env: {
            ...process.env,
            PYTHONUNBUFFERED: "1",
            AIASYS_PREVIEW_HOST: this.host,
            AIASYS_PREVIEW_PORT: String(this.frontendPort),
            AIASYS_PREVIEW_BACKEND_URL: this.backendBaseUrl,
          },
        },
      );
      this.managedChildren.push(child);
      await waitForUrl(frontendUrl, "frontend-preview");
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
      },
    );
    this.managedChildren.push(child);
    await waitForUrl(frontendUrl, "frontend-dev");
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
