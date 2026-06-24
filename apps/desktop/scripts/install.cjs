#!/usr/bin/env node
/**
 * AIASys 跨平台安装辅助脚本
 *
 * 让 AI 和人都能安全、可预期地安装/升级 AIASys。
 * 使用绿色版 zip 包（Windows / macOS / Linux 均支持），避免安装程序在自动化环境中卡死。
 *
 * 用法：
 *   node scripts/install.cjs <archivePath> [targetDir]
 *
 * 默认安装位置：
 *   - Windows: C:\Users\<user>\AppData\Local\Programs\AIASys
 *   - macOS:   /Applications/AIASys.app
 *   - Linux:   ~/.local/share/AIASys
 *
 * 行为：
 *   1. 自动检测当前平台
 *   2. 检测并安全终止运行中的 AIASys 进程（按 PID）
 *   3. 备份旧版本
 *   4. 解压绿色版包到目标位置
 *   5. 创建系统快捷方式 / .desktop / 应用图标
 *   6. 验证关键文件
 *   7. 输出结构化日志，便于 AI 读取
 */

const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawnSync } = require("child_process");

const PLATFORM = process.platform;

function log(level, message) {
  const timestamp = new Date().toISOString();
  console.log(`[${timestamp}] [${level}] ${message}`);
}

function fail(message, code = 1) {
  log("ERROR", message);
  process.exit(code);
}

function exec(cmd, args, options = {}) {
  const result = spawnSync(cmd, args, {
    encoding: "utf-8",
    stdio: "pipe",
    windowsHide: true,
    ...options,
  });
  return result;
}

function sleepMs(ms) {
  try {
    spawnSync(process.execPath, ["-e", `setTimeout(() => {}, ${ms})`], { timeout: ms + 100 });
  } catch {
    // ignore
  }
}

// ---------------------------------------------------------------------------
// 公共：进程管理
// ---------------------------------------------------------------------------

function getProcessPidsByName(name) {
  if (PLATFORM === "win32") {
    const result = exec("tasklist", ["/FI", `IMAGENAME eq ${name}`, "/FO", "CSV", "/NH"]);
    if (result.status !== 0 || !result.stdout) return [];
    return result.stdout
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .map((line) => {
        const match = line.match(new RegExp(`^"${name}"\\s*,\\s*"(\\d+)"`, "i"));
        return match ? parseInt(match[1], 10) : null;
      })
      .filter((pid) => pid !== null);
  }

  // Unix: pgrep 优先，fallback 到 ps
  let result = exec("pgrep", ["-f", name]);
  if (result.status === 0 && result.stdout) {
    return result.stdout
      .split(/\r?\n/)
      .map((line) => parseInt(line.trim(), 10))
      .filter((pid) => !Number.isNaN(pid));
  }

  result = exec("ps", ["aux"]);
  if (result.status !== 0 || !result.stdout) return [];
  return result.stdout
    .split(/\r?\n/)
    .map((line) => {
      const parts = line.trim().split(/\s+/);
      if (parts.length < 11) return null;
      const cmdLine = parts.slice(10).join(" ");
      if (cmdLine.includes(name)) return parseInt(parts[1], 10);
      return null;
    })
    .filter((pid) => pid !== null);
}

function killAiasysProcesses() {
  const names = PLATFORM === "win32" ? ["AIASys.exe"] : ["AIASys", "aiasys-desktop"];
  const pids = names.flatMap(getProcessPidsByName);
  const uniquePids = [...new Set(pids)];

  if (uniquePids.length === 0) {
    log("INFO", "没有运行中的 AIASys 进程");
    return;
  }

  log("INFO", `发现运行中的 AIASys 进程: ${uniquePids.join(", ")}，正在终止...`);

  if (PLATFORM === "win32") {
    const result = exec("taskkill", ["/F", ...uniquePids.flatMap((pid) => ["/PID", String(pid)])]);
    if (result.status !== 0) {
      log("WARN", `终止进程时出现问题: ${result.stderr || result.error || "未知错误"}`);
    }
  } else {
    for (const pid of uniquePids) {
      const result = exec("kill", ["-9", String(pid)]);
      if (result.status !== 0) {
        log("WARN", `终止 PID ${pid} 失败: ${result.stderr || result.error || "未知错误"}`);
      }
    }
  }

  // 等待进程彻底退出
  for (let i = 0; i < 20; i++) {
    const stillRunning = names.flatMap(getProcessPidsByName);
    if (stillRunning.length === 0) break;
    sleepMs(200);
  }
  log("INFO", "已终止运行中的 AIASys 进程");
}

