const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

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
      try {
        // 先删除符号链接，避免 copyFileSync 因权限问题无法覆盖只读链接
        fs.unlinkSync(entryPath);
        fs.copyFileSync(realFile, entryPath);
        // 保持可执行权限
        const mode = fs.statSync(realFile).mode;
        fs.chmodSync(entryPath, mode | 0o111);
        console.log(`[aiasys-desktop] 实体化符号链接: ${entry} -> ${realFile}`);
      } catch (error) {
        console.warn(`[aiasys-desktop] 实体化符号链接失败 ${entry}:`, error.message);
      }
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

/**
 * 在嵌入的 Python 目录中查找 framework 路径对应的本地文件。
 */
function resolveEmbedDylibPath(frameworkPath, embedPythonRoot) {
  // 匹配 /Library/Frameworks/Python.framework/Versions/3.12/...
  const match = frameworkPath.match(
    /^\/Library\/Frameworks\/Python\.framework\/Versions\/\d+\/(.+)$/
  );
  if (match) {
    const candidate = path.join(embedPythonRoot, match[1]);
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  // fallback: 如果只依赖根目录的 Python dylib
  if (frameworkPath.endsWith("/Python")) {
    const candidate = path.join(embedPythonRoot, "Python");
    if (fs.existsSync(candidate)) {
      return candidate;
    }
  }
  return null;
}

/**
 * 检查文件是否是 Mach-O 格式（可执行文件、.dylib、.so）。
 */
function isMachOFile(filePath) {
  try {
    const fd = fs.openSync(filePath, "r");
    const magic = Buffer.alloc(4);
    fs.readSync(fd, magic, 0, 4, 0);
    fs.closeSync(fd);
    // Mach-O 64-bit: 0xfeedfacf (小端: cf fa ed fe)
    // Mach-O 32-bit: 0xfeedface (小端: ce fa ed fe)
    // Universal:      0xcafebabe (大端: ca fe ba be)
    return (
      (magic[0] === 0xcf && magic[1] === 0xfa && magic[2] === 0xed && magic[3] === 0xfe) ||
      (magic[0] === 0xce && magic[1] === 0xfa && magic[2] === 0xed && magic[3] === 0xfe) ||
      (magic[0] === 0xca && magic[1] === 0xfe && magic[2] === 0xba && magic[3] === 0xbe)
    );
  } catch {
    return false;
  }
}

/**
 * 修复单个 Mach-O 文件中硬编码的 Python.framework dylib 绝对路径。
 */
function fixSingleDylibPath(filePath, embedPythonRoot) {
  if (!isMachOFile(filePath)) return false;

  const otoolResult = spawnSync("otool", ["-L", filePath], { encoding: "utf-8" });
  if (otoolResult.status !== 0) return false;

  const frameworkPrefix = "/Library/Frameworks/Python.framework/";
  const lines = otoolResult.stdout.split("\n");
  let fixed = false;

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith(frameworkPrefix)) continue;

    const oldPath = trimmed.split(" ")[0];
    const embedTarget = resolveEmbedDylibPath(oldPath, embedPythonRoot);
    if (!embedTarget) continue;

    const relativePath = path.relative(path.dirname(filePath), embedTarget);
    const newPath = "@loader_path/" + relativePath;

    const installResult = spawnSync("install_name_tool", [
      "-change", oldPath, newPath, filePath,
    ]);

    if (installResult.status === 0) {
      console.log(
        `[aiasys-desktop] 修复 dylib: ${path.relative(embedPythonRoot, filePath)} ` +
          `${oldPath} -> ${newPath}`
      );
      fixed = true;
    } else {
      console.warn(
        `[aiasys-desktop] 修复 dylib 失败: ${path.relative(embedPythonRoot, filePath)}`,
        installResult.stderr || ""
      );
    }
  }

  return fixed;
}

