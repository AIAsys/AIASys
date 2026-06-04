const fs = require("fs");
const path = require("path");

const desktopRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(desktopRoot, "..", "..");
const runtimeRoot = path.join(desktopRoot, ".dist");
const webStageRoot = path.join(runtimeRoot, "web");
const backendStageRoot = path.join(runtimeRoot, "backend");
const backendRoot = path.join(repoRoot, "apps", "backend");
const webRoot = path.join(repoRoot, "apps", "web");

function ensureExists(targetPath, label) {
  if (!fs.existsSync(targetPath)) {
    throw new Error(`${label} 不存在: ${targetPath}`);
  }
}

function resetDir(targetPath) {
  fs.rmSync(targetPath, { recursive: true, force: true });
  fs.mkdirSync(targetPath, { recursive: true });
}

function copyPath(sourcePath, targetPath, options = {}) {
  ensureExists(sourcePath, "source");
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  fs.cpSync(sourcePath, targetPath, {
    recursive: true,
    preserveTimestamps: true,
    ...options,
  });
}

function copyPathIfExists(sourcePath, targetPath, options = {}) {
  if (!fs.existsSync(sourcePath)) {
    console.warn(`[aiasys-desktop] 跳过不存在的路径: ${sourcePath}`);
    return;
  }
  copyPath(sourcePath, targetPath, options);
}

/**
 * 递归清理目录下的 __pycache__ 和 .pyc 文件。
 * 避免工具类名变更后缓存不一致，同时减小打包体积。
 * 跳过 .venv 和 node_modules，避免清理第三方包缓存（耗时且无必要）。
 */
function cleanPycache(dirPath) {
  if (!fs.existsSync(dirPath)) {
    return;
  }

  const skipDirs = new Set([".venv", "node_modules", ".git"]);
  const entries = fs.readdirSync(dirPath, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      if (skipDirs.has(entry.name)) {
        continue;
      }
      if (entry.name === "__pycache__") {
        console.log(`[aiasys-desktop] 清理: ${fullPath}`);
        fs.rmSync(fullPath, { recursive: true, force: true });
      } else {
        cleanPycache(fullPath);
      }
    } else if (entry.name.endsWith(".pyc") || entry.name.endsWith(".pyo")) {
      console.log(`[aiasys-desktop] 清理: ${fullPath}`);
      fs.unlinkSync(fullPath);
    }
  }
}

function prepareWebRuntime() {
  const webDistRoot = path.join(webRoot, "dist");

  ensureExists(webDistRoot, "web dist");

  copyPath(webDistRoot, path.join(webStageRoot, "dist"));

  const scriptsCommittedRoot = path.join(webRoot, "scripts", "committed");
  copyPathIfExists(scriptsCommittedRoot, path.join(webStageRoot, "scripts", "committed"));
}

function readPyvenvHome(pyvenvPath) {
  try {
    const content = fs.readFileSync(pyvenvPath, "utf-8");
    const match = content.match(/^home\s*=\s*(.+)$/m);
    if (match) {
      return match[1].trim();
    }
  } catch {
    // ignore
  }
  return null;
}

function prepareBackendRuntime() {
  const requiredEntries = [
    ".venv",
    "app",
    "vendor",
    "skills",
    "agent_runtime_helpers",
    "templates",
    "capability_sources",
    "pyproject.toml",
    "__init__.py",
  ];

  const optionalEntries = [
    "config.json",
    "config.example.json",
    "scripts",
    "fonts",
    "docs",
  ];

  for (const entry of requiredEntries) {
    copyPath(path.join(backendRoot, entry), path.join(backendStageRoot, entry));
  }

  for (const entry of optionalEntries) {
    copyPathIfExists(path.join(backendRoot, entry), path.join(backendStageRoot, entry));
  }

  // config.json 不在仓库中时，用 config.example.json 兜底
  const stagedConfigPath = path.join(backendStageRoot, "config.json");
  const stagedExamplePath = path.join(backendStageRoot, "config.example.json");
  if (!fs.existsSync(stagedConfigPath) && fs.existsSync(stagedExamplePath)) {
    fs.copyFileSync(stagedExamplePath, stagedConfigPath);
    console.warn("[aiasys-desktop] config.json 不存在，已从 config.example.json 复制");
  }

  fs.mkdirSync(path.join(backendStageRoot, "data", "workspaces"), { recursive: true });
  fs.mkdirSync(path.join(backendStageRoot, "logs"), { recursive: true });
  fs.mkdirSync(path.join(backendStageRoot, "workspaces"), { recursive: true });

  // Windows: 将 pyvenv.cfg 指向的完整 Python 运行时复制到嵌入目录
  // 避免目标机器上没有系统 Python 时 venv 无法启动
  if (process.platform === "win32") {
    const pyvenvPath = path.join(backendStageRoot, ".venv", "pyvenv.cfg");
    const homePath = readPyvenvHome(pyvenvPath);
    if (homePath && fs.existsSync(homePath)) {
      const embedPythonRoot = path.join(backendStageRoot, ".venv", "python");
      if (!fs.existsSync(embedPythonRoot)) {
        console.log(`[aiasys-desktop] 嵌入完整 Python 运行时: ${homePath} -> ${embedPythonRoot}`);
        fs.cpSync(homePath, embedPythonRoot, { recursive: true, preserveTimestamps: true });
        // 删除 python3.exe shim，避免 Windows 上 7-Zip 打包时报 "directory name is invalid"
        const python3Shim = path.join(embedPythonRoot, "python3.exe");
        if (fs.existsSync(python3Shim)) {
          fs.unlinkSync(python3Shim);
          console.log("[aiasys-desktop] 移除 python3.exe shim");
        }
      }
    } else {
      console.warn("[aiasys-desktop] 未找到 pyvenv.cfg home 路径，嵌入 Python 可能不完整");
    }
  }
}

function main() {
  console.log("[aiasys-desktop] 准备运行时...");

  // 清理 Python 缓存（在复制前清理源目录，避免复制到 staging）
  console.log("[aiasys-desktop] 清理 __pycache__ 和 .pyc 文件...");
  cleanPycache(backendRoot);

  resetDir(runtimeRoot);
  prepareWebRuntime();
  prepareBackendRuntime();

  // 再次清理 staging 目录中可能残留的缓存（防御性）
  cleanPycache(backendStageRoot);

  console.log(`[aiasys-desktop] runtime prepared at ${runtimeRoot}`);
}

main();
