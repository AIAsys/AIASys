import { test } from "@playwright/test";
import fs from "fs";
import path from "path";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-20250608";

test("probe page structure", async ({ page }) => {
  await page.goto("http://localhost:13000/", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(5000);

  // 截图首页
  await page.screenshot({ path: path.join(OUT_DIR, "probe-01-landing.png"), fullPage: false });

  // 获取所有可见交互元素
  const elements = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('a, button, [role="button"], input, textarea, [contenteditable], [onclick]'));
    return all
      .filter(el => {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
      })
      .map(el => ({
        tag: el.tagName,
        text: el.textContent?.trim().slice(0, 60) || '',
        href: (el as HTMLAnchorElement).href || '',
        class: (el.className || '').toString().slice(0, 120),
        id: el.id,
        'data-testid': (el as HTMLElement).dataset?.testid || '',
        role: el.getAttribute('role') || '',
        rect: { x: Math.round(el.getBoundingClientRect().x), y: Math.round(el.getBoundingClientRect().y), w: Math.round(el.getBoundingClientRect().width), h: Math.round(el.getBoundingClientRect().height) }
      }));
  });

  fs.writeFileSync(path.join(OUT_DIR, "probe-elements.json"), JSON.stringify(elements, null, 2));
  console.log("Found", elements.length, "interactive elements");
  elements.forEach((e, i) => {
    console.log(`${i}: ${e.tag} "${e.text}" class="${e.class}" href="${e.href}" rect=${JSON.stringify(e.rect)}`);
  });

  // 尝试点击 "开始分析" 按钮
  const startBtn = page.locator('button:has-text("开始分析")').first();
  if (await startBtn.isVisible().catch(() => false)) {
    await startBtn.click();
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(OUT_DIR, "probe-02-after-start.png"), fullPage: false });

    // 再次探测
    const elements2 = await page.evaluate(() => {
      const all = Array.from(document.querySelectorAll('a, button, [role="button"], input, textarea, [contenteditable]'));
      return all
        .filter(el => {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        })
        .map(el => ({
          tag: el.tagName,
          text: el.textContent?.trim().slice(0, 60) || '',
          href: (el as HTMLAnchorElement).href || '',
          class: (el.className || '').toString().slice(0, 120),
          id: el.id,
          'data-testid': (el as HTMLElement).dataset?.testid || '',
          rect: { x: Math.round(el.getBoundingClientRect().x), y: Math.round(el.getBoundingClientRect().y), w: Math.round(el.getBoundingClientRect().width), h: Math.round(el.getBoundingClientRect().height) }
        }));
    });
    fs.writeFileSync(path.join(OUT_DIR, "probe-elements-2.json"), JSON.stringify(elements2, null, 2));
    console.log("After click: Found", elements2.length, "interactive elements");
    elements2.forEach((e, i) => {
      console.log(`${i}: ${e.tag} "${e.text}" class="${e.class}" href="${e.href}" rect=${JSON.stringify(e.rect)}`);
    });
  }
});