/**
 * 递归修复目录下所有 .so/.dylib 文件的 dylib 路径。
 */
function fixDylibPathsInDir(dir, embedPythonRoot, fixedFiles) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const filePath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      fixDylibPathsInDir(filePath, embedPythonRoot, fixedFiles);
    } else if (entry.name.endsWith(".so") || entry.name.endsWith(".dylib")) {
      if (fixSingleDylibPath(filePath, embedPythonRoot)) {
        fixedFiles.push(path.relative(embedPythonRoot, filePath));
      }
    }
  }
}

/**
 * 检测嵌入的 Python 是否是官方 Python（依赖 /Library/Frameworks/ 系统框架）。
 * python-build-standalone 使用 @rpath 相对路径，不会匹配此模式。
 */
function isOfficialMacOSPython(embedPythonRoot) {
  if (process.platform !== "darwin") return false;
  const pythonExe = path.join(embedPythonRoot, "bin", "python3");
  if (!fs.existsSync(pythonExe)) {
    // fallback 检查 python（不带版本号）
    const pythonExe2 = path.join(embedPythonRoot, "bin", "python");
    if (!fs.existsSync(pythonExe2)) return false;
  }
  const target = fs.existsSync(pythonExe) ? pythonExe : path.join(embedPythonRoot, "bin", "python");
  const otoolResult = spawnSync("otool", ["-L", target], { encoding: "utf-8" });
  if (otoolResult.status !== 0) return false;
  return otoolResult.stdout.includes("/Library/Frameworks/Python.framework/");
}

/**
 * macOS 上修复嵌入 Python 中所有 Mach-O 文件的 dylib 加载路径。
 * 官方 Python 的可执行文件硬编码了 /Library/Frameworks/Python.framework/... 的绝对路径，
 * 需要替换为 @loader_path/... 相对路径，使应用能在没有系统框架的目标机器上运行。
 */
function fixMacOSDylibPaths(embedPythonRoot) {
  const hasOtool = spawnSync("which", ["otool"]).status === 0;
  const hasInstallNameTool = spawnSync("which", ["install_name_tool"]).status === 0;
  if (!hasOtool || !hasInstallNameTool) {
    console.warn(
      "[aiasys-desktop] 未找到 otool/install_name_tool，跳过 dylib 路径修复。" +
        "建议安装 Xcode Command Line Tools。"
    );
    return;
  }

  // 检测是否是官方 Python，给出明确警告
  if (isOfficialMacOSPython(embedPythonRoot)) {
    console.warn(
      "[aiasys-desktop] 警告：检测到官方 Python（依赖 /Library/Frameworks/ 系统框架）。" +
        "正在尝试用 install_name_tool 修复 dylib 路径，但最佳方案是使用 " +
        "'uv python install 3.12' 安装 python-build-standalone。"
    );
  }

  const fixedFiles = [];

  // 修复 bin/ 目录中的可执行文件
  const binDir = path.join(embedPythonRoot, "bin");
  if (fs.existsSync(binDir)) {
    for (const entry of fs.readdirSync(binDir)) {
      const filePath = path.join(binDir, entry);
      if (fixSingleDylibPath(filePath, embedPythonRoot)) {
        fixedFiles.push(path.relative(embedPythonRoot, filePath));
      }
    }
  }

  // 递归修复 lib/ 目录中的 .so/.dylib
  const libDir = path.join(embedPythonRoot, "lib");
  if (fs.existsSync(libDir)) {
    fixDylibPathsInDir(libDir, embedPythonRoot, fixedFiles);
  }

  if (fixedFiles.length > 0) {
    console.log(`[aiasys-desktop] 已修复 ${fixedFiles.length} 个文件的 dylib 路径`);
  }
}

