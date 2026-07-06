const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

/**
 * Windows 上用 robocopy 把 .dist/backend/.venv 复制到打包产物中。
 *
 * electron-builder 自带的 extraResources 复制对包含数万个文件的 .venv 极慢，
 * 经常在 CI/本地超时。因此先在 package.json 中通过 filter 排除 .venv，
 * 再在这里用多线程 robocopy 完成复制。
 */
function copyVenvWithRobocopy(sourceVenv, targetVenv) {
  fs.rmSync(targetVenv, { recursive: true, force: true });
  fs.mkdirSync(path.dirname(targetVenv), { recursive: true });
  const result = spawnSync(
    "robocopy",
    [
      path.resolve(sourceVenv),
      path.resolve(targetVenv),
      "/E",
      "/MT:8",
      "/NFL",
      "/NDL",
      "/NJH",
      "/NJS",
      "/R:2",
      "/W:1",
    ],
    { encoding: "utf-8", windowsHide: true }
  );
  // robocopy 退出码 0-7 通常表示成功完成（含文件被跳过/差异）
  if (result.status !== null && result.status >= 8) {
    throw new Error(
      `[afterPack] robocopy 复制 .venv 失败: ${sourceVenv} -> ${targetVenv}, exit ${result.status}\n${result.stderr || ""}`
    );
  }
  console.log(`[afterPack] copied .venv to ${targetVenv}`);
}

module.exports = async function afterPack(context) {
  const { electronPlatformName, appOutDir } = context;

  if (electronPlatformName === "win32") {
    const sourceVenv = path.resolve(__dirname, "..", ".dist", "backend", ".venv");
    const targetVenv = path.join(appOutDir, "resources", "backend", ".venv");
    if (fs.existsSync(sourceVenv)) {
      copyVenvWithRobocopy(sourceVenv, targetVenv);
    } else {
      console.warn(`[afterPack] .venv 源目录不存在: ${sourceVenv}`);
    }
  }

  if (electronPlatformName !== "linux") {
    return;
  }

  const appRunPath = path.join(appOutDir, "AppRun");
  if (!fs.existsSync(appRunPath)) {
    return;
  }

  const original = fs.readFileSync(appRunPath, "utf8");
  const marker = "# AIASYS_ELECTRON_DISABLE_SANDBOX";
  if (original.includes(marker)) {
    return;
  }

  const patched = original.replace(
    /^#!/m,
    `#!/bin/bash\n${marker}\nexport ELECTRON_DISABLE_SANDBOX=1\n`,
  );

  if (patched === original) {
    return;
  }

  fs.writeFileSync(appRunPath, patched, { mode: 0o755 });
  console.log(`[afterPack] injected ELECTRON_DISABLE_SANDBOX into ${appRunPath}`);
};
