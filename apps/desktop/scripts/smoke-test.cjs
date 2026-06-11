#!/usr/bin/env node
/**
 * Desktop 打包产物 Smoke 测试
 *
 * 验证 dist/linux-unpacked/aiasys-desktop 能正常启动 backend 和 frontend 服务。
 *
 * 运行方式:
 *   cd apps/desktop && node scripts/smoke-test.cjs
 *
 * 退出码:
 *   0 = 通过
 *   1 = 产物不存在 / 启动失败 / 超时
 */

const fs = require("fs");
const path = require("path");
const net = require("net");
const { spawn, spawnSync } = require("child_process");

const DIST_DIR = path.resolve(__dirname, "..", "dist", "linux-unpacked");
const DESKTOP_BINARY = path.join(DIST_DIR, "aiasys-desktop");
const HOST = "127.0.0.1";
const BACKEND_START_PORT = 13020;
const FRONTEND_START_PORT = 13021;
const STARTUP_TIMEOUT_MS = 60000;
const HEALTH_PROBE_INTERVAL_MS = 1000;

function log(...args) {
  console.log("[smoke]", ...args);
}

function logError(...args) {
  console.error("[smoke]", ...args);
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
  for (let p = startPort; p < startPort + 200; p++) {
    if (blocked.has(p)) continue;
    if (await probeFreePort(host, p)) return p;
  }
  throw new Error(`无法找到可用端口，起始: ${startPort}`);
}

async function probeUrl(url, timeoutMs = 2000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: controller.signal, redirect: "manual" });
    return res.ok || res.status === 304;
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

function findPidsByPort(port) {
  // Linux/macOS: lsof
  const result = spawnSync("lsof", ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-Fp"], {
    encoding: "utf-8",
  });
  if (result.status !== 0) return [];
  return result.stdout
    .split("\n")
    .filter((line) => line.startsWith("p"))
    .map((line) => line.slice(1).trim())
    .filter(Boolean);
}

async function killByPort(port) {
  const pids = findPidsByPort(port);
  for (const pid of pids) {
    try {
      process.kill(Number(pid), "SIGTERM");
      log(`已发送 SIGTERM 到端口 ${port} 的进程 PID=${pid}`);
    } catch {
      // ignore
    }
  }
  // 等待进程退出
  await new Promise((resolve) => setTimeout(resolve, 1500));
  // 强制清理
  const remaining = findPidsByPort(port);
  for (const pid of remaining) {
    try {
      process.kill(Number(pid), "SIGKILL");
    } catch {
      // ignore
    }
  }
}

async function main() {
  log("开始 Smoke 测试 ...");

  // 1. 检查产物
  if (!fs.existsSync(DESKTOP_BINARY)) {
    logError(`产物不存在: ${DESKTOP_BINARY}`);
    logError("请先执行: npm run dist:linux:dir");
    process.exit(1);
  }
  log(`产物: ${DESKTOP_BINARY}`);

  // 2. 找空闲端口
  const backendPort = await findAvailablePort(HOST, BACKEND_START_PORT);
  const frontendPort = await findAvailablePort(HOST, FRONTEND_START_PORT, [backendPort]);
  log(`backend 端口: ${backendPort}, frontend 端口: ${frontendPort}`);

  // 3. 先清理可能残留的进程
  await killByPort(backendPort);
  await killByPort(frontendPort);

  // 4. 启动 desktop
  const args = [
    "--no-sandbox",
    "--disable-gpu",
    "--disable-namespace-sandbox",
    "--disable-setuid-sandbox",
  ];

  const childEnv = {
    ...process.env,
    AIASYS_DESKTOP_BACKEND_PORT: String(backendPort),
    AIASYS_DESKTOP_FRONTEND_PORT: String(frontendPort),
  };

  log("启动 desktop ...");
  const child = spawn(DESKTOP_BINARY, args, {
    env: childEnv,
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });

  // 收集 stdout/stderr 用于调试
  let stdoutBuf = "";
  let stderrBuf = "";
  if (child.stdout) {
    child.stdout.on("data", (d) => {
      stdoutBuf += d;
    });
  }
  if (child.stderr) {
    child.stderr.on("data", (d) => {
      stderrBuf += d;
    });
  }

  const backendUrl = `http://${HOST}:${backendPort}/health`;
  const frontendUrl = `http://${HOST}:${frontendPort}/`;

  let backendReady = false;
  let frontendReady = false;
  const start = Date.now();

  while (Date.now() - start < STARTUP_TIMEOUT_MS) {
    if (!backendReady) backendReady = await probeUrl(backendUrl);
    if (!frontendReady) frontendReady = await probeUrl(frontendUrl);

    if (backendReady && frontendReady) {
      log("backend 和 frontend 均已就绪");
      break;
    }

    // Electron 主进程可能在 WSLg 下崩溃，但 backend/frontend 子进程可能还在跑
    // 所以不因为 child.exitCode !== null 就立即失败，而是继续等端口
    await new Promise((resolve) => setTimeout(resolve, HEALTH_PROBE_INTERVAL_MS));
  }

  // 5. 终止进程
  try {
    process.kill(-child.pid, "SIGTERM");
    log(`已发送 SIGTERM 到进程组 PID=${child.pid}`);
  } catch (e) {
    log(`终止主进程失败: ${e.message}`);
  }

  // 等待主进程退出
  await new Promise((resolve) => setTimeout(resolve, 2000));

  // 清理可能残留的 backend/frontend 子进程
  await killByPort(backendPort);
  await killByPort(frontendPort);

  // 6. 判定结果
  if (!backendReady) {
    logError(`backend 未在 ${STARTUP_TIMEOUT_MS}ms 内就绪`);
    logError("stdout:\n", stdoutBuf.slice(-2000));
    logError("stderr:\n", stderrBuf.slice(-2000));
    process.exit(1);
  }

  if (!frontendReady) {
    logError(`frontend 未在 ${STARTUP_TIMEOUT_MS}ms 内就绪`);
    logError("stdout:\n", stdoutBuf.slice(-2000));
    logError("stderr:\n", stderrBuf.slice(-2000));
    process.exit(1);
  }

  log("PASS");
  process.exit(0);
}

main().catch((err) => {
  logError("未捕获异常:", err);
  process.exit(1);
});
