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

function resolvePythonRoot(homePath) {
  // Unix 上 pyvenv.cfg 的 home 指向 bin/ 目录，Python 安装根目录是其父目录
  // Windows 上 home 直接指向 Python 安装根目录
  if (homePath && path.basename(homePath) === "bin") {
    return path.dirname(homePath);
  }
  return homePath;
}

/**
 * 递归解析符号链接链，找到最终的实际文件路径。
 * 如果链中任何环节出错，返回 null。
 */
function resolveRealFile(linkPath, visited = new Set()) {
  try {
    if (visited.has(linkPath)) return null; // 循环链接
    visited.add(linkPath);

    const lstat = fs.lstatSync(linkPath);
    if (!lstat.isSymbolicLink()) {
      return fs.existsSync(linkPath) ? linkPath : null;
    }

    const target = fs.readlinkSync(linkPath);
    const resolved = path.isAbsolute(target)
      ? target
      : path.resolve(path.dirname(linkPath), target);
    return resolveRealFile(resolved, visited);
  } catch {
    return null;
  }
}

/**
 * 实体化 bin 目录中指向外部路径的符号链接。
 * 递归解析符号链接链，用最终的实际文件替换链接本身。
 */
function materializeBinSymlinks(embedPythonRoot) {
  const binDir = path.join(embedPythonRoot, "bin");
  if (!fs.existsSync(binDir)) return;

  for (const entry of fs.readdirSync(binDir)) {
    const entryPath = path.join(binDir, entry);
    const realFile = resolveRealFile(entryPath);
    if (realFile && realFile !== entryPath) {
      fs.copyFileSync(realFile, entryPath);
      console.log(`[aiasys-desktop] 实体化符号链接: ${entry} -> ${realFile}`);
    }
  }
}

/**
 * 修复 .venv/bin/python 符号链接，使其指向嵌入的 Python 解释器。
 * 避免 venv 的 python 链接指向构建机的绝对路径，在目标机器上失效。
 */
function fixVenvPythonSymlink(venvRoot, embedPythonRoot) {
  const venvBinDir = path.join(venvRoot, "bin");
  const embedBinDir = path.join(embedPythonRoot, "bin");
  if (!fs.existsSync(venvBinDir) || !fs.existsSync(embedBinDir)) return;

  for (const name of ["python", "python3"]) {
    const linkPath = path.join(venvBinDir, name);
    let isSymlink = false;
    try {
      isSymlink = fs.lstatSync(linkPath).isSymbolicLink();
    } catch {
      continue;
    }
    if (!isSymlink) continue;

    const target = fs.readlinkSync(linkPath);
    // 绝对路径或 broken symlink（指向的文件不存在）都需要修复
    const needsFix = path.isAbsolute(target) || !fs.existsSync(linkPath);
    if (!needsFix) continue;

    const embedPython = path.join(embedBinDir, name);
    if (!fs.existsSync(embedPython)) continue;

    fs.unlinkSync(linkPath);
    const relativeTarget = path.relative(venvBinDir, embedPython);
    fs.symlinkSync(relativeTarget, linkPath);
    console.log(`[aiasys-desktop] 修复 venv 符号链接: ${name} -> ${relativeTarget}`);
  }
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

  // 三端统一嵌入完整 Python 运行时
  // 避免目标机器上没有系统 Python 时 venv 无法启动
  const pyvenvPath = path.join(backendStageRoot, ".venv", "pyvenv.cfg");
  const homePath = readPyvenvHome(pyvenvPath);
  const pythonRoot = resolvePythonRoot(homePath);
  if (pythonRoot && fs.existsSync(pythonRoot)) {
    const embedPythonRoot = path.join(backendStageRoot, ".venv", "python");
    if (!fs.existsSync(embedPythonRoot)) {
      console.log(`[aiasys-desktop] 嵌入完整 Python 运行时: ${pythonRoot} -> ${embedPythonRoot}`);
      fs.cpSync(pythonRoot, embedPythonRoot, { recursive: true, preserveTimestamps: true });

      // 实体化指向外部路径的符号链接，避免在目标机器上失效
      materializeBinSymlinks(embedPythonRoot);

      // 修复 .venv/bin/python 符号链接，使其指向嵌入的 Python
      fixVenvPythonSymlink(path.join(backendStageRoot, ".venv"), embedPythonRoot);

      // Windows: 删除 python3.exe shim，避免 7-Zip 打包时报 "directory name is invalid"
      if (process.platform === "win32") {
        const python3Shim = path.join(embedPythonRoot, "python3.exe");
        if (fs.existsSync(python3Shim)) {
          fs.rmSync(python3Shim, { force: true });
          console.log("[aiasys-desktop] 移除 python3.exe shim");
        }
      }

      // Linux/macOS: 确保 bin 目录下的可执行文件有正确权限
      if (process.platform !== "win32") {
        const binDir = path.join(embedPythonRoot, "bin");
        if (fs.existsSync(binDir)) {
          const entries = fs.readdirSync(binDir);
          let fixed = 0;
          for (const entry of entries) {
            const filePath = path.join(binDir, entry);
            const stat = fs.statSync(filePath);
            if (stat.isFile() && !(stat.mode & 0o111)) {
              fs.chmodSync(filePath, stat.mode | 0o111);
              fixed++;
            }
          }
          if (fixed > 0) {
            console.log(`[aiasys-desktop] 已修复 ${fixed} 个可执行文件权限`);
          }
        }
      }
    }
  } else {
    console.warn("[aiasys-desktop] 未找到 pyvenv.cfg home 路径，嵌入 Python 可能不完整");
  }
}

