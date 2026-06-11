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
      const expectedPaths = processInfo?.command
        ? [processInfo.command.split(" ")[0]]
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
    const mockServer = await startMockServer(0);
    try {
      const info = readListeningProcess(mockServer.port);
      if (info === null) {
        log("lsof 不可用或返回空，跳过进程诊断测试");
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
