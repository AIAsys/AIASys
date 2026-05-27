import { chromium } from "playwright";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
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

    // 2. 点击第一个工作区
    const workspaceButton = page.locator('button:has-text("新任务测试")').first();
    const count = await workspaceButton.count();
    if (count > 0) {
      await workspaceButton.click();
      await page.waitForTimeout(1500);
    }

    // 3. 截图：按键前状态
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "terminal-tab-before.png"),
      fullPage: false,
    });
    console.log("[OK] Screenshot before: terminal-tab-before.png");

    // 4. 在页面中注入监听器，跟踪所有 keydown 事件和 requestSidebarTab 调用
    await page.evaluate(() => {
      window.__keydownLog = [];
      window.__requestSidebarTabCalls = [];
      window.addEventListener("keydown", (e) => {
        window.__keydownLog.push({ key: e.key, code: e.code, ctrlKey: e.ctrlKey });
      }, { capture: true });
    });

    // 5. 模拟 Ctrl+` 按键 (Playwright Backquote)
    await page.keyboard.press("Control+Backquote");
    await page.waitForTimeout(1000);

    // 6. 读取事件日志
    const log1 = await page.evaluate(() => window.__keydownLog);
    console.log("[INFO] Keydown events from Playwright:", JSON.stringify(log1));

    // 7. 截图：Playwright 按键后
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "terminal-tab-after-playwright.png"),
      fullPage: false,
    });
    console.log("[OK] Screenshot after Playwright keypress: terminal-tab-after-playwright.png");

    // 8. 清除日志，然后直接通过 JS 触发 KeyboardEvent(key="`", code="Backquote")
    await page.evaluate(() => {
      window.__keydownLog = [];
    });

    const jsEventResult = await page.evaluate(() => {
      return new Promise((resolve) => {
        let captured = false;
        const handler = (e) => {
          if (e.ctrlKey && e.key === "`") {
            captured = true;
          }
        };
        window.addEventListener("keydown", handler, { once: true });

        const evt = new KeyboardEvent("keydown", {
          key: "`",
          code: "Backquote",
          ctrlKey: true,
          bubbles: true,
        });
        document.dispatchEvent(evt);

        setTimeout(() => {
          window.removeEventListener("keydown", handler);
          resolve({ captured, log: window.__keydownLog });
        }, 500);
      });
    });
    console.log("[INFO] JS event result:", JSON.stringify(jsEventResult));

    // 9. 截图：JS 事件触发后
    await page.waitForTimeout(500);
    await page.screenshot({
      path: path.join(ARTIFACTS_DIR, "terminal-tab-after-js.png"),
      fullPage: false,
    });
    console.log("[OK] Screenshot after JS event: terminal-tab-after-js.png");

    // 10. 检查 pane tree tab 数量
    const tabs = await page.locator("[role='tablist'] [role='tab']").count();
    console.log(`[INFO] Tab count in pane tree: ${tabs}`);

    // 11. 通过直接调用 requestSidebarTab 验证 SidebarProvider 是否正确响应
    // 先找到 MainContent 组件中的 requestSidebarTab（无法直接访问），但可以模拟 activeTabRequest
    // 更简单：检查页面上是否有 terminal 相关的元素被激活
    const terminalElements = await page.locator("text=终端").count();
    console.log(`[INFO] Elements containing '终端': ${terminalElements}`);

    console.log("\n=== Verification Summary ===");
    console.log("Screenshots saved to:", ARTIFACTS_DIR);
  } catch (err) {
    console.error("[ERROR]", err);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