function pruneDevDependencies(backendStageRoot) {
  const venvRoot = path.join(backendStageRoot, ".venv");
  const sitePackagesPaths = [];

  function findSitePackages(dir) {
    if (!fs.existsSync(dir)) return;
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const fullPath = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        if (entry.name === "site-packages") {
          sitePackagesPaths.push(fullPath);
        } else {
          findSitePackages(fullPath);
        }
      }
    }
  }
  findSitePackages(path.join(venvRoot, "lib"));
  findSitePackages(path.join(venvRoot, "Lib"));

  const devPackages = [
    "pytest", "_pytest", "ruff", "mypy", "mypy_extensions",
    "black", "ipython", "ipykernel", "coverage", "pre_commit",
    "flake8", "pylint", "bandit", "isort", "autopep8",
    "pytest_xdist", "pytest_asyncio", "pytest_cov",
    "sphinx", "sphinx_rtd_theme", "mccabe", "pycodestyle",
    "pyflakes", "typing_extensions",
  ];

  let removed = 0;
  for (const sp of sitePackagesPaths) {
    for (const pkg of devPackages) {
      for (const name of [pkg, pkg.replace(/_/g, "-")]) {
        const pkgPath = path.join(sp, name);
        if (fs.existsSync(pkgPath)) {
          fs.rmSync(pkgPath, { recursive: true, force: true });
          removed++;
        }
      }
    }
  }
  if (removed > 0) {
    console.log(`[aiasys-desktop] 已清理 ${removed} 个开发依赖包`);
  }

  for (const dir of ["docs", "tests"]) {
    const dirPath = path.join(backendStageRoot, dir);
    if (fs.existsSync(dirPath)) {
      fs.rmSync(dirPath, { recursive: true, force: true });
      console.log(`[aiasys-desktop] 清理目录: ${dirPath}`);
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

  // 清理开发依赖和无用目录，减小打包体积
  pruneDevDependencies(backendStageRoot);

  // 再次清理 staging 目录中可能残留的缓存（防御性）
  cleanPycache(backendStageRoot);

  console.log(`[aiasys-desktop] runtime prepared at ${runtimeRoot}`);
}

main();
