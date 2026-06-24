const fs = require("fs");
const path = require("path");

/**
 * electron-builder afterPack 钩子。
 *
 * 针对 Linux AppImage 在 AppRun 脚本顶部注入 ELECTRON_DISABLE_SANDBOX=1，
 * 以兼容 Ubuntu 23.10+ 默认启用的 AppArmor unprivileged user namespace 限制。
 * Windows/macOS 产物不受影响。
 */
module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== "linux") {
    return;
  }

  const appRunPath = path.join(context.appOutDir, "AppRun");
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
