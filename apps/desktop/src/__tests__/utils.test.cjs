const { describe, it } = require("node:test");
const assert = require("node:assert");

const {
  escapeRegExp,
  commandIncludesPath,
  resolveNpmCommand,
  canReuseService,
  resolveDesiredPort,
} = require("../utils.cjs");

describe("escapeRegExp", () => {
  it("空字符串", () => {
    assert.strictEqual(escapeRegExp(""), "");
  });

  it("普通字符串无特殊字符", () => {
    assert.strictEqual(escapeRegExp("abc123"), "abc123");
  });

  it("转义所有正则特殊字符", () => {
    const input = ".*+?^${}()|[]\\";
    const expected = "\\.\\*\\+\\?\\^\\$\\{\\}\\(\\)\\|\\[\\]\\\\";
    assert.strictEqual(escapeRegExp(input), expected);
  });

  it("混合内容", () => {
    assert.strictEqual(
      escapeRegExp("path/to/file.js"),
      "path/to/file\\.js",
    );
  });
});

describe("commandIncludesPath", () => {
  it("完全匹配", () => {
    assert.strictEqual(
      commandIncludesPath("/home/ke/projects/AIASys/apps/backend/.venv/bin/python3", "/home/ke/projects/AIASys/apps/backend"),
      true,
    );
  });

  it("子路径匹配", () => {
    assert.strictEqual(
      commandIncludesPath("/home/ke/projects/AIASys/apps/backend/.venv/bin/python3", "/home/ke/projects/AIASys"),
      true,
    );
  });

  it("Windows 路径分隔符", () => {
    assert.strictEqual(
      commandIncludesPath("C:\\Users\\ke\\projects\\AIASys\\apps\\backend\\.venv\\Scripts\\python.exe", "C:\\Users\\ke\\projects\\AIASys\\apps\\backend"),
      true,
    );
  });

  it("路径后有空格", () => {
    assert.strictEqual(
      commandIncludesPath("/repo/apps/backend .venv/bin/python3", "/repo/apps/backend"),
      true,
    );
  });

  it("路径后有引号", () => {
    assert.strictEqual(
      commandIncludesPath('"/repo/apps/backend"/.venv/bin/python3', "/repo/apps/backend"),
      true,
    );
  });

  it("不匹配", () => {
    assert.strictEqual(
      commandIncludesPath("/other/project/.venv/bin/python3", "/repo/apps/backend"),
      false,
    );
  });

  it("末尾斜杠处理", () => {
    assert.strictEqual(
      commandIncludesPath("/repo/apps/backend/.venv/bin/python3", "/repo/apps/backend/"),
      true,
    );
  });

  it("部分匹配但不是路径边界", () => {
    assert.strictEqual(
      commandIncludesPath("/repo/apps/backend-old/.venv/bin/python3", "/repo/apps/backend"),
      false,
    );
  });
});

describe("resolveNpmCommand", () => {
  it("Linux/macOS 返回 npm", () => {
    if (process.platform === "win32") {
      // 在 Windows 上跳过
      return;
    }
    assert.strictEqual(resolveNpmCommand(), "npm");
  });

  it("Windows 返回 npm.cmd", () => {
    if (process.platform !== "win32") {
      // 在非 Windows 上跳过
      return;
    }
    assert.strictEqual(resolveNpmCommand(), "npm.cmd");
  });
});

describe("canReuseService", () => {
  const url = "http://127.0.0.1:13011/health";
  const port = 13011;
  const label = "backend";
  const expectedPaths = ["/repo/apps/backend"];

  it("not_running：端口无进程，URL 不健康", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => null,
      probeUrl: async () => false,
    });
    assert.strictEqual(result.reusable, false);
    assert.strictEqual(result.reason, "not_running");
    assert.strictEqual(result.processInfo, null);
  });

  it("occupied_unknown：有进程但无法获取命令，URL 不健康", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => ({ pid: "1234", command: "" }),
      probeUrl: async () => false,
    });
    assert.strictEqual(result.reusable, false);
    assert.strictEqual(result.reason, "occupied_unknown");
  });

  it("occupied_current：当前 checkout 的进程异常，URL 不健康", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => ({
        pid: "1234",
        command: "/repo/apps/backend/.venv/bin/python3",
      }),
      probeUrl: async () => false,
    });
    assert.strictEqual(result.reusable, false);
    assert.strictEqual(result.reason, "occupied_current");
  });

  it("occupied_foreign：其他进程的进程，URL 不健康", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => ({
        pid: "5678",
        command: "/other/project/.venv/bin/python3",
      }),
      probeUrl: async () => false,
    });
    assert.strictEqual(result.reusable, false);
    assert.strictEqual(result.reason, "occupied_foreign");
  });

  it("healthy_unknown：URL 健康，但无法获取进程信息", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => null,
      probeUrl: async () => true,
    });
    assert.strictEqual(result.reusable, true);
    assert.strictEqual(result.reason, "healthy_unknown");
  });

  it("healthy_current：URL 健康，进程属于当前 checkout", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => ({
        pid: "1234",
        command: "/repo/apps/backend/.venv/bin/python3",
      }),
      probeUrl: async () => true,
    });
    assert.strictEqual(result.reusable, true);
    assert.strictEqual(result.reason, "healthy_current");
  });

  it("healthy_foreign：URL 健康，进程不属于当前 checkout", async () => {
    const result = await canReuseService({
      url,
      port,
      label,
      expectedPaths,
      readListeningProcess: () => ({
        pid: "5678",
        command: "/other/project/.venv/bin/python3",
      }),
      probeUrl: async () => true,
    });
    assert.strictEqual(result.reusable, false);
    assert.strictEqual(result.reason, "healthy_foreign");
  });
});

