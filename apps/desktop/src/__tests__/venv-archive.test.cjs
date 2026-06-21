const fs = require("fs");
const path = require("path");
const os = require("os");
const { describe, it, beforeEach, afterEach } = require("node:test");
const assert = require("node:assert");
const tar = require("tar");

const {
  _readVenvManifest,
  _extractVenvArchive,
  _preparePackagedVenv,
} = require("../service-manager.cjs");

function tempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function createFakeVenv(dir) {
  const venvDir = path.join(dir, ".venv");
  const binDir = path.join(venvDir, "bin");
  const libDir = path.join(venvDir, "lib", "python3.12", "site-packages");
  fs.mkdirSync(binDir, { recursive: true });
  fs.mkdirSync(libDir, { recursive: true });
  fs.writeFileSync(path.join(binDir, "python3"), "#!/usr/bin/env python3\n", "utf-8");
  fs.writeFileSync(path.join(libDir, "module.py"), "print('hello')\n", "utf-8");
  fs.writeFileSync(
    path.join(venvDir, "pyvenv.cfg"),
    "home = python\nversion = 3.12.0\n",
    "utf-8",
  );
  return venvDir;
}

describe("venv archive", () => {
  let tmpDir = null;

  beforeEach(() => {
    tmpDir = tempDir("desktop-venv-archive-test-");
  });

  afterEach(() => {
    if (tmpDir) {
      fs.rmSync(tmpDir, { recursive: true, force: true });
      tmpDir = null;
    }
  });

  it("readVenvManifest 读取有效的 manifest", () => {
    const backendRoot = tmpDir;
    fs.writeFileSync(
      path.join(backendRoot, ".venv.manifest.json"),
      JSON.stringify({ entries: 42, compressedSize: 12345 }),
      "utf-8",
    );
    const manifest = _readVenvManifest(backendRoot);
    assert.strictEqual(manifest.entries, 42);
    assert.strictEqual(manifest.compressedSize, 12345);
  });

  it("readVenvManifest 对缺失/损坏文件返回 null", () => {
    assert.strictEqual(_readVenvManifest(tmpDir), null);

    fs.writeFileSync(
      path.join(tmpDir, ".venv.manifest.json"),
      "not json",
      "utf-8",
    );
    assert.strictEqual(_readVenvManifest(tmpDir), null);
  });

  it("extractVenvArchive 解压压缩包并报告进度", async () => {
    const backendRoot = tmpDir;
    const venvDir = createFakeVenv(backendRoot);
    const archivePath = path.join(backendRoot, ".venv.tar.gz");

    await tar.create(
      { gzip: true, file: archivePath, cwd: backendRoot },
      [".venv"],
    );

    const extractRoot = path.join(tmpDir, "extracted");
    fs.mkdirSync(extractRoot, { recursive: true });

    const progressEvents = [];
    await _extractVenvArchive(archivePath, extractRoot, 8, (event) => {
      progressEvents.push(event);
    });

    const extractedVenv = path.join(extractRoot, ".venv");
    assert.strictEqual(fs.existsSync(extractedVenv), true);
    assert.strictEqual(
      fs.existsSync(path.join(extractedVenv, "bin", "python3")),
      true,
    );
    assert.strictEqual(
      fs.existsSync(path.join(extractedVenv, "pyvenv.cfg")),
      true,
    );

    // 进度事件应包含 percent，且最后为 100
    assert.ok(progressEvents.length > 0);
    const lastEvent = progressEvents[progressEvents.length - 1];
    assert.strictEqual(lastEvent.percent, 100);
  });

  it("preparePackagedVenv 优先解压压缩包", async () => {
    const backendRoot = tmpDir;
    const venvDir = createFakeVenv(backendRoot);
    const archivePath = path.join(backendRoot, ".venv.tar.gz");

    await tar.create(
      { gzip: true, file: archivePath, cwd: backendRoot },
      [".venv"],
    );
    fs.rmSync(venvDir, { recursive: true, force: true });

    fs.writeFileSync(
      path.join(backendRoot, ".venv.manifest.json"),
      JSON.stringify({ entries: 8 }),
      "utf-8",
    );

    const runtimeStateRoot = path.join(tmpDir, "runtime");
    fs.mkdirSync(runtimeStateRoot, { recursive: true });

    const progressEvents = [];
    await _preparePackagedVenv(
      backendRoot,
      runtimeStateRoot,
      (event) => {
        progressEvents.push(event);
      },
    );

    const writableVenv = path.join(runtimeStateRoot, ".venv");
    assert.strictEqual(fs.existsSync(writableVenv), true);
    assert.strictEqual(
      fs.existsSync(path.join(writableVenv, "bin", "python3")),
      true,
    );
    assert.ok(progressEvents.length > 0);
    assert.strictEqual(progressEvents[progressEvents.length - 1].percent, 100);
  });

  it("preparePackagedVenv 无压缩包时回退到逐文件复制", async () => {
    const backendRoot = tmpDir;
    createFakeVenv(backendRoot);

    const runtimeStateRoot = path.join(tmpDir, "runtime");
    fs.mkdirSync(runtimeStateRoot, { recursive: true });

    const progressEvents = [];
    await _preparePackagedVenv(
      backendRoot,
      runtimeStateRoot,
      (event) => {
        progressEvents.push(event);
      },
    );

    const writableVenv = path.join(runtimeStateRoot, ".venv");
    assert.strictEqual(fs.existsSync(writableVenv), true);
    assert.strictEqual(
      fs.existsSync(path.join(writableVenv, "bin", "python3")),
      true,
    );
  });

  it("preparePackagedVenv 对已存在的完整 .venv 直接复用", async () => {
    const backendRoot = tmpDir;
    createFakeVenv(backendRoot);

    const runtimeStateRoot = path.join(tmpDir, "runtime");
    const writableVenv = path.join(runtimeStateRoot, ".venv");
    fs.mkdirSync(path.join(writableVenv, "bin"), { recursive: true });
    fs.writeFileSync(path.join(writableVenv, "bin", "python3"), "#!/bin/sh\necho ok", "utf-8");
    fs.writeFileSync(path.join(writableVenv, "existing"), "yes", "utf-8");

    let called = false;
    await _preparePackagedVenv(backendRoot, runtimeStateRoot, () => {
      called = true;
    });

    assert.strictEqual(called, false);
    assert.strictEqual(fs.readFileSync(path.join(writableVenv, "existing"), "utf-8"), "yes");
  });
});