function prepareBackendRuntime() {
  // 确保当前平台的 fnm 二进制已下载到 vendor/node/<slug>/
  {
    const downloadScript = path.join(__dirname, "download-fnm-binary.cjs");
    const result = spawnSync("node", [downloadScript], {
      encoding: "utf-8",
      stdio: "pipe",
    });
    if (result.status !== 0) {
      const detail = result.stderr || result.error || `exit ${result.status}`;
      console.error("[aiasys-desktop] 下载 fnm 二进制失败:", detail);
      throw new Error(`下载 fnm 二进制失败: ${detail}`);
    }
    if (result.stdout) {
      process.stdout.write(result.stdout);
    }
  }
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
    "config.toml",
    "config.example.toml",
    "scripts",
    "fonts",
    "docs",
  ];

  for (const entry of requiredEntries) {
    // macOS/Linux 上 .venv 包含大量指向系统 Python 的符号链接，
    // 不解引用会导致目标机器上链接失效。Windows 无需此处理。
    const options =
      entry === ".venv" && process.platform !== "win32"
        ? { dereference: true }
        : {};
    copyPath(path.join(backendRoot, entry), path.join(backendStageRoot, entry), options);
  }

  for (const entry of optionalEntries) {
    copyPathIfExists(path.join(backendRoot, entry), path.join(backendStageRoot, entry));
  }

  // config.toml 不在仓库中时，用 config.example.toml 兜底
  const stagedConfigPath = path.join(backendStageRoot, "config.toml");
  const stagedExamplePath = path.join(backendStageRoot, "config.example.toml");
  if (!fs.existsSync(stagedConfigPath) && fs.existsSync(stagedExamplePath)) {
    fs.copyFileSync(stagedExamplePath, stagedConfigPath);
    console.warn("[aiasys-desktop] config.toml 不存在，已从 config.example.toml 复制");
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
      fs.cpSync(pythonRoot, embedPythonRoot, {
        recursive: true,
        preserveTimestamps: true,
        dereference: true,
      });

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

      // macOS: 修复硬编码的 Python.framework dylib 绝对路径
      if (process.platform === "darwin") {
        fixMacOSDylibPaths(embedPythonRoot);

        // 同时修复 .venv/bin/ 中的可执行文件
        // venv 入口点（.venv/bin/python3）在 dereference: true 复制后可能是系统 Python 副本，
        // dylib 路径未修复。需要确保它能正常启动并找到 pyvenv.cfg。
        const venvBinDir = path.join(backendStageRoot, ".venv", "bin");
        if (fs.existsSync(venvBinDir)) {
          const venvBinFixedFiles = [];
          for (const entry of fs.readdirSync(venvBinDir)) {
            const filePath = path.join(venvBinDir, entry);
            if (fixSingleDylibPath(filePath, embedPythonRoot)) {
              venvBinFixedFiles.push(entry);
            }
          }
          if (venvBinFixedFiles.length > 0) {
            console.log(
              `[aiasys-desktop] 已修复 .venv/bin 中 ${venvBinFixedFiles.length} 个文件的 dylib 路径`
            );
          }
        }

        // 同时修复 .venv/lib 中的原生扩展（如 lib-dynload 中的 .so）
        // 这些文件在 import 时加载，也可能硬编码了 framework 路径
        const venvLibDir = path.join(backendStageRoot, ".venv", "lib");
        if (fs.existsSync(venvLibDir)) {
          const venvFixedFiles = [];
          fixDylibPathsInDir(venvLibDir, embedPythonRoot, venvFixedFiles);
          if (venvFixedFiles.length > 0) {
            console.log(
              `[aiasys-desktop] 已修复 .venv/lib 中 ${venvFixedFiles.length} 个文件的 dylib 路径`
            );
          }
        }
      }
    }
  } else {
    console.warn("[aiasys-desktop] 未找到 pyvenv.cfg home 路径，嵌入 Python 可能不完整");
  }

  // 修复 .venv/bin/ 脚本 shebang 中的构建机绝对路径
  fixVenvBinShebangs(backendStageRoot);

  // 修复 pyvenv.cfg 的 home 路径为嵌入目录
  // AppImage squashfs 只读，运行时无法原地修改，必须在构建时修正
  fixPyvenvCfgHome(backendStageRoot);
}