// ---------------------------------------------------------------------------
// 公共：备份与解压
// ---------------------------------------------------------------------------

function backupOldVersion(targetPath) {
  if (!fs.existsSync(targetPath)) return null;
  const backupPath = `${targetPath}.bak.${Date.now()}`;
  try {
    fs.renameSync(targetPath, backupPath);
    log("INFO", `已备份旧版本到: ${backupPath}`);
    return backupPath;
  } catch (err) {
    fail(`备份旧版本失败: ${err.message}。可能是目录被占用，请关闭 AIASys 后重试。`);
  }
}

function extractArchive(archivePath, targetDir) {
  log("INFO", `解压 ${archivePath} 到 ${targetDir}...`);
  fs.mkdirSync(targetDir, { recursive: true });

  const ext = path.extname(archivePath).toLowerCase();
  const isZip = ext === ".zip";

  if (PLATFORM === "win32") {
    // Windows: PowerShell Expand-Archive
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "aiasys-install-"));
    const psScript = path.join(tmpDir, "extract.ps1");
    const scriptContent =
      `param([string]$ZipPath, [string]$DestPath)\n` +
      `Expand-Archive -Path $ZipPath -DestinationPath $DestPath -Force -ErrorAction Stop\n`;
    fs.writeFileSync(psScript, scriptContent, "utf-8");

    const result = exec(
      "powershell",
      ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", psScript, "-ZipPath", archivePath, "-DestPath", targetDir]
    );

    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // ignore
    }

    if (result.status !== 0) {
      fail(`解压失败: ${result.stderr || result.error || "未知错误"}`);
    }
  } else {
    // macOS / Linux: 优先用 unzip，fallback 到 tar/python
    let result;
    if (isZip) {
      result = exec("unzip", ["-q", "-o", archivePath, "-d", targetDir]);
      if (result.status !== 0) {
        if (result.error && result.error.code === "ENOENT") {
          fail("未找到 unzip 命令，请先安装 unzip (macOS: 通常已内置; Linux: apt/yum install unzip)");
        }
        fail(`解压失败: ${result.stderr || result.error || "未知错误"}`);
      }
    } else {
      // tar.gz
      fs.mkdirSync(targetDir, { recursive: true });
      result = exec("tar", ["-xzf", archivePath, "-C", targetDir]);
      if (result.status !== 0) {
        fail(`解压失败: ${result.stderr || result.error || "未知错误"}`);
      }
    }
  }

  log("INFO", "解压完成");
}

// ---------------------------------------------------------------------------
// Windows
// ---------------------------------------------------------------------------

function copyDirRecursive(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  const entries = fs.readdirSync(src);
  for (const entry of entries) {
    const srcPath = path.join(src, entry);
    const destPath = path.join(dest, entry);
    const stat = fs.statSync(srcPath);
    if (stat.isDirectory()) {
      copyDirRecursive(srcPath, destPath);
    } else {
      fs.copyFileSync(srcPath, destPath);
    }
  }
}

