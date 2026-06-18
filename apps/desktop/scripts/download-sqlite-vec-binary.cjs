const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const SQLITE_VEC_VERSION = "0.1.6";
const REPO = "asg017/sqlite-vec";

const PLATFORM_ASSETS = {
  "linux-x64":    { slug: "linux-x86_64",   subdir: "linux-x86_64", filename: "vec0.so"    },
  "linux-arm64":  { slug: "linux-x86_64",   subdir: "linux-x86_64", filename: "vec0.so"    },
  "darwin-x64":   { slug: "macos-x86_64",   subdir: "macos-x86_64", filename: "vec0.dylib" },
  "darwin-arm64": { slug: "macos-aarch64",  subdir: "macos-aarch64", filename: "vec0.dylib" },
  "win-x64":      { slug: "windows-x86_64", subdir: "windows-x86_64", filename: "vec0.dll"  },
};

/**
 * 镜像优先级：
 * 1. SQLITE_VEC_DOWNLOAD_MIRROR 环境变量（完整 URL 前缀）
 * 2. 空 = 直连 https://github.com
 */
function downloadBase() {
  const env = process.env.SQLITE_VEC_DOWNLOAD_MIRROR;
  return env ? env.replace(/\/+$/, "") : "https://github.com";
}

function detectPlatform() {
  const platform = process.platform;
  const arch = process.arch;
  if (platform === "darwin" && arch === "arm64") return "darwin-arm64";
  if (platform === "darwin" && arch === "x64")   return "darwin-x64";
  if (platform === "linux" && arch === "arm64")  return "linux-arm64";
  if (platform === "linux" && arch === "x64")    return "linux-x64";
  if (platform === "win32")                         return "win-x64";
  throw new Error(`不支持的平台: ${platform}-${arch}`);
}

function resolveRepoRoot() {
  let dir = __dirname;
  for (let i = 0; i < 8; i++) {
    const candidate = path.join(dir, "apps", "backend");
    if (fs.existsSync(candidate)) {
      return path.resolve(dir);
    }
    dir = path.dirname(dir);
  }
  return path.resolve(__dirname, "..", "..", "..");
}

function curlDownload(url, dest) {
  console.log(`[download-sqlite-vec] 下载: ${url}`);
  const result = spawnSync(
    "curl",
    ["-L", "-f", "--connect-timeout", "15", "--max-time", "120", "-o", dest, url],
    { encoding: "utf-8", stdio: "pipe" }
  );
  if (result.status !== 0) {
    const detail = result.stderr || result.error || `curl exit ${result.status}`;
    throw new Error(`下载失败 (${url}): ${detail}`);
  }
  const stat = fs.statSync(dest);
  console.log(`[download-sqlite-vec] 已保存: ${dest} (${(stat.size / 1024).toFixed(1)} KB)`);
}

function resolvePython() {
  const candidates = [process.env.PYTHON, process.env.PYTHON3, "py", "python3", "python"].filter(Boolean);
  for (const cmd of candidates) {
    const result = spawnSync(cmd, ["--version"], { encoding: "utf-8", stdio: "pipe" });
    if (result.status === 0) return cmd;
  }
  return null;
}

function extractTarGz(archivePath, targetDir) {
  console.log(`[download-sqlite-vec] 解压: ${archivePath}`);
  fs.mkdirSync(targetDir, { recursive: true });
  const result = spawnSync("tar", ["-xzf", archivePath, "-C", targetDir], {
    encoding: "utf-8",
    stdio: "pipe",
  });
  if (result.status === 0) return;
  if (result.error && result.error.code === "ENOENT") {
    const pyCmd = resolvePython();
    if (!pyCmd) {
      throw new Error("未找到可用的 Python 解释器（尝试 py/python3/python），无法解压 tar.gz");
    }
    console.log(`[download-sqlite-vec] 未找到 tar，使用 ${pyCmd} tarfile 解压`);
    const pyResult = spawnSync(
      pyCmd,
      ["-c", `import tarfile, os, gzip; ar="${archivePath.replace(/"/g, '\\"')}"; td="${targetDir.replace(/"/g, '\\"')}"; f=tarfile.open(ar, "r:gz" if ar.endswith(".gz") else "r"); f.extractall(td)`],
      { encoding: "utf-8", stdio: "pipe" }
    );
    if (pyResult.status !== 0) {
      throw new Error(`${pyCmd} tarfile 解压失败: ${pyResult.stderr || pyResult.error}`);
    }
    return;
  }
  throw new Error(`解压失败: ${result.stderr || result.error}`);
}

