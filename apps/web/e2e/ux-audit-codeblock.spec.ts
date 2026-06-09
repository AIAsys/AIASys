import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-chat-layout";

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

test.use({
  viewport: { width: 1440, height: 900 },
});

test.describe("Code Block Style Audit", () => {
  test("send message with code block request and verify rendering", async ({ page }) => {
    await page.goto(
      "http://localhost:13000/workspace?workspace_id=24dccdcb27b2&session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db",
      { waitUntil: "networkidle" }
    );
    await page.waitForTimeout(3000);

    // Send a message asking for code
    const chatInput = page.locator('textarea').first();
    await chatInput.fill("请写一个 Python 快速排序函数，用代码块展示");
    await chatInput.press("Enter");
    console.log("Message sent, waiting for response...");

    // Wait for AI response to complete (up to 60 seconds)
    const chatScroll = page.locator('[data-testid="chat-scroll-container"]').first();
    let lastHeight = 0;
    let stableCount = 0;
    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(1000);
      const currentHeight = await chatScroll.evaluate((el) => el.scrollHeight).catch(() => 0);
      if (currentHeight === lastHeight) {
        stableCount++;
        if (stableCount >= 5) break; // stable for 5 seconds
      } else {
        stableCount = 0;
        lastHeight = currentHeight;
      }
      // Also scroll to bottom to see new content
      await chatScroll.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
    }

    // Scroll to top to see the full response
    await chatScroll.evaluate((el) => el.scrollTo({ top: 0 }));
    await page.waitForTimeout(1000);

    // Check for code blocks
    const codeBlockTitles = await page.locator('span.text-white\\/50').all();
    console.log(`Found ${codeBlockTitles.length} code block language labels`);
    for (const t of codeBlockTitles) {
      console.log("  Label:", await t.textContent());
    }

    // Check for macOS dots
    const dots = await page.locator('span.rounded-full.bg-\\[\\#ff5f56\\]').all();
    console.log(`Found ${dots.length} red macOS dots`);

    // Check for copy buttons
    const copyBtns = await page.locator('button:has-text("复制")').all();
    console.log(`Found ${copyBtns.length} copy buttons`);

    await page.screenshot({
      path: path.join(OUT_DIR, "codeblock-audit-top.png"),
      fullPage: false,
    });

    // Scroll to bottom to see the code block
    await chatScroll.evaluate((el) => el.scrollTo({ top: el.scrollHeight }));
    await page.waitForTimeout(1000);

    await page.screenshot({
      path: path.join(OUT_DIR, "codeblock-audit-bottom.png"),
      fullPage: false,
    });
  });
});