function installWindows(archivePath, targetDir) {
  killAiasysProcesses();

  // 为避免 zip 内含 wrapper 目录导致安装验证失败，先解压到临时目录，
  // 再根据实际内容决定是直接把 wrapper 内容搬到目标目录，还是整体搬到目标目录。
  const tmpRoot = fs.mkdtempSync(path.join(os.tmpdir(), "aiasys-install-"));
  const tmpTarget = path.join(tmpRoot, "final");
  fs.mkdirSync(tmpTarget, { recursive: true });

  backupOldVersion(targetDir);
  extractArchive(archivePath, tmpTarget);

  const entries = fs.readdirSync(tmpTarget);
  if (entries.length === 1) {
    const only = path.join(tmpTarget, entries[0]);
    if (fs.existsSync(only) && fs.statSync(only).isDirectory()) {
      const nestedExe = path.join(only, "AIASys.exe");
      if (fs.existsSync(nestedExe)) {
        log("INFO", `检测到 zip 内含 wrapper 目录 ${entries[0]}，直接将其作为安装根目录`);
        fs.mkdirSync(targetDir, { recursive: true });
        copyDirRecursive(only, targetDir);
        try {
          fs.rmSync(tmpRoot, { recursive: true, force: true });
        } catch {
          // ignore cleanup error
        }

        // 创建快捷方式
        const exePath = path.join(targetDir, "AIASys.exe");
        if (!fs.existsSync(exePath)) {
          log("WARN", `未找到 ${exePath}，跳过创建快捷方式`);
        } else {
          const desktopPath = path.join(os.homedir(), "Desktop");
          const startMenuPath = path.join(
            os.homedir(),
            "AppData",
            "Roaming",
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs"
          );

          for (const dir of [desktopPath, startMenuPath]) {
            fs.mkdirSync(dir, { recursive: true });
            const shortcutPath = path.join(dir, "AIASys.lnk");
            const psCommand =
              "$WshShell = New-Object -ComObject WScript.Shell; " +
              `$Shortcut = $WshShell.CreateShortcut('${shortcutPath.replace(/'/g, "''")}'); ` +
              `$Shortcut.TargetPath = '${exePath.replace(/'/g, "''")}'; ` +
              `$Shortcut.WorkingDirectory = '${targetDir.replace(/'/g, "''")}'; ` +
              "$Shortcut.Save()";
            const result = exec("powershell", ["-NoProfile", "-Command", psCommand]);
            if (result.status !== 0) {
              log("WARN", `创建快捷方式失败 ${shortcutPath}: ${result.stderr || result.error}`);
            } else {
              log("INFO", `已创建快捷方式: ${shortcutPath}`);
            }
          }
        }

        // 验证
        for (const rel of ["AIASys.exe", "resources", "resources/app.asar"]) {
          if (!fs.existsSync(path.join(targetDir, rel))) {
            fail(`安装验证失败: 缺少 ${rel}`);
          }
        }
        log("INFO", `安装验证通过: ${targetDir}`);
        log("INFO", `启动方式: 双击桌面快捷方式 "AIASys" 或运行 ${exePath}`);
        return;
      }
    }
  }

  // 没有 wrapper 目录，把整个临时目录搬到目标目录
  copyDirRecursive(tmpTarget, targetDir);
  try {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  } catch {
    // ignore cleanup error
  }

  // 创建快捷方式
  const exePath = path.join(targetDir, "AIASys.exe");
  if (!fs.existsSync(exePath)) {
    log("WARN", `未找到 ${exePath}，跳过创建快捷方式`);
  } else {
    const desktopPath = path.join(os.homedir(), "Desktop");
    const startMenuPath = path.join(
      os.homedir(),
      "AppData",
      "Roaming",
      "Microsoft",
      "Windows",
      "Start Menu",
      "Programs"
    );

    for (const dir of [desktopPath, startMenuPath]) {
      fs.mkdirSync(dir, { recursive: true });
      const shortcutPath = path.join(dir, "AIASys.lnk");
      const psCommand =
        "$WshShell = New-Object -ComObject WScript.Shell; " +
        `$Shortcut = $WshShell.CreateShortcut('${shortcutPath.replace(/'/g, "''")}'); ` +
        `$Shortcut.TargetPath = '${exePath.replace(/'/g, "''")}'; ` +
        `$Shortcut.WorkingDirectory = '${targetDir.replace(/'/g, "''")}'; ` +
        "$Shortcut.Save()";
      const result = exec("powershell", ["-NoProfile", "-Command", psCommand]);
      if (result.status !== 0) {
        log("WARN", `创建快捷方式失败 ${shortcutPath}: ${result.stderr || result.error}`);
      } else {
        log("INFO", `已创建快捷方式: ${shortcutPath}`);
      }
    }
  }

  // 验证
  for (const rel of ["AIASys.exe", "resources", "resources/app.asar"]) {
    if (!fs.existsSync(path.join(targetDir, rel))) {
      fail(`安装验证失败: 缺少 ${rel}`);
    }
  }
  log("INFO", `安装验证通过: ${targetDir}`);
  log("INFO", `启动方式: 双击桌面快捷方式 "AIASys" 或运行 ${exePath}`);
}

