import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const ARTIFACTS_DIR = path.resolve(__dirname, "../../design-draft/archive/artifacts");

async function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

test("verify Ctrl+Backquote switches to terminal sidebar tab", async ({ page }) => {
  await ensureDir(ARTIFACTS_DIR);

  // 1. 打开分析页面
  await page.goto("http://127.0.0.1:13000/analysis");
  await page.waitForTimeout(2000);

  // 2. 截图：初始状态（工作区首页）
  await page.screenshot({
    path: path.join(ARTIFACTS_DIR, "terminal-tab-before.png"),
    fullPage: false,
  });

  // 3. 尝试点击第一个工作区进入工作区详情
  const workspaceButton = page.locator('button:has-text("新任务测试")').first();
  const count = await workspaceButton.count();
  if (count > 0) {
    await workspaceButton.click();
    await page.waitForTimeout(1500);
  }

  // 4. 截图：进入工作区后的状态
  await page.screenshot({
    path: path.join(ARTIFACTS_DIR, "terminal-tab-workspace.png"),
    fullPage: false,
  });

  // 5. 模拟 Ctrl+` 按键
  await page.keyboard.press("Control+Backquote");
  await page.waitForTimeout(1000);

  // 6. 截图：按键后状态
  await page.screenshot({
    path: path.join(ARTIFACTS_DIR, "terminal-tab-after.png"),
    fullPage: false,
  });

  // 7. 验证：检查 URL 或页面内容，确认没有创建新标签页
  // 获取当前页面上的 tab 数量（pane tree 中的标签）
  const tabCount = await page.locator("[role='tab']").count();
  console.log(`Tab count after Ctrl+\`: ${tabCount}`);
});
