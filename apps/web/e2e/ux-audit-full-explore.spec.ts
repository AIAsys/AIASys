import { test, expect } from "@playwright/test";
import path from "path";
import fs from "fs";

const OUT_DIR = "/home/ke/projects/AIASys/design-draft/archive/artifacts/ux-audit-20250609";

// 确保输出目录存在
if (!fs.existsSync(OUT_DIR)) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

test.use({
  video: "on",
  viewport: { width: 1440, height: 900 },
});

test.describe("UX Full System Exploration", () => {
  test("explore all major features with video", async ({ page }, testInfo) => {
    let step = 0;
    const screenshot = async (name: string) => {
      step++;
      const fileName = `${String(step).padStart(2, "0")}-${name}.png`;
      await page.screenshot({ path: path.join(OUT_DIR, fileName), fullPage: false });
      console.log(`[${step}] ${name}`);
    };

    // ========== 1. 首页 ==========
    await page.goto("http://localhost:13000/", { waitUntil: "networkidle" });
    await page.waitForTimeout(3000);
    await screenshot("landing-page");

    // ========== 2. 首页导航项 hover ==========
    const navItems = ["能力概览", "应用场景", "工作方式"];
    for (const item of navItems) {
      const nav = page.locator(`button:has-text("${item}")`).first();
      if (await nav.isVisible().catch(() => false)) {
        await nav.hover();
        await page.waitForTimeout(800);
        await screenshot(`nav-hover-${item}`);
      }
    }

    // ========== 3. 进入工作区列表 ==========
    const startBtn = page.locator('nav button:has-text("开始分析"), header button:has-text("开始分析")').first();
    await startBtn.waitFor({ state: "visible", timeout: 10000 });
    await startBtn.click();
    await page.waitForTimeout(3000);
    await screenshot("workspace-list");

    // ========== 4. 侧边栏功能探索 ==========
    // 点击"频道"
    const channelBtn = page.locator('button:has-text("频道")').first();
    if (await channelBtn.isVisible().catch(() => false)) {
      await channelBtn.click();
      await page.waitForTimeout(1500);
      await screenshot("sidebar-channel");
    }

    // ========== 5. 进入具体工作区 ==========
    await page.goto("http://localhost:13000/workspace?session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db");
    await page.waitForTimeout(5000);
    await screenshot("workspace-detail");

    // ========== 6. 左侧面板切换 ==========
    const leftPanelTabs = [
      { name: "当前工作区", selector: 'button:has-text("当前工作区")' },
      { name: "全局工作区", selector: 'button:has-text("全局工作区")' },
      { name: "数据查询", selector: 'button:has-text("数据查询")' },
      { name: "文件搜索", selector: 'button:has-text("文件搜索")' },
      { name: "监控任务", selector: 'button:has-text("监控任务")' },
      { name: "终端", selector: 'button:has-text("终端")' },
      { name: "自动化任务", selector: 'button:has-text("自动化任务")' },
      { name: "专家协作节点", selector: 'button:has-text("专家协作节点")' },
      { name: "环境变量", selector: 'button:has-text("环境变量")' },
      { name: "能力管理", selector: 'button:has-text("能力管理")' },
      { name: "工作区设置", selector: 'button:has-text("工作区设置")' },
      { name: "文件变更", selector: 'button:has-text("文件变更")' },
    ];

    for (const tab of leftPanelTabs) {
      const btn = page.locator(tab.selector).first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        await page.waitForTimeout(1500);
        await screenshot(`left-panel-${tab.name}`);
      }
    }

    // ========== 7. 回到文件树，展开文件夹 ==========
    const fileTreeTab = page.locator('button:has-text("当前工作区")').first();
    if (await fileTreeTab.isVisible().catch(() => false)) {
      await fileTreeTab.click();
      await page.waitForTimeout(1500);
    }

    // 尝试展开文件夹
    const folderToggles = page.locator('[data-testid="folder-toggle"], button[class*="folder"]').all();
    const toggles = await folderToggles;
    if (toggles.length > 0) {
      await toggles[0].click();
      await page.waitForTimeout(1000);
      await screenshot("file-tree-expanded");
    }

    // ========== 8. 文件树工具栏 ==========
    const toolbarActions = [
      { name: "新建文件", selector: 'button[title*="新建文件"], button[aria-label*="新建文件"]' },
      { name: "新建文件夹", selector: 'button[title*="新建文件夹"], button[aria-label*="新建文件夹"]' },
      { name: "上传文件", selector: 'button[title*="上传"], button[aria-label*="上传"]' },
      { name: "刷新", selector: 'button[title*="刷新"], button[aria-label*="刷新"]' },
      { name: "折叠", selector: 'button[title*="折叠"], button[aria-label*="折叠"]' },
    ];

    for (const action of toolbarActions) {
      const btn = page.locator(action.selector).first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.hover();
        await page.waitForTimeout(500);
        await screenshot(`toolbar-hover-${action.name}`);
      }
    }

    // ========== 9. 对话区域交互 ==========
    // 点击"新建会话"
    const newChatBtn = page.locator('button:has-text("新建会话")').first();
    if (await newChatBtn.isVisible().catch(() => false)) {
      await newChatBtn.click();
      await page.waitForTimeout(2000);
      await screenshot("chat-new-conversation");
    }

    // ========== 10. 输入区域 ==========
    const chatInput = page.locator('textarea, [contenteditable="true"]').first();
    if (await chatInput.isVisible().catch(() => false)) {
      await chatInput.fill("这是一个测试消息，用于验证输入框的交互体验");
      await page.waitForTimeout(500);
      await screenshot("chat-input-filled");
      await chatInput.clear();
    }

    // ========== 11. 模型选择器 ==========
    const modelSelector = page.locator('button:has-text("step-"), button[class*="model"]').first();
    if (await modelSelector.isVisible().catch(() => false)) {
      await modelSelector.click();
      await page.waitForTimeout(1500);
      await screenshot("model-selector-open");
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }

    // ========== 12. Thinking 开关 ==========
    const thinkingBtn = page.locator('button:has-text("Thinking")').first();
    if (await thinkingBtn.isVisible().catch(() => false)) {
      await thinkingBtn.click();
      await page.waitForTimeout(1000);
      await screenshot("thinking-toggle");
    }

    // ========== 13. 工具配置 ==========
    const toolConfigBtn = page.locator('button:has-text("工具配置"), button[title*="工具"]').first();
    if (await toolConfigBtn.isVisible().catch(() => false)) {
      await toolConfigBtn.click();
      await page.waitForTimeout(1500);
      await screenshot("tool-config");
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }

    // ========== 14. Token 预算条 ==========
    const tokenBar = page.locator('button:has-text("预算"), [class*="token"], [class*="budget"]').first();
    if (await tokenBar.isVisible().catch(() => false)) {
      await tokenBar.click();
      await page.waitForTimeout(1500);
      await screenshot("token-budget-clicked");
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }

    // ========== 15. 右侧边栏切换 ==========
    const rightPanelTabs = [
      { name: "收起右侧栏", selector: 'button:has-text("收起右侧栏")' },
    ];
    for (const tab of rightPanelTabs) {
      const btn = page.locator(tab.selector).first();
      if (await btn.isVisible().catch(() => false)) {
        await btn.click();
        await page.waitForTimeout(1500);
        await screenshot(`right-panel-${tab.name}`);
      }
    }

    // ========== 16. 用户菜单 ==========
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    const userMenu = page.locator('button:has-text("Local Default")').first();
    if (await userMenu.isVisible().catch(() => false)) {
      await userMenu.click({ force: true });
      await page.waitForTimeout(1000);
      await screenshot("user-menu");
      await page.keyboard.press("Escape");
      await page.waitForTimeout(500);
    }

    // ========== 17. 运行环境面板 ==========
    await page.keyboard.press("Escape");
    await page.waitForTimeout(500);
    const runtimeBtn = page.locator('button:has-text("运行环境")').first();
    if (await runtimeBtn.isVisible().catch(() => false)) {
      await runtimeBtn.click({ force: true });
      await page.waitForTimeout(1500);
      await screenshot("runtime-environment");
    }

    // ========== 18. 回到首页 ==========
    const homeLink = page.locator('a:has-text("艾斯"), button:has-text("艾斯")').first();
    if (await homeLink.isVisible().catch(() => false)) {
      await homeLink.click();
      await page.waitForTimeout(3000);
      await screenshot("back-to-home");
    }

    // ========== 19. 工作区设置 ==========
    await page.goto("http://localhost:13000/workspace?session_id=9b5a168d-9b77-42a0-8a64-191cec3b41db");
    await page.waitForTimeout(3000);
    const wsSettings = page.locator('button:has-text("工作区设置")').first();
    if (await wsSettings.isVisible().catch(() => false)) {
      await wsSettings.click();
      await page.waitForTimeout(1500);
      await screenshot("workspace-settings");
    }

    // ========== 20. 空状态检查 ==========
    // 检查各种空状态提示
    const emptyStates = await page.locator('text=/没有找到|暂无|为空|未找到|没有/').all();
    for (let i = 0; i < Math.min(emptyStates.length, 3); i++) {
      const text = await emptyStates[i].textContent().catch(() => "");
      if (text.trim()) {
        console.log(`Empty state found: ${text.trim().substring(0, 50)}`);
      }
    }

    await page.waitForTimeout(2000);

    // 复制 video
    const videoPath = testInfo.video?.path;
    if (videoPath) {
      const dest = path.join(OUT_DIR, "ux-full-explore.webm");
      fs.copyFileSync(videoPath, dest);
      console.log("Video saved to:", dest);
    }

    console.log(`Total screenshots: ${step}`);
  });
});
