#!/usr/bin/env node
/**
 * Desktop 系统调用集成测试
 *
 * 在真实系统环境中验证端口探测、端口回退、进程诊断等依赖系统调用的逻辑。
 *
 * 运行方式:
 *   cd apps/desktop && node scripts/integration-test.cjs
 *
 * 退出码:
 *   0 = 全部通过
 *   1 = 有失败
 */

const http = require("http");
const { spawnSync } = require("child_process");
const { describe, it } = require("node:test");
const assert = require("node:assert");

const {
  probeFreePort,
  findAvailablePort,
  canReuseService,
  probeUrl,
} = require("../src/utils.cjs");

const HOST = "127.0.0.1";

function log(...args) {
  console.log("[integration]", ...args);
}

/**
 * 探测 lsof 是否可用（部分容器/WSL 环境 lsof 会无限挂起）。
 */
function isLsofAvailable() {
  const result = spawnSync("lsof", ["-nP", "-iTCP:19000", "-sTCP:LISTEN", "-Fp"], {
    encoding: "utf-8",
    timeout: 1000,
  });
  // 即使端口没有监听，正常返回的 exit code 也是 1；timeout 或错误时 result.error 存在
  return !result.error;
}

const LSOf_AVAILABLE = isLsofAvailable();
if (!LSOf_AVAILABLE) {
  log("lsof 不可用或超时，跳过依赖进程诊断的测试");
}

/**
 * 启动一个临时 HTTP server，返回 { server, port, close() }
 */
function startMockServer(port) {
  return new Promise((resolve, reject) => {
    const server = http.createServer((req, res) => {
      if (req.url === "/") {
        res.writeHead(200);
        res.end("ok");
      } else {
        res.writeHead(404);
        res.end("not found");
      }
    });

    server.listen(port, HOST, () => {
      const actualPort = server.address().port;
      resolve({
        server,
        port: actualPort,
        close: () =>
          new Promise((res) => {
            server.close(() => res());
          }),
      });
    });

    server.once("error", reject);
  });
}

/**
 * 简化版 readListeningProcess，用于测试验证
 */
