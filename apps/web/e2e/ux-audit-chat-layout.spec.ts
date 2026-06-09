import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-chat-layout";

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

test.use({
  video: "on",
  viewport: { width: 1440, height: 900 },
});

test.describe("Chat Content Layout Audit", () => {
  test("record and inspect chat message layout", async ({ page }, testInfo) => {
    let step = 100;
    const screenshot = async (name: string, opts?: { fullPage?: boolean }) => {
      step++;
      const fileName = `${step}-${name}.png`;
      await page.screenshot({
        path: path.join(OUT_DIR, fileName),
        fullPage: opts?.fullPage ?? false,
      });
      console.log(`[${step}] ${name}`);
    };

    // 进入指定工作区会话
    await page.goto(
      "http://localhost:13000/workspace?workspace_id=24dccdcb27b2&session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db",
      { waitUntil: "domcontentloaded" }
    );
    await page.waitForTimeout(4000);
    await screenshot("initial-chat-state");

    // 滚动对话区域到底部
    const chatScroll = page.locator('[class*="messages"], [class*="chat"], [class*="overflow-y"]').first();
    if (await chatScroll.isVisible().catch(() => false)) {
      await chatScroll.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
      await page.waitForTimeout(1000);
      await screenshot("chat-scrolled-bottom");
    }

    // 尝试找到所有 AI 回复消息气泡，点击展开思考过程（如果有）
    const thoughtBlocks = await page.locator('[class*="thought"], button:has-text("思考")').all();
    console.log(`Found ${thoughtBlocks.length} thought blocks`);

    for (let i = 0; i < Math.min(thoughtBlocks.length, 5); i++) {
      const tb = thoughtBlocks[i];
      const isVisible = await tb.isVisible().catch(() => false);
      if (!isVisible) continue;
      await tb.click();
      await page.waitForTimeout(800);
      await screenshot(`thought-expanded-${i}`);
    }

    // 尝试发送一条新消息，观察 AI 回复的排版
    const chatInput = page.locator('textarea').first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("请写一个 Python 函数，包含代码块、列表和加粗文字，测试下 Markdown 渲染效果");
      await page.waitForTimeout(500);
      await screenshot("input-filled");

      await chatInput.press("Enter");
      await page.waitForTimeout(2000);
      await screenshot("after-send");

      // 等待 AI 回复过程中
      await page.waitForTimeout(5000);
      await screenshot("during-response");

      // 再等待回复完成
      await page.waitForTimeout(8000);
      await screenshot("after-response");

      // 滚动到底部
      if (await chatScroll.isVisible().catch(() => false)) {
        await chatScroll.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
        await page.waitForTimeout(1000);
        await screenshot("final-scrolled-bottom");
      }

      // 向上滚动查看完整 AI 回复内容（特别是代码块顶部）
      if (await chatScroll.isVisible().catch(() => false)) {
        await chatScroll.evaluate((el) => el.scrollTo({ top: 0 }));
        await page.waitForTimeout(1000);
        await screenshot("scrolled-top");
      }
    }

    // 复制 video
    let videoPath = testInfo.video?.path;
    if (!videoPath && page.video()) {
      videoPath = await page.video()!.path();
    }
    if (videoPath) {
      const dest = path.join(OUT_DIR, "ux-audit-chat-layout.webm");
      fs.copyFileSync(videoPath, dest);
      console.log("Video saved to:", dest);
    } else {
      console.log("No video path available");
    }

    console.log(`Total screenshots: ${step - 100}`);
  });
});
