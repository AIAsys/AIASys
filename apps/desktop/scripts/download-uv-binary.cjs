const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const UV_VERSION = "0.11.3";
const REPO = "astral-sh/uv";

const PLATFORM_TRIPLES = {
  "darwin-arm64": "aarch64-apple-darwin",
  "darwin-x64":   "x86_64-apple-darwin",
  "linux-arm64":  "aarch64-unknown-linux-gnu",
  "linux-x64":    "x86_64-unknown-linux-gnu",
  "windows-x64":  "x86_64-pc-windows-msvc",
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
  if (platform === "win32")                       return "windows-x64";
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

/**
 * 用 curl 下载文件。curl 自动遵循代理环境变量（http_proxy/https_proxy）。
 */
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

function verifySha256(filePath, expectedHash) {
  const result = spawnSync("sha256sum", [filePath], { encoding: "utf-8", stdio: "pipe" });
  if (result.status !== 0) {
    console.warn("[download-uv] sha256sum 不可用，跳过校验");
    return true;
  }
  const actualHash = (result.stdout || "").trim().split(/\s+/)[0];
  if (actualHash !== expectedHash) {
    throw new Error(
      `SHA256 校验失败: 期望 ${expectedHash}, 实际 ${actualHash}`
    );
  }
  console.log("[download-uv] SHA256 校验通过");
  return true;
}

function extractTarGz(gzPath, targetDir) {
  console.log(`[download-uv] 解压: ${gzPath}`);
  const result = spawnSync("tar", ["-xzf", gzPath, "-C", targetDir], {
    encoding: "utf-8", stdio: "pipe",
  });
  if (result.status !== 0) {
    throw new Error(`解压失败: ${result.stderr || result.error}`);
  }
}

async function downloadForPlatform(slug) {
  slug = slug || detectPlatform();
  const triple = PLATFORM_TRIPLES[slug];
  if (!triple) throw new Error(`未知平台 slug: ${slug}`);

  const repoRoot = resolveRepoRoot();
  const vendorDir = path.join(repoRoot, "apps", "backend", "vendor", "uv");
  const platformDir = path.join(vendorDir, slug);
  const binaryName = slug.startsWith("windows") ? "uv.exe" : "uv";
  const binaryPath = path.join(platformDir, binaryName);

  // 已存在且可执行则跳过
  if (fs.existsSync(binaryPath) && fs.statSync(binaryPath).mode & 0o111) {
    console.log(`[download-uv] ${slug} 已存在且可执行，跳过下载`);
    return binaryPath;
  }

  const assetName = `uv-${triple}.tar.gz`;
  const shaName = `${assetName}.sha256`;

  // 构建下载 URL（直连 + 镜像两种候选）
  const bases = [downloadBase()];
  if (bases[0] === "https://github.com") {
    // 直连时也尝试 ghfast 镜像作为 fallback（应对国内网络问题）
    bases.push("https://ghfast.top/https://github.com");
  }

  const downloadDir = path.join(repoRoot, "apps", "backend", "vendor", "uv", ".download");
  fs.mkdirSync(downloadDir, { recursive: true });
  const archivePath = path.join(downloadDir, assetName);
  const shaPath = path.join(downloadDir, shaName);

  // 下载 tar.gz（依次尝试各 base URL）
  let lastErr;
  for (const base of bases) {
    const url = `${base}/astral-sh/uv/releases/download/${UV_VERSION}/${assetName}`;
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

  // 下载 sha256 校验文件
  let expectedSha = null;
  for (const base of bases) {
    const url = `${base}/astral-sh/uv/releases/download/${UV_VERSION}/${shaName}`;
    try {
      curlDownload(url, shaPath);
      const content = fs.readFileSync(shaPath, "utf-8").trim();
      expectedSha = content.split(/\s+/)[0];
      break;
    } catch {
      console.warn(`[download-uv] 获取 sha256 文件失败，跳过校验`);
    }
  }

  if (expectedSha) {
    verifySha256(archivePath, expectedSha);
  }

  // 解压到临时目录，然后取出一级目录中的二进制
  const extractDir = path.join(downloadDir, "_extracted");
  fs.mkdirSync(extractDir, { recursive: true });
  extractTarGz(archivePath, extractDir);

  // 找到解压后的一级子目录
  const entries = fs.readdirSync(extractDir);
  if (entries.length !== 1 || !fs.statSync(path.join(extractDir, entries[0])).isDirectory()) {
    throw new Error(`解压后结构不符合预期: ${entries.join(", ")}`);
  }
  const srcDir = path.join(extractDir, entries[0]);

  if (slug.startsWith("windows")) {
    const src = path.join(srcDir, "uv.exe");
    if (!fs.existsSync(src)) throw new Error(`解压后未找到 uv.exe，期望在 ${src}`);
    fs.mkdirSync(platformDir, { recursive: true });
    fs.cpSync(src, binaryPath);
    console.log(`[download-uv] 已放置: ${binaryPath}`);
  } else {
    const src = path.join(srcDir, "uv");
    if (!fs.existsSync(src)) throw new Error(`解压后未找到 uv 二进制，期望在 ${src}`);
    fs.mkdirSync(platformDir, { recursive: true });
    fs.cpSync(src, binaryPath);
    fs.chmodSync(binaryPath, (fs.statSync(binaryPath).mode | 0o111) & 0o7777);
    console.log(`[download-uv] 已放置: ${binaryPath}`);
  }

  // 清理临时文件
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
  windows-x64     Windows x64

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

// 允许被 require 调用
module.exports = { downloadForPlatform, detectPlatform, UV_VERSION };

if (require.main === module) {
  main();
}