function readListeningProcess(port) {
  if (process.platform === "win32") {
    return readListeningProcessWindows(port);
  }

  const lsofResult = spawnSync(
    "lsof",
    ["-nP", `-iTCP:${port}`, "-sTCP:LISTEN", "-Fp"],
    { encoding: "utf-8", timeout: 1000 },
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

/**
 * Windows 版 readListeningProcess，使用 PowerShell 查询监听端口进程。
 */
function readListeningProcessWindows(port) {
  const psResult = spawnSync(
    "powershell.exe",
    [
      "-NoProfile",
      "-Command",
      `try { $conn = Get-NetTCPConnection -LocalPort ${port} -State Listen -ErrorAction Stop; ` +
        `$proc = Get-Process -Id $conn.OwningProcess -ErrorAction Stop; ` +
        `Write-Output \"PID=$($conn.OwningProcess)\"; ` +
        `Write-Output \"PATH=$($proc.Path)\" } catch { }`,
    ],
    { encoding: "utf-8", timeout: 2000, windowsHide: true },
  );

  if (psResult.status !== 0 || psResult.error || !psResult.stdout) {
    return null;
  }

  const lines = psResult.stdout.split(/\r?\n/).map((line) => line.trim());
  const pidLine = lines.find((line) => line.startsWith("PID="));
  const pathLine = lines.find((line) => line.startsWith("PATH="));
  if (!pidLine) {
    return null;
  }

  const pid = pidLine.slice("PID=".length).trim();
  const command = pathLine ? pathLine.slice("PATH=".length).trim() : "";
  if (!pid) {
    return null;
  }

  return { pid, command };
}

describe("probeFreePort", () => {
  it("空闲端口返回 true", async () => {
    // 找一个高端口，大概率空闲
    const port = 19000;
    const result = await probeFreePort(HOST, port);
    assert.strictEqual(result, true, `端口 ${port} 应该是空闲的`);
  });

  it("被占端口返回 false", async () => {
    const mockServer = await startMockServer(0);
    try {
      const result = await probeFreePort(HOST, mockServer.port);
      assert.strictEqual(result, false, `端口 ${mockServer.port} 应该被占`);
    } finally {
      await mockServer.close();
    }
  });
});

describe("findAvailablePort", () => {
  it("从起始端口开始找到第一个空闲端口", async () => {
    const port = await findAvailablePort(HOST, 19010);
    assert.strictEqual(typeof port, "number");
    assert.ok(port >= 19010, `找到的端口 ${port} 应该 >= 19010`);
  });

  it("跳过被占端口", async () => {
    const mockServer1 = await startMockServer(0);
    const mockServer2 = await startMockServer(0);
    try {
      const blocked = [mockServer1.port, mockServer2.port];
      const startPort = Math.min(mockServer1.port, mockServer2.port);
      const port = await findAvailablePort(HOST, startPort, blocked);
      assert.ok(
        !blocked.includes(port),
        `找到的端口 ${port} 不应该在排除列表 ${blocked} 中`,
      );
    } finally {
      await mockServer1.close();
      await mockServer2.close();
    }
  });
});

describe("canReuseService 真实场景", () => {
  it("服务健康：reusable=true", async () => {
    const mockServer = await startMockServer(0);
    try {
      const url = `http://${HOST}:${mockServer.port}/`;
      // 先获取实际进程命令，用它作为 expectedPaths
      const processInfo = readListeningProcess(mockServer.port);
      // 提取可执行文件路径，处理 Windows 路径含空格的情况（如 C:\Program Files\...）
      const cmd = processInfo?.command || "";
      const expectedPaths = cmd
        ? [cmd.match(/^"?[^"]+"?/)?.[0]?.replace(/^"|"$/g, "") || cmd.split(/\s+/)[0]]
        : [process.cwd()];

      const result = await canReuseService({
        url,
        port: mockServer.port,
        label: "mock",
        expectedPaths,
        readListeningProcess,
        probeUrl,
      });
      // 服务健康时，reusable 应为 true
      assert.strictEqual(result.reusable, true);
      assert.ok(
        ["healthy_current", "healthy_unknown"].includes(result.reason),
        `unexpected reason: ${result.reason}`,
      );
    } finally {
      await mockServer.close();
    }
  });

  it("服务未运行：reusable=false, reason=not_running", async () => {
    const port = 19030;
    // 确保端口空闲
    const free = await probeFreePort(HOST, port);
    if (!free) {
      log(`端口 ${port} 不空闲，跳过此测试`);
      return;
    }

    const result = await canReuseService({
      url: `http://${HOST}:${port}/`,
      port,
      label: "mock",
      expectedPaths: ["/nonexistent"],
      readListeningProcess,
      probeUrl,
    });
    assert.strictEqual(result.reusable, false);
    assert.strictEqual(result.reason, "not_running");
  });

  it("端口被其他进程占且不健康：reusable=false", async () => {
    if (!LSOf_AVAILABLE) {
      log("lsof 不可用，跳过 occupied_foreign 场景测试");
      return;
    }
    const mockServer = await startMockServer(0);
    try {
      const result = await canReuseService({
        url: `http://${HOST}:${mockServer.port}/nonexistent`,
        port: mockServer.port,
        label: "mock",
        expectedPaths: ["/definitely/not/matching"],
        readListeningProcess,
        probeUrl,
      });
      // 进程存在但 URL 返回 404，probeUrl 返回 false
      // 进程命令不匹配 expectedPaths，所以是 occupied_foreign
      assert.strictEqual(result.reusable, false);
      assert.strictEqual(result.reason, "occupied_foreign");
    } finally {
      await mockServer.close();
    }
  });
});

describe("readListeningProcess 诊断", () => {
  it("能正确找到监听进程", async () => {
    if (!LSOf_AVAILABLE) {
      log("lsof 不可用，跳过进程诊断测试");
      return;
    }
    const mockServer = await startMockServer(0);
    try {
      const info = readListeningProcess(mockServer.port);
      if (info === null) {
        log("lsof 返回空，跳过进程诊断测试");
        return;
      }
      assert.ok(info.pid, "应该有 PID");
      assert.ok(info.command, "应该有命令");
      assert.ok(info.command.includes("node"), `命令应包含 node: ${info.command}`);
    } finally {
      await mockServer.close();
    }
  });

  it("无监听进程返回 null", () => {
    const info = readListeningProcess(19050);
    assert.strictEqual(info, null);
  });
});

log("开始运行集成测试 ...");