/**
 * 修复 .venv/bin/ 脚本 shebang 中的构建机绝对路径。
 * dereference: true 复制后，脚本的 shebang 仍指向构建机路径，
 * 在目标机器上会报 "bad interpreter"。替换为 /usr/bin/env python3。
 */
function fixVenvBinShebangs(backendStageRoot) {
  const venvBinDir = path.join(backendStageRoot, ".venv", "bin");
  if (!fs.existsSync(venvBinDir)) {
    return;
  }

  const embedPythonBinDir = path.join(backendStageRoot, ".venv", "python", "bin");
  const embedPython = path.join(embedPythonBinDir, "python3");
  const fallbackShebang = "#!/usr/bin/env python3";

  let fixed = 0;
  for (const entry of fs.readdirSync(venvBinDir)) {
    const filePath = path.join(venvBinDir, entry);
    const stat = fs.statSync(filePath);
    if (!stat.isFile()) {
      continue;
    }

    let content;
    try {
      content = fs.readFileSync(filePath, "utf-8");
    } catch {
      continue;
    }

    const lines = content.split(/\r?\n/);
    const shebang = lines[0];
    if (!shebang || !shebang.startsWith("#!")) {
      continue;
    }

    // 如果 shebang 包含绝对路径（以 / 开头且包含构建机路径特征），修复它
    const needsFix =
      shebang.startsWith("#!/") &&
      (
        // 指向仓库内的 .venv
        shebang.includes("/.venv/") ||
        // 指向系统 Python 路径（如 /Users/xxx/.local/share/uv/python/）
        shebang.includes("/python") ||
        // 指向通用 Python 安装路径
        shebang.includes("/bin/python")
      );

    if (!needsFix) {
      continue;
    }

    // 优先使用嵌入 Python 的绝对路径（如果存在）
    // 否则回退到 /usr/bin/env python3
    const newShebang = fs.existsSync(embedPython) ? `#!${embedPython}` : fallbackShebang;
    lines[0] = newShebang;

    try {
      fs.writeFileSync(filePath, lines.join("\n"), "utf-8");
      fixed++;
    } catch (error) {
      console.warn(`[aiasys-desktop] 修复 shebang 失败 ${entry}: ${error.message}`);
    }
  }

  if (fixed > 0) {
    console.log(`[aiasys-desktop] 已修复 ${fixed} 个 .venv/bin 脚本的 shebang`);
  }
}

/**
 * 修复 pyvenv.cfg 的 home 路径，指向嵌入的 Python 目录。
 * AppImage squashfs 只读，运行时无法原地修改，必须在构建时修正。
 */
function fixPyvenvCfgHome(backendStageRoot) {
  const pyvenvPath = path.join(backendStageRoot, ".venv", "pyvenv.cfg");
  if (!fs.existsSync(pyvenvPath)) {
    return;
  }

  const embedPythonDir = path.join(backendStageRoot, ".venv", "python");
  if (!fs.existsSync(embedPythonDir)) {
    return;
  }

  const content = fs.readFileSync(pyvenvPath, "utf-8");
  const homeMatch = content.match(/^home\s*=\s*(.+)$/m);
  if (!homeMatch) {
    return;
  }

  const currentHome = homeMatch[1].trim();
  if (path.resolve(currentHome) === path.resolve(embedPythonDir)) {
    return; // 已经正确，无需修改
  }

  const newContent = content.replace(/^home\s*=\s*.+$/m, `home = ${embedPythonDir}`);
  fs.writeFileSync(pyvenvPath, newContent, "utf-8");
  console.log(`[aiasys-desktop] 已修正 pyvenv.cfg home 路径: ${embedPythonDir}`);
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
