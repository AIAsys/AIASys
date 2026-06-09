import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-20250609";

if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

test.use({
  video: "on",
  viewport: { width: 1440, height: 900 },
});

test.describe("Sidebar Tabs Deep Audit", () => {
  test("test all sidebar tab interactions", async ({ page }, testInfo) => {
    let step = 100;
    const screenshot = async (name: string) => {
      step++;
      const fileName = `${step}-${name}.png`;
      await page.screenshot({ path: path.join(OUT_DIR, fileName), fullPage: false });
      console.log(`[${step}] ${name}`);
    };

    // 进入工作区
    await page.goto("http://localhost:13000/workspace?session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db");
    await page.waitForTimeout(5000);
    await screenshot("initial-state");

    // 获取所有左侧图标按钮（通过左侧栏的 nav 区域）
    const sidebarButtons = await page.locator('aside button, [class*="sidebar"] > div button, nav[class*="sidebar"] button').all();
    console.log(`Found ${sidebarButtons.length} sidebar buttons`);

    // 记录每个按钮的初始状态
    const buttonStates: Array<{ index: number; text: string; ariaLabel: string; title: string; className: string }> = [];
    for (let i = 0; i < sidebarButtons.length; i++) {
      const btn = sidebarButtons[i];
      const text = await btn.textContent().catch(() => '');
      const ariaLabel = await btn.getAttribute('aria-label').catch(() => '');
      const title = await btn.getAttribute('title').catch(() => '');
      const className = await btn.evaluate(el => el.className).catch(() => '');
      if (text.trim() || ariaLabel || title) {
        buttonStates.push({ index: i, text: text.trim().substring(0, 30), ariaLabel, title, className: className.substring(0, 50) });
      }
    }
    console.log('Button states:', JSON.stringify(buttonStates, null, 2));

    // 逐个点击左侧图标按钮，观察状态变化
    const iconButtons = await page.locator('[class*="sidebar"] button, aside > div > button').all();
    console.log(`Found ${iconButtons.length} icon buttons`);

    for (let i = 0; i < Math.min(iconButtons.length, 15); i++) {
      const btn = iconButtons[i];
      const ariaLabel = await btn.getAttribute('aria-label').catch(() => '');
      const title = await btn.getAttribute('title').catch(() => '');
      const label = ariaLabel || title || `btn-${i}`;

      // 检查按钮是否可见且可点击
      const isVisible = await btn.isVisible().catch(() => false);
      if (!isVisible) continue;

      // 先关闭可能存在的弹窗遮罩
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);

      // 记录点击前的状态
      const beforeClass = await btn.evaluate(el => el.className).catch(() => '');

      await btn.click({ force: true });
      await page.waitForTimeout(1500);

      // 记录点击后的状态
      const afterClass = await btn.evaluate(el => el.className).catch(() => '');
      const hasActiveState = afterClass.includes('active') || afterClass.includes('bg-') || afterClass !== beforeClass;

      await screenshot(`tab-${label.replace(/\s+/g, '-')}`);

      console.log(`Tab ${label}: active=${hasActiveState}`);
    }

    // 测试对话时左侧栏的状态变化
    await page.goto("http://localhost:13000/workspace?session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db");
    await page.waitForTimeout(3000);

    // 找到输入框并发送消息
    const chatInput = page.locator('textarea').first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("测试消息，观察左侧栏状态");
      await page.waitForTimeout(500);
      await screenshot("before-send");

      // 点击发送
      const sendBtn = page.locator('button[aria-label="发送"], button:has-text("发送")').first();
      if (await sendBtn.isVisible().catch(() => false)) {
        await sendBtn.click();
        await page.waitForTimeout(2000);
        await screenshot("after-send");

        // 等待 AI 回复过程中观察左侧栏
        await page.waitForTimeout(3000);
        await screenshot("during-response");

        // 再等一会儿
        await page.waitForTimeout(5000);
        await screenshot("after-response");
      }
    }

    // 测试文件树展开/折叠时左侧栏状态
    await page.goto("http://localhost:13000/workspace?session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db");
    await page.waitForTimeout(3000);

    // 找到文件树中的文件夹并点击展开
    const folders = await page.locator('button[class*="folder"], [data-testid="folder-toggle"]').all();
    console.log(`Found ${folders.length} folder toggles`);

    for (let i = 0; i < Math.min(folders.length, 3); i++) {
      await folders[i].click();
      await page.waitForTimeout(1000);
      await screenshot(`folder-expand-${i}`);
    }

    // 复制 video
    const videoPath = testInfo.video?.path;
    if (videoPath) {
      const dest = path.join(OUT_DIR, "ux-sidebar-tabs.webm");
      fs.copyFileSync(videoPath, dest);
      console.log("Video saved to:", dest);
    }

    console.log(`Total screenshots: ${step - 100}`);
  });
});