// ---------------------------------------------------------------------------
// macOS
// ---------------------------------------------------------------------------

function installMacos(archivePath, targetDir) {
  killAiasysProcesses();

  // macOS 目标是一个 app bundle，先把 zip 解压到临时目录
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "aiasys-install-"));
  try {
    extractArchive(archivePath, tmpDir);

    // 查找 AIASys.app
    const entries = fs.readdirSync(tmpDir);
    const appName = entries.find((e) => e.endsWith(".app"));
    if (!appName) {
      fail(`解压后未找到 .app  bundle，内容: ${entries.join(", ")}`);
    }
    const sourceApp = path.join(tmpDir, appName);

    backupOldVersion(targetDir);

    // 复制到 /Applications
    fs.mkdirSync(path.dirname(targetDir), { recursive: true });
    const result = exec("cp", ["-R", sourceApp, targetDir]);
    if (result.status !== 0) {
      fail(`复制到 ${targetDir} 失败: ${result.stderr || result.error || "未知错误"}`);
    }
  } finally {
    try {
      fs.rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  }

  // 验证
  const exePath = path.join(targetDir, "Contents", "MacOS", "AIASys");
  if (!fs.existsSync(exePath)) {
    fail(`安装验证失败: 未找到可执行文件 ${exePath}`);
  }
  if (!fs.existsSync(path.join(targetDir, "Contents", "Resources", "app.asar"))) {
    fail("安装验证失败: 未找到 app.asar");
  }
  log("INFO", `安装验证通过: ${targetDir}`);
  log("INFO", `启动方式: 在 Launchpad / Applications 中打开 AIASys，或运行: open "${targetDir}"`);
}

// ---------------------------------------------------------------------------
// Linux
// ---------------------------------------------------------------------------

