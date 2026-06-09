import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/chat-deep-audit";

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

test.use({ viewport: { width: 1440, height: 900 } });

const screenshot = async (page: any, name: string) => {
  await page.screenshot({
    path: path.join(OUT_DIR, name),
    fullPage: false,
  });
  console.log(`[screenshot] ${name}`);
};

test.describe("Chat Deep Audit", () => {
  test("history load + streaming + multi-turn", async ({ page }) => {
    // 1. 打开有历史数据的工作区
    await page.goto(
      "http://localhost:13000/workspace?workspace_id=24dccdcb27b2&session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db",
      { waitUntil: "domcontentloaded" },
    );
    await page.waitForTimeout(4000);
    await screenshot(page, "01-history-loaded.png");

    // 2. 检查历史消息结构：用户消息、AI 消息、turn 分隔线、think 块
    const turnDividers = await page.locator('text=/Turn \\d+/i').all();
    console.log(`Turn dividers found: ${turnDividers.length}`);

    const thinkBlocks = await page.locator('text=/思考过程|思考/i').all();
    console.log(`Think blocks found: ${thinkBlocks.length}`);

    const toolButtons = await page.locator('button:has-text("点击查看详情")').all();
    console.log(`Tool buttons found: ${toolButtons.length}`);

    // 3. 滚动到顶部看完整历史
    const chatScroll = page.locator('[class*="messages"], [class*="chat"], [class*="overflow-y"]').first();
    if (await chatScroll.isVisible().catch(() => false)) {
      await chatScroll.evaluate((el) => el.scrollTo({ top: 0 }));
      await page.waitForTimeout(1000);
      await screenshot(page, "02-history-top.png");
    }

    // 4. 发送第一条消息，测试流式输出
    const chatInput = page.locator("textarea").first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("请写一个 Python 函数计算斐波那契数列，并解释思路");
      await chatInput.press("Enter");
      await page.waitForTimeout(2000);
      await screenshot(page, "03-streaming-start.png");

      // 等待流式过程中
      await page.waitForTimeout(6000);
      await screenshot(page, "04-streaming-mid.png");

      // 等待完成
      await page.waitForTimeout(10000);
      await screenshot(page, "05-streaming-done.png");
    }

    // 5. 发送第二条消息，测试多 turn 和 turn 分隔线
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("再用递归方式写一个");
      await chatInput.press("Enter");
      await page.waitForTimeout(2000);
      await screenshot(page, "06-second-send.png");

      await page.waitForTimeout(15000);
      await screenshot(page, "07-second-done.png");
    }

    // 6. 滚动查看 turn 分隔线是否正确
    if (await chatScroll.isVisible().catch(() => false)) {
      await chatScroll.evaluate((el) => el.scrollTo({ top: 0 }));
      await page.waitForTimeout(1000);
      await screenshot(page, "08-multi-turn-top.png");

      await chatScroll.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
      await page.waitForTimeout(1000);
      await screenshot(page, "09-multi-turn-bottom.png");
    }

    // 7. 测试思考过程的展开/折叠
    const thinkToggles = await page.locator('text=/思考过程|点击展开|点击折叠/i').all();
    console.log(`Think toggles: ${thinkToggles.length}`);
    for (let i = 0; i < Math.min(thinkToggles.length, 3); i++) {
      const t = thinkToggles[i];
      if (await t.isVisible().catch(() => false)) {
        await t.click();
        await page.waitForTimeout(800);
        await screenshot(page, `10-think-toggle-${i}.png`);
      }
    }

    console.log("Deep audit test completed");
  });

  test("tool call render check", async ({ page }) => {
    await page.goto(
      "http://localhost:13000/workspace?workspace_id=24dccdcb27b2&session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db",
      { waitUntil: "domcontentloaded" },
    );
    await page.waitForTimeout(4000);

    const chatInput = page.locator("textarea").first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("请执行 ls -la 命令查看当前目录");
      await chatInput.press("Enter");
      await page.waitForTimeout(3000);
      await screenshot(page, "20-tool-start.png");

      await page.waitForTimeout(10000);
      await screenshot(page, "21-tool-done.png");

      // 点击 tool 按钮查看详情
      const toolBtn = page.locator('button:has-text("点击查看详情")').first();
      if (await toolBtn.isVisible().catch(() => false)) {
        await toolBtn.click();
        await page.waitForTimeout(1000);
        await screenshot(page, "22-tool-detail.png");
      }
    }
  });
});