async function downloadForPlatform(platformSlug) {
  platformSlug = platformSlug || detectPlatform();
  const cfg = PLATFORM_ASSETS[platformSlug];
  if (!cfg) throw new Error(`未知平台 slug: ${platformSlug}`);

  const repoRoot = resolveRepoRoot();
  const vendorDir = path.join(repoRoot, "apps", "backend", "vendor", "sqlite-vec");
  const platformDir = path.join(vendorDir, cfg.subdir);
  const binaryPath = path.join(platformDir, cfg.filename);

  if (fs.existsSync(binaryPath)) {
    console.log(`[download-sqlite-vec] ${platformSlug} 已存在，跳过下载`);
    return binaryPath;
  }

  const assetName = `sqlite-vec-${SQLITE_VEC_VERSION}-loadable-${cfg.slug}.tar.gz`;

  const bases = [downloadBase()];
  if (bases[0] === "https://github.com") {
    bases.push("https://ghfast.top/https://github.com");
  }

  const downloadDir = path.join(vendorDir, ".download");
  fs.mkdirSync(downloadDir, { recursive: true });
  const archivePath = path.join(downloadDir, assetName);

  let lastErr;
  for (const base of bases) {
    const url = `${base}/${REPO}/releases/download/v${SQLITE_VEC_VERSION}/${assetName}`;
    try {
      curlDownload(url, archivePath);
      lastErr = null;
      break;
    } catch (err) {
      lastErr = err;
      console.warn(`[download-sqlite-vec] 下载失败，尝试下一个源: ${err.message}`);
    }
  }
  if (lastErr) throw lastErr;

  extractTarGz(archivePath, platformDir);

  if (!fs.existsSync(binaryPath)) {
    throw new Error(`解压后未找到 ${cfg.filename}，期望在 ${binaryPath}`);
  }

  if (!platformSlug.startsWith("win")) {
    fs.chmodSync(binaryPath, (fs.statSync(binaryPath).mode | 0o111) & 0o7777);
  }

  console.log(`[download-sqlite-vec] 已放置: ${binaryPath}`);

  fs.rmSync(downloadDir, { recursive: true, force: true });

  return binaryPath;
}

function main() {
  let targetSlug = null;
  let help = false;

  for (const arg of process.argv.slice(2)) {
    if (arg === "--help" || arg === "-h") {
      help = true;
    } else {
      targetSlug = arg;
    }
  }

  if (help) {
    console.log(`
用法: node download-sqlite-vec-binary.cjs [平台 slug]

平台 slug:
  darwin-arm64    macOS Apple Silicon
  darwin-x64      macOS Intel
  linux-arm64     Linux ARM64
  linux-x64       Linux x64
  win-x64         Windows x64

不传参数时自动检测当前平台。
示例:
  node apps/desktop/scripts/download-sqlite-vec-binary.cjs
  node apps/desktop/scripts/download-sqlite-vec-binary.cjs linux-x64

镜像加速（网络不佳时）:
  SQLITE_VEC_DOWNLOAD_MIRROR=https://ghfast.top/https://github.com node apps/desktop/scripts/download-sqlite-vec-binary.cjs
`);
    process.exit(0);
  }

  (async () => {
    try {
      const slug = targetSlug || detectPlatform();
      console.log(`[download-sqlite-vec] 平台: ${slug}, sqlite-vec v${SQLITE_VEC_VERSION}`);
      const result = await downloadForPlatform(slug);
      console.log(`[download-sqlite-vec] 完成: ${result}`);
      process.exit(0);
    } catch (err) {
      console.error(`[download-sqlite-vec] 失败: ${err.message}`);
      process.exit(1);
    }
  })();
}

module.exports = { downloadForPlatform, detectPlatform, SQLITE_VEC_VERSION };

if (require.main === module) {
  main();
}