function installLinux(archivePath, targetDir) {
  killAiasysProcesses();
  backupOldVersion(targetDir);
  extractArchive(archivePath, targetDir);

  // Linux 绿色版解压后通常是一个目录，里面包含可执行文件
  // electron-builder 对 Linux 可执行文件的命名可能来自 productName 或 package.json name
  const possibleExeNames = ["AIASys", "aiasys-desktop", "aiasys"];
  let exePath = null;

  for (const name of possibleExeNames) {
    const candidate = path.join(targetDir, name);
    if (fs.existsSync(candidate)) {
      exePath = candidate;
      break;
    }
  }

  if (!exePath) {
    // electron-builder dir/zip 可能多一层目录名如 AIASys-linux-x64
    const entries = fs.readdirSync(targetDir);
    for (const name of possibleExeNames) {
      const subDir = entries.find((e) => {
        const p = path.join(targetDir, e);
        return fs.statSync(p).isDirectory() && fs.existsSync(path.join(p, name));
      });
      if (subDir) {
        exePath = path.join(targetDir, subDir, name);
        break;
      }
    }
  }

  if (!exePath || !fs.existsSync(exePath)) {
    fail(`安装验证失败: 未找到可执行文件，目标目录内容: ${fs.readdirSync(targetDir).join(", ")}`);
  }
  fs.chmodSync(exePath, 0o755);

  // 创建 .desktop
  const applicationsDir = path.join(os.homedir(), ".local", "share", "applications");
  fs.mkdirSync(applicationsDir, { recursive: true });
  const desktopEntryPath = path.join(applicationsDir, "aiasys.desktop");
  const iconCandidates = [
    path.join(path.dirname(exePath), "resources", "app", "build", "icon.png"),
    path.join(path.dirname(exePath), "build", "icon.png"),
  ];
  const iconPath = iconCandidates.find((p) => fs.existsSync(p)) || null;
  const desktopEntryLines = [
    "[Desktop Entry]",
    "Name=AIASys",
    "Comment=AI Agent System",
    `Exec=env ELECTRON_DISABLE_SANDBOX=1 ${exePath} --no-sandbox`,
    "Type=Application",
    "Terminal=false",
  ];
  if (iconPath) desktopEntryLines.push(`Icon=${iconPath}`);
  desktopEntryLines.push("Categories=Development;", "");
  fs.writeFileSync(desktopEntryPath, desktopEntryLines.join("\n"), "utf-8");
  fs.chmodSync(desktopEntryPath, 0o755);
  log("INFO", `已创建 .desktop: ${desktopEntryPath}`);

  // 验证
  if (!fs.existsSync(path.join(path.dirname(exePath), "resources", "app.asar"))) {
    fail("安装验证失败: 未找到 app.asar");
  }
  log("INFO", `安装验证通过: ${targetDir}`);
  log("INFO", `启动方式: 运行 ${exePath} --no-sandbox`);
}

// ---------------------------------------------------------------------------
// 入口
// ---------------------------------------------------------------------------

function printUsage() {
  console.log(`
用法: node scripts/install.cjs <archivePath> [targetDir]

参数:
  archivePath   AIASys 绿色版包路径
                - Windows: dist/AIASys-x.x.x-win.zip
                - macOS:   dist/AIASys-x.x.x-mac.zip
                - Linux:   dist/AIASys-x.x.x-linux.zip (推荐) 或 .tar.gz
  targetDir     安装目标目录（可选）
                - Windows 默认: %LOCALAPPDATA%\\Programs\\AIASys
                - macOS   默认: /Applications/AIASys.app
                - Linux   默认: ~/.local/share/AIASys

示例:
  node scripts/install.cjs dist/AIASys-0.4.25-win.zip
  node scripts/install.cjs dist/AIASys-0.4.25-mac.zip
  node scripts/install.cjs dist/AIASys-0.4.25-linux.zip

环境变量:
  AIASYS_AGENT_MODE=1     Agent 模式，自动终止进程、跳过确认对话框
`);
}

function main() {
  const args = process.argv.slice(2);
  if (args.length < 1) {
    printUsage();
    process.exit(0);
  }

  const archivePath = path.resolve(args[0]);

  let defaultTarget;
  if (PLATFORM === "win32") {
    defaultTarget = path.join(os.homedir(), "AppData", "Local", "Programs", "AIASys");
  } else if (PLATFORM === "darwin") {
    defaultTarget = path.join("/Applications", "AIASys.app");
  } else {
    defaultTarget = path.join(os.homedir(), ".local", "share", "AIASys");
  }

  const targetDir = args[1] ? path.resolve(args[1]) : defaultTarget;

  log("INFO", `开始安装 AIASys`);
  log("INFO", `平台: ${PLATFORM}`);
  log("INFO", `安装包: ${archivePath}`);
  log("INFO", `目标目录: ${targetDir}`);

  if (!fs.existsSync(archivePath)) {
    fail(`安装包不存在: ${archivePath}`);
  }

  if (PLATFORM === "win32") {
    installWindows(archivePath, targetDir);
  } else if (PLATFORM === "darwin") {
    installMacos(archivePath, targetDir);
  } else if (PLATFORM === "linux") {
    installLinux(archivePath, targetDir);
  } else {
    fail(`不支持的平台: ${PLATFORM}`);
  }

  log("INFO", "AIASys 安装/升级完成");
}

main();
