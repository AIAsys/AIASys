import { test, expect } from "@playwright/test";

test.describe("Prose Debug", () => {
  test("check prose computed styles", async ({ page }) => {
    await page.goto(
      "http://localhost:13000/workspace?workspace_id=24dccdcb27b2&session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db",
      { waitUntil: "networkidle" },
    );
    await page.waitForTimeout(3000);

    const proseElements = await page.locator(".prose").all();
    console.log(`Found ${proseElements.length} prose elements`);

    for (let i = 0; i < Math.min(proseElements.length, 3); i++) {
      const el = proseElements[i];
      const styles = await el.evaluate((node) => {
        const computed = window.getComputedStyle(node);
        const firstChild = node.querySelector("p, div, span, h1, h2, h3, h4, h5, h6, li, pre, code, table");
        const childStyle = firstChild ? window.getComputedStyle(firstChild) : null;
        return {
          color: computed.color,
          backgroundColor: computed.backgroundColor,
          height: computed.height,
          width: computed.width,
          opacity: computed.opacity,
          visibility: computed.visibility,
          display: computed.display,
          overflow: computed.overflow,
          overflowY: computed.overflowY,
          fontSize: computed.fontSize,
          lineHeight: computed.lineHeight,
          childTag: firstChild?.tagName,
          childColor: childStyle?.color,
          childDisplay: childStyle?.display,
          childOpacity: childStyle?.opacity,
          childVisibility: childStyle?.visibility,
          innerHTML: node.innerHTML.slice(0, 500),
        };
      });
      console.log(`Prose ${i}:`, JSON.stringify(styles, null, 2));
    }

    // Check if prose CSS variables are defined
    const hasProseStyles = await page.evaluate(() => {
      const sheets = Array.from(document.styleSheets);
      let proseRules = [];
      for (const sheet of sheets) {
        try {
          const rules = Array.from(sheet.cssRules || sheet.rules || []);
          for (const rule of rules) {
            if (rule.cssText?.includes("prose") || rule.selectorText?.includes("prose")) {
              proseRules.push(rule.cssText?.slice(0, 200) || rule.selectorText);
            }
          }
        } catch (e) {
          // cross-origin stylesheet
        }
      }
      return proseRules.slice(0, 10);
    });
    console.log("Prose CSS rules found:", hasProseStyles.length);
    for (const rule of hasProseStyles.slice(0, 5)) {
      console.log("  Rule:", rule);
    }

    await page.screenshot({
      path: "design-draft/archive/artifacts/ux-audit-chat-layout/prose-debug.png",
      fullPage: false,
    });
  });
});
