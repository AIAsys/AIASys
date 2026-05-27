const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const ARTIFACTS_DIR = path.resolve(__dirname, "../../design-draft/archive/artifacts");

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

(async () => {
  ensureDir(ARTIFACTS_DIR);

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();

  try {
    // 1. 打开分析页面
    await page.goto("http://127.0.0.1:13000/analysis", { waitUntil: "networkidle" });
    await page.waitForTimeout(2000);

    // 2. 截图：初始状态
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "terminal-tab-before.png"),
      fullPage: false,
    });
    console.log("[OK] Screenshot before: terminal-tab-before.png");

    // 3. 尝试点击第一个工作区
    const workspaceButton = page.locator('button:has-text("新任务测试")').first();
    const count = await workspaceButton.count();
    if (count > 0) {
      await workspaceButton.click();
      await page.waitForTimeout(1500);
      console.log("[OK] Clicked workspace '新任务测试'");
    } else {
      console.log("[INFO] No workspace '新任务测试' found, staying on workspace home");
    }

    // 4. 截图：进入工作区后的状态
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "terminal-tab-workspace.png"),
      fullPage: false,
    });
    console.log("[OK] Screenshot workspace: terminal-tab-workspace.png");

    // 5. 模拟 Ctrl+` 按键
    await page.keyboard.press("Control+Backquote");
    await page.waitForTimeout(1000);

    // 6. 截图：按键后状态
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "terminal-tab-after.png"),
      fullPage: false,
    });
    console.log("[OK] Screenshot after Ctrl+`: terminal-tab-after.png");

    // 7. 获取页面信息用于验证
    const url = page.url();
    const tabs = await page.locator("[role='tablist'] [role='tab']").count();
    console.log(`[INFO] Current URL: ${url}`);
    console.log(`[INFO] Tab count in pane tree: ${tabs}`);

    console.log("\n=== Verification Summary ===");
    console.log("Screenshots saved to:", ARTIFACTS_DIR);
  } catch (err) {
    console.error("[ERROR]", err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