describe("resolveDesiredPort", () => {
  const label = "backend";
  const expectedPaths = ["/repo/apps/backend"];
  const urlFactory = (port) => `http://127.0.0.1:${port}/health`;

  it("端口可复用：返回原端口 reuse=true", async () => {
    const result = await resolveDesiredPort({
      requestedPort: 13011,
      locked: false,
      label,
      expectedPaths,
      urlFactory,
      excludePorts: [],
      host: "127.0.0.1",
      findAvailablePort: async () => 13012,
      canReuseService: async () => ({
        reusable: true,
        reason: "healthy_current",
        processInfo: { pid: "1234", command: "/repo/apps/backend/.venv/bin/python3" },
      }),
      readListeningProcess: () => null,
      probeUrl: async () => true,
    });
    assert.deepStrictEqual(result, { port: 13011, reuse: true });
  });

  it("端口未运行：返回原端口 reuse=false", async () => {
    const result = await resolveDesiredPort({
      requestedPort: 13011,
      locked: false,
      label,
      expectedPaths,
      urlFactory,
      excludePorts: [],
      host: "127.0.0.1",
      findAvailablePort: async () => 13012,
      canReuseService: async () => ({
        reusable: false,
        reason: "not_running",
        processInfo: null,
      }),
      readListeningProcess: () => null,
      probeUrl: async () => false,
    });
    assert.deepStrictEqual(result, { port: 13011, reuse: false });
  });

  it("occupied_current：抛出错误", async () => {
    await assert.rejects(
      async () => {
        await resolveDesiredPort({
          requestedPort: 13011,
          locked: false,
          label,
          expectedPaths,
          urlFactory,
          excludePorts: [],
          host: "127.0.0.1",
          findAvailablePort: async () => 13012,
          canReuseService: async () => ({
            reusable: false,
            reason: "occupied_current",
            processInfo: { pid: "1234", command: "/repo/apps/backend/.venv/bin/python3" },
          }),
          readListeningProcess: () => null,
          probeUrl: async () => false,
        });
      },
      /异常进程/,
    );
  });

  it("locked + 端口被占：抛出错误", async () => {
    await assert.rejects(
      async () => {
        await resolveDesiredPort({
          requestedPort: 13011,
          locked: true,
          label,
          expectedPaths,
          urlFactory,
          excludePorts: [],
          host: "127.0.0.1",
          findAvailablePort: async () => 13012,
          canReuseService: async () => ({
            reusable: false,
            reason: "healthy_foreign",
            processInfo: { pid: "5678", command: "/other/.venv/bin/python3" },
          }),
          readListeningProcess: () => null,
          probeUrl: async () => true,
        });
      },
      /锁定/,
    );
  });

  it("非 locked + 端口被占：回退到可用端口", async () => {
    const result = await resolveDesiredPort({
      requestedPort: 13011,
      locked: false,
      label,
      expectedPaths,
      urlFactory,
      excludePorts: [],
      host: "127.0.0.1",
      findAvailablePort: async (host, startPort, excludePorts) => {
        assert.strictEqual(startPort, 13012);
        return 13015;
      },
      canReuseService: async () => ({
        reusable: false,
        reason: "healthy_foreign",
        processInfo: { pid: "5678", command: "/other/.venv/bin/python3" },
      }),
      readListeningProcess: () => null,
      probeUrl: async () => true,
    });
    assert.deepStrictEqual(result, { port: 13015, reuse: false });
  });
});
