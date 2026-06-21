const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
const { spawnSync } = require("child_process");

const FNM_VERSION = "1.39.0";
const REPO = "Schniz/fnm";

const PLATFORM_TRIPLES = {
  "linux-x64":    "fnm-linux",
  "linux-arm64":  "fnm-arm64",
  "darwin-x64":   "fnm-macos",
  "darwin-arm64": "fnm-macos",
  "win-x64":      "fnm-windows",
};

/**
 * 镜像优先级：
 * 1. FNM_DOWNLOAD_MIRROR 环境变量（完整 URL 前缀，如 https://ghfast.top/https://github.com）
 * 2. 空 = 直连 https://github.com
 */
function downloadBase() {
  const env = process.env.FNM_DOWNLOAD_MIRROR;
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

/**
 * 用 curl 下载文件。curl 自动遵循代理环境变量（http_proxy/https_proxy）。
 */
function curlDownload(url, dest) {
  console.log(`[download-fnm] 下载: ${url}`);
  let result = spawnSync(
    "curl",
    ["-L", "-f", "--connect-timeout", "15", "--max-time", "300", "-o", dest, url],
    { encoding: "utf-8", stdio: "pipe", windowsHide: true }
  );
  if (result.status !== 0) {
    // Fallback to wget
    console.log(`[download-fnm] curl 不可用，尝试 wget...`);
    result = spawnSync(
      "wget",
      ["-q", "--timeout=15", "--tries=3", "-O", dest, url],
      { encoding: "utf-8", stdio: "pipe", windowsHide: true }
    );
  }
  if (result.status !== 0) {
    const detail = result.stderr || result.error || `exit ${result.status}`;
    throw new Error(`下载失败 (${url}): curl 和 wget 均不可用 (${detail})`);
  }
  const stat = fs.statSync(dest);
  console.log(`[download-fnm] 已保存: ${dest} (${(stat.size / 1024 / 1024).toFixed(1)} MB)`);
}

function verifySha256(filePath, expectedHash) {
  // 使用 Node.js 内置 crypto 计算 SHA256，避免依赖外部命令 sha256sum（Windows 无此命令）
  let buf;
  try {
    buf = fs.readFileSync(filePath);
  } catch (err) {
    console.warn(`[download-fnm] 读取文件失败，跳过校验: ${err.message}`);
    return true;
  }
  const actualHash = crypto.createHash("sha256").update(buf).digest("hex");
  if (actualHash !== expectedHash) {
    throw new Error(
      `SHA256 校验失败: 期望 ${expectedHash}, 实际 ${actualHash}`
    );
  }
  console.log("[download-fnm] SHA256 校验通过");
  return true;
}

function resolvePython() {
  const candidates = [process.env.PYTHON, process.env.PYTHON3, "py", "python3", "python"].filter(Boolean);
  for (const cmd of candidates) {
    const result = spawnSync(cmd, ["--version"], { encoding: "utf-8", stdio: "pipe", windowsHide: true });
    if (result.status === 0) return cmd;
  }
  return null;
}

function unzip(zipPath, targetDir) {
  console.log(`[download-fnm] 解压: ${zipPath}`);
  fs.mkdirSync(targetDir, { recursive: true });
  // Windows 10+ 内置 tar 命令支持 zip 格式；Unix 上优先用 unzip，fallback 到 Python zipfile
  const isWindows = process.platform === "win32";
  const primaryCmd = isWindows ? "tar" : "unzip";
  const primaryArgs = isWindows
    ? ["-xf", zipPath, "-C", targetDir]
    : ["-q", "-o", zipPath, "-d", targetDir];
  const primaryResult = spawnSync(primaryCmd, primaryArgs, {
    encoding: "utf-8", stdio: "pipe", windowsHide: true,
  });
  if (primaryResult.status === 0) return;
  if (primaryResult.error && primaryResult.error.code === "ENOENT") {
    const pyCmd = resolvePython();
    if (!pyCmd) {
      throw new Error("未找到可用的 Python 解释器（尝试 py/python3/python），无法解压 zip");
    }
    console.log(`[download-fnm] 未找到 ${primaryCmd}，使用 ${pyCmd} zipfile 解压`);
    const pyResult = spawnSync(
      pyCmd,
      ["-m", "zipfile", "-e", zipPath, targetDir],
      { encoding: "utf-8", stdio: "pipe", windowsHide: true }
    );
    if (pyResult.status !== 0) {
      throw new Error(`${pyCmd} zipfile 解压失败: ${pyResult.stderr || pyResult.error}`);
    }
    return;
  }
  throw new Error(`解压失败: ${primaryResult.stderr || primaryResult.error}`);
}

async function downloadForPlatform(slug) {
  slug = slug || detectPlatform();
  const triple = PLATFORM_TRIPLES[slug];
  if (!triple) throw new Error(`未知平台 slug: ${slug}`);

  const repoRoot = resolveRepoRoot();
  const vendorDir = path.join(repoRoot, "apps", "backend", "vendor", "node");
  const platformDir = path.join(vendorDir, slug);
  const binaryName = slug.startsWith("win") ? "fnm.exe" : "fnm";
  const binaryPath = path.join(platformDir, binaryName);

  // 已存在且可执行则跳过
  // Windows 上 fs.statSync(path).mode 不包含可执行位，只要文件存在即可跳过
  const isWindows = slug.startsWith("win");
  if (fs.existsSync(binaryPath) && (isWindows || (fs.statSync(binaryPath).mode & 0o111))) {
    console.log(`[download-fnm] ${slug} 已存在且可执行，跳过下载`);
    return binaryPath;
  }

  const assetName = `${triple}.zip`;
  const shaName = `${assetName}.sha256`;

  // 构建下载 URL（直连 + 镜像两种候选）
  const bases = [downloadBase()];
  if (bases[0] === "https://github.com") {
    // 直连时也尝试 ghfast 镜像作为 fallback（应对国内网络问题）
    bases.push("https://ghfast.top/https://github.com");
  }

  const downloadDir = path.join(vendorDir, ".download");
  fs.mkdirSync(downloadDir, { recursive: true });
  const archivePath = path.join(downloadDir, assetName);
  const shaPath = path.join(downloadDir, shaName);

  // 下载 zip（依次尝试各 base URL）
  let lastErr;
  for (const base of bases) {
    const url = `${base}/${REPO}/releases/download/v${FNM_VERSION}/${assetName}`;
    try {
      curlDownload(url, archivePath);
      lastErr = null;
      break;
    } catch (err) {
      lastErr = err;
      console.warn(`[download-fnm] 下载失败，尝试下一个源: ${err.message}`);
    }
  }
  if (lastErr) throw lastErr;

  // 下载 sha256 校验文件
  let expectedSha = null;
  for (const base of bases) {
    const url = `${base}/${REPO}/releases/download/v${FNM_VERSION}/${shaName}`;
    try {
      curlDownload(url, shaPath);
      const content = fs.readFileSync(shaPath, "utf-8").trim();
      expectedSha = content.split(/\s+/)[0];
      break;
    } catch {
      console.warn("[download-fnm] 获取 sha256 文件失败，跳过校验");
    }
  }

  if (expectedSha) {
    verifySha256(archivePath, expectedSha);
  }

  // 解压到临时目录，然后取出 fnm 二进制
  const extractDir = path.join(downloadDir, "_extracted");
  fs.mkdirSync(extractDir, { recursive: true });
  unzip(archivePath, extractDir);

  // fnm zip 解压后直接包含 fnm/fnm.exe，没有额外嵌套目录
  const srcBinary = path.join(extractDir, binaryName);
  if (!fs.existsSync(srcBinary)) {
    // 某些版本可能有一个中间目录，尝试查找
    const entries = fs.readdirSync(extractDir);
    const found = entries.find(e => {
      const p = path.join(extractDir, e);
      return fs.statSync(p).isFile() && (e === "fnm" || e === "fnm.exe");
    });
    if (!found) {
      throw new Error(`解压后未找到 ${binaryName}，期望在 ${srcBinary}`);
    }
    fs.mkdirSync(platformDir, { recursive: true });
    fs.cpSync(path.join(extractDir, found), binaryPath);
  } else {
    fs.mkdirSync(platformDir, { recursive: true });
    fs.cpSync(srcBinary, binaryPath);
  }

  if (!slug.startsWith("win")) {
    fs.chmodSync(binaryPath, (fs.statSync(binaryPath).mode | 0o111) & 0o7777);
  }

  console.log(`[download-fnm] 已放置: ${binaryPath}`);

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
用法: node download-fnm-binary.cjs [平台 slug]

平台 slug:
  darwin-arm64    macOS Apple Silicon
  darwin-x64      macOS Intel
  linux-arm64     Linux ARM64
  linux-x64       Linux x64
  win-x64         Windows x64

不传参数时自动检测当前平台。
示例:
  node apps/desktop/scripts/download-fnm-binary.cjs
  node apps/desktop/scripts/download-fnm-binary.cjs linux-x64

镜像加速（网络不佳时）:
  FNM_DOWNLOAD_MIRROR=https://ghfast.top/https://github.com node apps/desktop/scripts/download-fnm-binary.cjs
`);
    process.exit(0);
  }

  (async () => {
    try {
      const slug = targetSlug || detectPlatform();
      console.log(`[download-fnm] 平台: ${slug}, fnm v${FNM_VERSION}`);
      const result = await downloadForPlatform(slug);
      console.log(`[download-fnm] 完成: ${result}`);
      process.exit(0);
    } catch (err) {
      console.error(`[download-fnm] 失败: ${err.message}`);
      process.exit(1);
    }
  })();
}

// 允许被 require 调用
module.exports = { downloadForPlatform, detectPlatform, FNM_VERSION };

if (require.main === module) {
  main();
}
