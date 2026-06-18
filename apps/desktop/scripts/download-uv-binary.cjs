const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const UV_VERSION = "0.11.21";
const REPO = "astral-sh/uv";

const PLATFORM_TRIPLES = {
  "linux-x64":    "uv-x86_64-unknown-linux-gnu.tar.gz",
  "linux-arm64":  "uv-aarch64-unknown-linux-gnu.tar.gz",
  "darwin-x64":   "uv-x86_64-apple-darwin.tar.gz",
  "darwin-arm64": "uv-aarch64-apple-darwin.tar.gz",
  "win-x64":      "uv-x86_64-pc-windows-msvc.zip",
};

/**
 * 镜像优先级：
 * 1. UV_DOWNLOAD_MIRROR 环境变量（完整 URL 前缀，如 https://ghfast.top/https://github.com）
 * 2. 空 = 直连 https://github.com
 */
function downloadBase() {
  const env = process.env.UV_DOWNLOAD_MIRROR;
  return env ? env.replace(/\/+$/, "") : "https://github.com";
}

function detectPlatform() {
  const platform = process.platform;
  const arch = process.arch;
  if (platform === "darwin" && arch === "arm64") return "darwin-arm64";
  if (platform === "darwin" && arch === "x64")   return "darwin-x64";
  if (platform === "linux" && arch === "arm64")  return "linux-arm64";
  if (platform === "linux" && arch === "x64")    return "linux-x64";
  if (platform === "win32")                       return "win-x64";
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
  console.log(`[download-uv] 下载: ${url}`);
  const result = spawnSync(
    "curl",
    ["-L", "-f", "--connect-timeout", "15", "--max-time", "300", "-o", dest, url],
    { encoding: "utf-8", stdio: "pipe" }
  );
  if (result.status !== 0) {
    const detail = result.stderr || result.error || `curl exit ${result.status}`;
    throw new Error(`下载失败 (${url}): ${detail}`);
  }
  const stat = fs.statSync(dest);
  console.log(`[download-uv] 已保存: ${dest} (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
}

function resolvePython() {
  const candidates = [process.env.PYTHON, process.env.PYTHON3, "py", "python3", "python"].filter(Boolean);
  for (const cmd of candidates) {
    const result = spawnSync(cmd, ["--version"], { encoding: "utf-8", stdio: "pipe" });
    if (result.status === 0) return cmd;
  }
  return null;
}

function extractArchive(archivePath, targetDir, isZip) {
  console.log(`[download-uv] 解压: ${archivePath}`);
  fs.mkdirSync(targetDir, { recursive: true });
  let result;
  if (isZip) {
    // 优先使用系统 unzip；WSL 等环境可能未安装 unzip，fallback 到 python zipfile
    const unzipResult = spawnSync("unzip", ["-q", "-o", archivePath, "-d", targetDir], {
      encoding: "utf-8",
      stdio: "pipe",
    });
    if (unzipResult.status === 0) {
      result = unzipResult;
    } else if (unzipResult.error && unzipResult.error.code === "ENOENT") {
      const pyCmd = resolvePython();
      if (!pyCmd) {
        throw new Error("未找到可用的 Python 解释器（尝试 py/python3/python），无法解压 zip");
      }
      console.log(`[download-uv] 未找到 unzip，使用 ${pyCmd} zipfile 解压`);
      const pyResult = spawnSync(
        pyCmd,
        ["-m", "zipfile", "-e", archivePath, targetDir],
        { encoding: "utf-8", stdio: "pipe" }
      );
      if (pyResult.status !== 0) {
        throw new Error(`${pyCmd} zipfile 解压失败: ${pyResult.stderr || pyResult.error}`);
      }
      result = pyResult;
    } else {
      result = unzipResult;
    }
  } else {
    result = spawnSync("tar", ["-xzf", archivePath, "-C", targetDir], {
      encoding: "utf-8",
      stdio: "pipe",
    });
  }
  if (result.status !== 0) {
    throw new Error(`解压失败: ${result.stderr || result.error}`);
  }
}

async function downloadForPlatform(slug) {
  slug = slug || detectPlatform();
  const assetName = PLATFORM_TRIPLES[slug];
  if (!assetName) throw new Error(`未知平台 slug: ${slug}`);

  const repoRoot = resolveRepoRoot();
  const vendorDir = path.join(repoRoot, "apps", "backend", "vendor", "uv");
  // 与 service-manager.cjs 中 _bundledUvPath() 的目录命名保持一致
  const platformDirMap = {
    "linux-x64":    "linux-x64",
    "linux-arm64":  "linux-arm64",
    "darwin-x64":   "darwin-x64",
    "darwin-arm64": "darwin-arm64",
    "win-x64":      "windows-x64",
  };
  const platformDirName = platformDirMap[slug];
  const platformDir = path.join(vendorDir, platformDirName);
  const binaryName = slug.startsWith("win") ? "uv.exe" : "uv";
  const binaryPath = path.join(platformDir, binaryName);

  if (fs.existsSync(binaryPath)) {
    console.log(`[download-uv] ${slug} 已存在，跳过下载`);
    return binaryPath;
  }

  const isZip = assetName.endsWith(".zip");

  const bases = [downloadBase()];
  if (bases[0] === "https://github.com") {
    bases.push("https://ghfast.top/https://github.com");
  }

  const downloadDir = path.join(vendorDir, ".download");
  fs.mkdirSync(downloadDir, { recursive: true });
  const archivePath = path.join(downloadDir, assetName);

  let lastErr;
  for (const base of bases) {
    const url = `${base}/${REPO}/releases/download/${UV_VERSION}/${assetName}`;
    try {
      curlDownload(url, archivePath);
      lastErr = null;
      break;
    } catch (err) {
      lastErr = err;
      console.warn(`[download-uv] 下载失败，尝试下一个源: ${err.message}`);
    }
  }
  if (lastErr) throw lastErr;

  const extractDir = path.join(downloadDir, "_extracted");
  extractArchive(archivePath, extractDir, isZip);

  // 某些压缩包在根目录，有些有一层平台子目录，递归查找 uv/uv.exe
  function findBinary(dir) {
    const entries = fs.readdirSync(dir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        const found = findBinary(fullPath);
        if (found) return found;
      } else if (entry.name === binaryName) {
        return fullPath;
      }
    }
    return null;
  }

  const srcBinary = findBinary(extractDir);
  if (!srcBinary) {
    throw new Error(`解压后未找到 ${binaryName}，已解压目录: ${extractDir}`);
  }

  fs.mkdirSync(platformDir, { recursive: true });
  fs.cpSync(srcBinary, binaryPath);

  if (!slug.startsWith("win")) {
    fs.chmodSync(binaryPath, (fs.statSync(binaryPath).mode | 0o111) & 0o7777);
  }

  console.log(`[download-uv] 已放置: ${binaryPath}`);

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
用法: node download-uv-binary.cjs [平台 slug]

平台 slug:
  darwin-arm64    macOS Apple Silicon
  darwin-x64      macOS Intel
  linux-arm64     Linux ARM64
  linux-x64       Linux x64
  win-x64         Windows x64

不传参数时自动检测当前平台。
示例:
  node apps/desktop/scripts/download-uv-binary.cjs
  node apps/desktop/scripts/download-uv-binary.cjs linux-x64

镜像加速（网络不佳时）:
  UV_DOWNLOAD_MIRROR=https://ghfast.top/https://github.com node apps/desktop/scripts/download-uv-binary.cjs
`);
    process.exit(0);
  }

  (async () => {
    try {
      const slug = targetSlug || detectPlatform();
      console.log(`[download-uv] 平台: ${slug}, uv v${UV_VERSION}`);
      const result = await downloadForPlatform(slug);
      console.log(`[download-uv] 完成: ${result}`);
      process.exit(0);
    } catch (err) {
      console.error(`[download-uv] 失败: ${err.message}`);
      process.exit(1);
    }
  })();
}

module.exports = { downloadForPlatform, detectPlatform, UV_VERSION };

if (require.main === module) {
  main();
}
