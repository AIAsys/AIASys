import { test, expect } from "@playwright/test";

test.describe("Code Block Check", () => {
  test("check console errors and code block rendering", async ({ page }) => {
    const errors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        errors.push(msg.text());
        console.log("[CONSOLE ERROR]", msg.text());
      }
    });
    page.on("pageerror", (err) => {
      errors.push(err.message);
      console.log("[PAGE ERROR]", err.message);
    });

    await page.goto(
      "http://localhost:13000/workspace?workspace_id=24dccdcb27b2&session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db&v=" + Date.now(),
      { waitUntil: "networkidle" }
    );
    await page.waitForTimeout(4000);

    // 滚动到顶部查看历史代码块
    const chatScroll = page.locator('[data-testid="chat-scroll-container"]').first();
    if (await chatScroll.isVisible().catch(() => false)) {
      await chatScroll.evaluate((el) => el.scrollTo({ top: 0 }));
      await page.waitForTimeout(1000);
    }

    // 检查是否有代码块
    const codeBlocks = await page.locator('span.uppercase.tracking-wide').all();
    console.log(`Found ${codeBlocks.length} code block labels`);

    // 检查 AI 消息内容容器（AiMessageContent 的外层）
    const aiContents = await page.locator('div.min-w-0.py-2').all();
    console.log(`Found ${aiContents.length} AI content containers`);
    for (let i = 0; i < Math.min(aiContents.length, 3); i++) {
      const style = await aiContents[i].evaluate((el) => {
        const cs = window.getComputedStyle(el);
        return {
          width: el.getBoundingClientRect().width,
          height: el.getBoundingClientRect().height,
          color: cs.color,
          bg: cs.backgroundColor,
          overflow: cs.overflow,
          overflowY: cs.overflowY,
          display: cs.display,
          children: Array.from(el.children).map(c => ({ tag: c.tagName, cls: c.className.slice(0, 50), h: c.getBoundingClientRect().height })),
        };
      });
      console.log(`AI content ${i}: style=${JSON.stringify(style)}`);
    }

    // Deep check: first prose element inner HTML and child styles
    const proseElements = await page.locator(".prose").all();
    console.log(`Found ${proseElements.length} prose elements`);
    for (let i = 0; i < Math.min(proseElements.length, 2); i++) {
      const info = await proseElements[i].evaluate((node) => {
        const cs = window.getComputedStyle(node);
        const firstP = node.querySelector("p");
        const firstPStyle = firstP ? window.getComputedStyle(firstP) : null;
        const firstText = node.textContent?.slice(0, 200) || "";
        return {
          rect: node.getBoundingClientRect(),
          color: cs.color,
          backgroundColor: cs.backgroundColor,
          opacity: cs.opacity,
          visibility: cs.visibility,
          display: cs.display,
          fontSize: cs.fontSize,
          fontFamily: cs.fontFamily,
          lineHeight: cs.lineHeight,
          firstP_rect: firstP ? firstP.getBoundingClientRect() : null,
          firstP_color: firstPStyle?.color,
          firstP_fontSize: firstPStyle?.fontSize,
          firstP_display: firstPStyle?.display,
          firstP_opacity: firstPStyle?.opacity,
          firstP_visibility: firstPStyle?.visibility,
          textContent_preview: firstText,
          innerHTML_preview: node.innerHTML.slice(0, 500),
        };
      });
      console.log(`Prose ${i}:`, JSON.stringify(info, null, 2));
    }

    await page.screenshot({
      path: "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-chat-layout/code-block-check.png",
      fullPage: false,
    });

    if (errors.length > 0) {
      console.log("Total errors:", errors.length);
    }
  });
});
