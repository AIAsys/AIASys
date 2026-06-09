import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-20250608";

test.use({
  video: "on",
  viewport: { width: 1440, height: 900 },
});

test.describe("UX Audit Recording", () => {
  test("record full walkthrough with video", async ({ page }, testInfo) => {
    // ========== 1. 首页 ==========
    await page.goto("http://localhost:13000/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(OUT_DIR, "01-landing.png"), fullPage: false });

    // ========== 2. 进入工作区 ==========
    // 点击顶部"开始分析"按钮（右上角导航栏里的）
    const startBtn = page.locator('nav button:has-text("开始分析"), header button:has-text("开始分析")').first();
    await startBtn.waitFor({ state: "visible", timeout: 10000 });
    await startBtn.click();
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(OUT_DIR, "02-workspace-list.png"), fullPage: false });

    // ========== 3. 侧边栏交互 ==========
    // 点击"新建工作区"（侧边栏里的）
    const sidebarNewWs = page.locator('button:has-text("新建工作区")').nth(0);
    if (await sidebarNewWs.isVisible().catch(() => false)) {
      await sidebarNewWs.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(OUT_DIR, "03-new-workspace-dialog.png"), fullPage: false });
      // 关闭弹窗（按 Escape）
      await page.keyboard.press("Escape");
      await page.waitForTimeout(800);
    }

    // ========== 4. 搜索工作区 ==========
    const searchInput = page.locator('input[class*="pl-9"]').first();
    if (await searchInput.isVisible().catch(() => false)) {
      await searchInput.fill("test");
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT_DIR, "04-search-workspace.png"), fullPage: false });
      await searchInput.clear();
      await page.waitForTimeout(500);
    }

    // ========== 5. 进入具体工作区 ==========
    // 尝试点击第一个工作区卡片或列表项
    const wsItems = page.locator('[class*="workspace"], [data-testid*="workspace"], a[href*="/workspace/"]').first();
    // 如果没有已有工作区，点击主区域"新建工作区"
    const mainNewWs = page.locator('button:has-text("新建工作区")').nth(1);
    if (await mainNewWs.isVisible().catch(() => false)) {
      await mainNewWs.click();
      await page.waitForTimeout(2000);
      await page.screenshot({ path: path.join(OUT_DIR, "05-create-workspace-dialog.png"), fullPage: false });
      // 如果有输入框，填入名称
      const nameInput = page.locator('input[placeholder*="名称"], input[placeholder*="name"], input[placeholder*="工作区"]').first();
      if (await nameInput.isVisible().catch(() => false)) {
        await nameInput.fill("UX Audit Test");
        await page.waitForTimeout(500);
        // 确认创建
        const confirmBtn = page.locator('button:has-text("创建"), button:has-text("确认"), button:has-text("确定")').first();
        if (await confirmBtn.isVisible().catch(() => false)) {
          await confirmBtn.click();
          await page.waitForTimeout(3000);
          await page.screenshot({ path: path.join(OUT_DIR, "05-workspace-created.png"), fullPage: false });
        } else {
          await page.keyboard.press("Escape");
        }
      } else {
        await page.keyboard.press("Escape");
      }
    }

    // ========== 6. 对话区域 ==========
    await page.waitForTimeout(2000);
    const chatInput = page.locator('textarea, [contenteditable="true"], input[placeholder*="消息"], input[placeholder*="输入"]').first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("你好，请帮我分析一下当前的数据情况");
      await page.waitForTimeout(500);
      await chatInput.press("Enter");
      await page.waitForTimeout(4000);
      await page.screenshot({ path: path.join(OUT_DIR, "06-chat-message-sent.png"), fullPage: false });
    }

    // ========== 7. 文件树面板 ==========
    const fileTreeTab = page.locator('button:has-text("文件"), button:has-text("Files"), [class*="file-tree"], [data-testid*="file"]').first();
    if (await fileTreeTab.isVisible().catch(() => false)) {
      await fileTreeTab.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT_DIR, "07-file-tree.png"), fullPage: false });
    }

    // ========== 8. 右侧边栏 / 预览面板切换 ==========
    const previewTab = page.locator('button:has-text("预览"), button:has-text("Preview"), button:has-text("画布"), button:has-text("Canvas"), [data-testid*="preview"]').first();
    if (await previewTab.isVisible().catch(() => false)) {
      await previewTab.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT_DIR, "08-preview-panel.png"), fullPage: false });
    }

    // ========== 9. 设置入口 ==========
    const settingsBtn = page.locator('button[aria-label*="设置"], button:has-text("设置"), button:has-text("Settings"], [data-testid*="settings"], button[class*="gear"], button[class*="cog"]').first();
    if (await settingsBtn.isVisible().catch(() => false)) {
      await settingsBtn.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT_DIR, "09-settings-panel.png"), fullPage: false });
      // 关闭
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }

    // ========== 10. AutoTask / 自动化任务面板 ==========
    const autoTaskBtn = page.locator('button:has-text("AutoTask"), button:has-text("自动任务"), button:has-text("任务"), [data-testid*="auto-task"], [data-testid*="task"]').first();
    if (await autoTaskBtn.isVisible().catch(() => false)) {
      await autoTaskBtn.click();
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT_DIR, "10-auto-task.png"), fullPage: false });
    }

    // ========== 11. Token 预算条 hover ==========
    const tokenBar = page.locator('[data-testid*="token"], [class*="token-usage"], [class*="budget"], [class*="usage-bar"]').first();
    if (await tokenBar.isVisible().catch(() => false)) {
      await tokenBar.hover();
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(OUT_DIR, "11-token-bar-hover.png"), fullPage: false });
    }

    // ========== 12. 滚动测试 ==========
    const scrollable = page.locator('[class*="scrollable"], [class*="messages"], [data-testid*="messages"], .chat-messages, [class*="overflow-y"]').first();
    if (await scrollable.isVisible().catch(() => false)) {
      await scrollable.evaluate((el) => el.scrollTo({ top: el.scrollHeight, behavior: "smooth" }));
      await page.waitForTimeout(1500);
      await page.screenshot({ path: path.join(OUT_DIR, "12-scroll-bottom.png"), fullPage: false });
    }

    // ========== 13. 用户菜单 ==========
    // 先确保没有遮罩层阻挡
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    const userMenu = page.locator('button[class*="rounded-full"], [class*="avatar"], button:has-text("Local Default")').first();
    if (await userMenu.isVisible().catch(() => false)) {
      await userMenu.click({ force: true });
      await page.waitForTimeout(1000);
      await page.screenshot({ path: path.join(OUT_DIR, "13-user-menu.png"), fullPage: false });
      await page.keyboard.press("Escape");
    }

    await page.waitForTimeout(2000);

    // 复制 video 到目标目录
    const videoPath = testInfo.video?.path;
    if (videoPath) {
      const dest = path.join(OUT_DIR, "ux-audit-recording.webm");
      fs.copyFileSync(videoPath, dest);
      console.log("Video saved to:", dest);
    }
  });
});
