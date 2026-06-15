/**
 * 全局控制面板 8 维度交互视觉评审脚本
 *
 * 修复点：
 * 1. 先点击 landing page "开始分析" 进入应用
 * 2. 打开设置菜单并点击"全局控制面板"弹出对话框
 * 3. 在对话框左侧导航内切换 Tab
 * 4. 所有 8 维度采集限制在 [role="dialog"] 容器内
 * 5. 激活态识别使用对话框导航中的 aria-current="page"
 */

import { chromium } from "playwright";
import fs from "fs";
import http from "http";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ARTIFACTS_DIR = path.resolve(
  __dirname,
  "../../design-draft/archive/global-settings-8d-review-20260614"
);
const REPORT_PATH = path.resolve(ARTIFACTS_DIR, "report-serial.json");

// 可通过环境变量切换验证目标，例如验证构建产物：
// GLOBAL_SETTINGS_BASE_URL=http://127.0.0.1:13005 node e2e/scripts/global-settings-8d-review.mjs
const BASE_URL = process.env.GLOBAL_SETTINGS_BASE_URL || "http://127.0.0.1:13000";

function ensureDir(dir) {
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true });
  }
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * 文件锁：防止脚本并发运行导致 Chromium 进程爆炸
 */
const LOCK_FILE = path.resolve(__dirname, ".global-settings-8d-review.lock");

function acquireLock() {
  try {
    if (fs.existsSync(LOCK_FILE)) {
      const pid = fs.readFileSync(LOCK_FILE, "utf-8").trim();
      try {
        process.kill(Number(pid), 0);
        console.error(`⚠️ 已有实例在运行 (PID ${pid})，跳过本次执行`);
        process.exit(1);
      } catch {
        console.warn(`⚠️ 发现过期锁文件 (PID ${pid})，将清理后重新加锁`);
        fs.unlinkSync(LOCK_FILE);
      }
    }
    fs.writeFileSync(LOCK_FILE, String(process.pid), { flag: "wx" });
  } catch (err) {
    console.error("⚠️ 获取文件锁失败:", err.message);
    process.exit(1);
  }
}

function releaseLock() {
  try {
    if (fs.existsSync(LOCK_FILE)) {
      fs.unlinkSync(LOCK_FILE);
    }
  } catch {
    // ignore
  }
}

/**
 * 简单 HTTP 健康检查
 */
function checkHealth(url, timeoutMs = 3000) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      resolve(res.statusCode >= 200 && res.statusCode < 500);
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

// 全局设置对话框左侧导航里的 Tab 文案
const TABS = [
  { id: "capabilities", label: "能力管理" },
  { id: "tool-strategy", label: "我的默认配置" },
  { id: "llm", label: "模型配置" },
  { id: "env-vars", label: "全局环境变量" },
  { id: "uv-mirror", label: "uv 包管理器镜像" },
  { id: "storage", label: "存储位置" },
  { id: "execution-resources", label: "执行资源" },
  { id: "auto-tasks", label: "自动化任务" },
  { id: "monitor-tasks", label: "监控任务" },
  { id: "template-market", label: "模板市场" },
  { id: "template-management", label: "模板管理" },
];

const DIALOG_SELECTOR = '[role="dialog"]';

/**
 * 从页面提取 8 维度数据
 */
async function extractDimensions(page, tabId, tabLabel) {
  const data = {
    tabId,
    tabLabel,
    timestamp: new Date().toISOString(),
    statusConsistency: {
      tabActive: false,
      activeTabLabel: null,
      contentRendered: false,
      hasLoadingSpinner: false,
      hasSkeleton: false,
    },
    navigation: {
      tabSwitchable: true,
      tabClickable: true,
      previousContentLeaked: false,
      leakedLabels: [],
    },
    layout: {
      mainContentWidth: 0,
      sidebarWidth: 0,
      contentOverflow: false,
      elementSqueezed: false,
      scrollableAreas: 0,
    },
    buttons: {
      primaryButtons: [],
      secondaryButtons: [],
      disabledButtons: [],
      emptyStateCTA: null,
    },
    inputs: {
      searchPlaceholder: null,
      inputFields: [],
      selectFields: [],
      disabledInputs: 0,
    },
    loadingErrorEmpty: {
      isLoading: false,
      hasError: false,
      errorMessage: null,
      isEmptyState: false,
      emptyStateTitle: null,
      emptyStateDescription: null,
    },
    copywriting: {
      containsLegacyTerms: [],
      containsEnglishStatus: [],
      terminologyIssues: [],
    },
    streamHistoryConsistency: {
      historyRestoredCorrectly: true,
      stateAfterRefresh: "unknown",
    },
  };

  const dialog = page.locator(DIALOG_SELECTOR).first();
  const dialogExists = (await dialog.count()) > 0;
  if (!dialogExists) {
    data.statusConsistency.contentRendered = false;
    return data;
  }

  // 1. 交互状态一致性：在对话框导航内查找 aria-current="page"
  const activeNavBtn = dialog.locator('nav button[aria-current="page"]').first();
  if ((await activeNavBtn.count()) > 0) {
    data.statusConsistency.tabActive = true;
    data.statusConsistency.activeTabLabel = (await activeNavBtn.textContent())?.trim() || null;
  }

  data.statusConsistency.hasLoadingSpinner =
    (await dialog.locator(".animate-spin").count()) > 0;
  data.statusConsistency.hasSkeleton =
    (await dialog.locator('[class*="skeleton"], [class*="animate-pulse"]').count()) > 0;

  // 内容区：对话框右侧 main 区域
  const mainLocator = dialog.locator("main");
  let contentText = "";
  if ((await mainLocator.count()) > 0) {
    contentText = (await mainLocator.first().textContent().catch(() => "")) || "";
  }
  data.statusConsistency.contentRendered = contentText.trim().length > 20;

  // 2. 导航与视图切换：检查当前内容区是否包含其他 Tab 标题
  const allTabLabels = TABS.map((t) => t.label).filter(Boolean);
  const leakedLabels = allTabLabels.filter(
    (label) => label !== tabLabel && contentText.includes(label)
  );
  data.navigation.previousContentLeaked = leakedLabels.length > 0;
  data.navigation.leakedLabels = leakedLabels;

  // 3. 布局与空间分配
  const layoutResult = await dialog.evaluate((el) => {
    const sidebar = el.querySelector("aside");
    const main = el.querySelector("main");
    return {
      mainContentWidth: main ? Math.round(main.getBoundingClientRect().width) : 0,
      sidebarWidth: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : 0,
    };
  });
  data.layout.mainContentWidth = layoutResult.mainContentWidth;
  data.layout.sidebarWidth = layoutResult.sidebarWidth;

  data.layout.contentOverflow = await dialog.evaluate((el) => {
    const panels = el.querySelectorAll("main, [class*='settings-content']");
    for (const panel of panels) {
      if (panel.scrollWidth > panel.clientWidth + 1) return true;
    }
    return false;
  });

  data.layout.scrollableAreas = await dialog
    .locator('[class*="overflow-auto"], [class*="overflow-y-auto"]')
    .count();

  // 4. 按钮可用性与操作引导（限制在对话框内容区，排除左侧导航）
  const { primaryButtons, secondaryButtons, disabledButtons } = await dialog.evaluate((dialogEl) => {
    const result = { primaryButtons: [], secondaryButtons: [], disabledButtons: [] };
    const contentBtns = dialogEl.querySelectorAll("main button, main [role='button']");
    for (const btn of contentBtns) {
      const text = (btn.textContent || "").trim();
      if (!text || text.length > 100) continue;
      const isDisabled =
        btn.disabled || btn.getAttribute("aria-disabled") === "true" || btn.hasAttribute("disabled");
      const cls = btn.className || "";
      if (isDisabled) {
        result.disabledButtons.push(text);
      } else if (cls.includes("bg-primary") || cls.includes("btn-primary") || cls.includes("variant-default")) {
        result.primaryButtons.push(text);
      } else {
        result.secondaryButtons.push(text);
      }
    }
    const navBtns = dialogEl.querySelectorAll("aside button, aside [role='button']");
    for (const btn of navBtns) {
      const text = (btn.textContent || "").trim();
      if (text && text.length < 50 && !result.secondaryButtons.includes(`[nav] ${text}`)) {
        result.secondaryButtons.push(`[nav] ${text}`);
      }
    }
    return result;
  });

  data.buttons = { primaryButtons, secondaryButtons, disabledButtons, emptyStateCTA: null };

  // 空状态 CTA（先检查数量，避免 textContent 在元素不存在时超时等待）
  const emptyCTALocator = dialog
    .locator("main")
    .locator('[class*="empty"], [class*="empty-state"], [class*="no-data"]')
    .locator("button, a");
  if ((await emptyCTALocator.count()) > 0) {
    data.buttons.emptyStateCTA = await emptyCTALocator.first().textContent().catch(() => null);
  }

  // 5. 输入控件与表单（限制在 main 内容区）
  const inputData = await dialog.evaluate((dialogEl) => {
    const main = dialogEl.querySelector("main");
    if (!main) return { searchPlaceholder: null, inputFields: [], selectFields: [], disabledInputs: 0 };

    const searchInput = main.querySelector('input[type="search"], input[placeholder*="搜索"]');
    const searchPlaceholder = searchInput ? searchInput.getAttribute("placeholder") : null;

    const inputFields = [];
    const selectFields = [];
    let disabledInputs = 0;

    for (const el of main.querySelectorAll("input, select, textarea")) {
      const tagName = el.tagName.toLowerCase();
      const type = el.getAttribute("type") || "";
      const placeholder = el.getAttribute("placeholder") || "";
      const disabled =
        el.disabled || el.getAttribute("aria-disabled") === "true" || el.hasAttribute("disabled");
      if (disabled) disabledInputs++;

      if (tagName === "select") {
        const options = Array.from(el.querySelectorAll("option")).map((o) => o.textContent?.trim() || "");
        selectFields.push({ placeholder, options });
      } else if (type !== "hidden") {
        inputFields.push({ type, placeholder, disabled });
      }
    }

    return { searchPlaceholder, inputFields, selectFields, disabledInputs };
  });

  data.inputs = { ...data.inputs, ...inputData };

  // 6. 加载、错误与空状态
  data.loadingErrorEmpty.isLoading =
    data.statusConsistency.hasLoadingSpinner || data.statusConsistency.hasSkeleton;

  // 错误检测限定在真实错误/警告组件，避免匹配 Tailwind text-error 等样式类误报
  const errorElements = dialog.locator(
    "main [role='alert'], main [class*='alert-error'], main [class*='alert-destructive'], main [data-error]"
  );
  data.loadingErrorEmpty.hasError = (await errorElements.count()) > 0;
  if (data.loadingErrorEmpty.hasError) {
    data.loadingErrorEmpty.errorMessage = await errorElements.first().textContent();
  }

  const emptyIndicators = dialog
    .locator("main")
    .locator('[class*="empty"], [class*="no-data"], [class*="empty-state"]');
  data.loadingErrorEmpty.isEmptyState = (await emptyIndicators.count()) > 0;
  if (data.loadingErrorEmpty.isEmptyState) {
    const emptyEl = emptyIndicators.first();
    data.loadingErrorEmpty.emptyStateTitle = await emptyEl
      .locator("h3, h4, .title, strong")
      .first()
      .textContent()
      .catch(() => null);
    data.loadingErrorEmpty.emptyStateDescription = await emptyEl
      .locator("p, .description")
      .first()
      .textContent()
      .catch(() => null);
  }

  // 7. 文案与语义
  const englishStatus = [];
  const terminologyIssues = [];
  const statusMatches = contentText.match(/\b(Active|Idle|Closed|Running|Pending|Completed|Failed|Cancelled)\b/g);
  if (statusMatches) englishStatus.push(...statusMatches);
  if (contentText.includes("Goal")) terminologyIssues.push("使用旧称 'Goal' 而非 '会话'");

  data.copywriting = {
    containsLegacyTerms: [],
    containsEnglishStatus: englishStatus,
    terminologyIssues,
  };

  return data;
}

/**
 * 全局设置面板是否已打开
 */
async function isDialogOpen(page) {
  return (await page.locator(DIALOG_SELECTOR).count()) > 0;
}

/**
 * 进入应用并打开全局设置面板
 */
async function openGlobalSettings(page) {
  await page.goto(`${BASE_URL}/`, {
    waitUntil: "domcontentloaded",
    timeout: 30000,
  });
  await sleep(2500);

  // 从着陆页进入应用（使用可见按钮，避免动画导致 click 不稳定）
  const startBtn = page.locator('button:visible:has-text("开始分析")').first();
  if ((await startBtn.count()) > 0) {
    await startBtn.click({ force: true });
    await sleep(2000);
  }

  await openSettingsDialogFromWorkspace(page);
}

/**
 * 从工作区页面打开全局设置面板（不重新加载页面）
 */
async function openSettingsDialogFromWorkspace(page) {
  if (await isDialogOpen(page)) return;

  // 打开设置菜单
  const settingsTrigger = page.locator('[data-testid="sidebar-workspace-tools-menu-trigger"]').first();
  if ((await settingsTrigger.count()) > 0) {
    await settingsTrigger.click({ force: true });
    await sleep(400);
  }

  // 打开全局控制面板
  const globalSettingsItem = page.locator('[data-testid="sidebar-workspace-tools-global-settings"]').first();
  if ((await globalSettingsItem.count()) > 0) {
    await globalSettingsItem.click({ force: true });
    await sleep(800);
  }

  // 等待对话框出现
  await page.waitForSelector('[role="dialog"]', { timeout: 5000 });
}

const SKIP_SCREENSHOTS = process.env.SKIP_SCREENSHOTS === "1";
const screenshotOptions = { fullPage: false, timeout: 5000 };

/**
 * 创建新的 Playwright context，已屏蔽外部字体
 */
async function createReviewContext(browser) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  await context.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await context.route("https://fonts.gstatic.com/**", (route) => route.abort());
  return context;
}

/**
 * 在指定 page 上检查单个 Tab
 */
async function checkSingleTab(page, tab, index) {
  console.log(`\n[Tab ${index + 1}/${TABS.length}] 检查: ${tab.label}`);

  const dialog = page.locator(DIALOG_SELECTOR).first();
  const navBtn = dialog.locator("nav").locator(`button:has-text("${tab.label}")`).first();

  if ((await navBtn.count()) === 0) {
    console.log(`  ⚠️ 未在对话框导航中找到 Tab: ${tab.label}`);
    return {
      tabId: tab.id,
      tabLabel: tab.label,
      error: "未在对话框导航中找到 Tab",
      timestamp: new Date().toISOString(),
    };
  }

  await navBtn.click({ force: true });
  await sleep(900);

  const dimensionData = await extractDimensions(page, tab.id, tab.label);

  if (!SKIP_SCREENSHOTS) {
    const screenshotPath = path.join(ARTIFACTS_DIR, `tab-${index + 1}-${tab.id}.png`);
    try {
      await page.screenshot({ path: screenshotPath, ...screenshotOptions });
    } catch (e) {
      console.warn(`  ⚠️ ${tab.label} 截图失败:`, e.message);
    }
  }

  console.log(`  内容渲染: ${dimensionData.statusConsistency.contentRendered ? "✅" : "❌"}`);
  console.log(`  当前激活: ${dimensionData.statusConsistency.activeTabLabel || "❌"}`);
  console.log(`  Loading: ${dimensionData.loadingErrorEmpty.isLoading ? "⚠️" : "✅"}`);
  console.log(`  空状态: ${dimensionData.loadingErrorEmpty.isEmptyState ? "⚠️" : "✅"}`);
  console.log(`  错误: ${dimensionData.loadingErrorEmpty.hasError ? "⚠️" : "✅"}`);
  console.log(`  主按钮: ${dimensionData.buttons.primaryButtons.join(", ") || "无"}`);
  console.log(`  次按钮数: ${dimensionData.buttons.secondaryButtons.length}`);
  console.log(`  输入框数: ${dimensionData.inputs.inputFields.length}`);
  console.log(`  下拉框数: ${dimensionData.inputs.selectFields.length}`);
  console.log(`  搜索框: ${dimensionData.inputs.searchPlaceholder || "无"}`);
  console.log(`  内容残留: ${dimensionData.navigation.previousContentLeaked ? "⚠️ " + dimensionData.navigation.leakedLabels.join(", ") : "✅"}`);

  return dimensionData;
}

/**
 * 串行检查所有 Tab，按 batch 重启 context 以避免单 context 长时间运行崩溃
 */
async function checkAllTabs(browser) {
  const results = [];
  const BATCH_SIZE = 6;

  for (let batchStart = 0; batchStart < TABS.length; batchStart += BATCH_SIZE) {
    const batch = TABS.slice(batchStart, batchStart + BATCH_SIZE);
    console.log(`\n=== 批次 ${Math.floor(batchStart / BATCH_SIZE) + 1}，Tab ${batchStart + 1}~${Math.min(batchStart + BATCH_SIZE, TABS.length)} ===`);

    const context = await createReviewContext(browser);
    const page = await context.newPage();
    page.on("pageerror", (err) => console.error(`  [batch pageerror]`, err.message));
    page.on("crash", () => console.error(`  [batch] page crashed`));

    try {
      await openGlobalSettings(page);

      if (batchStart === 0 && !SKIP_SCREENSHOTS) {
        try {
          await page.screenshot({
            path: path.join(ARTIFACTS_DIR, "00-initial-state.png"),
            ...screenshotOptions,
          });
        } catch (e) {
          console.warn("  ⚠️ 初始状态截图失败:", e.message);
        }
      }

      for (let i = 0; i < batch.length; i++) {
        const tab = batch[i];
        const globalIndex = batchStart + i;
        try {
          // 如果面板意外关闭，尝试重新打开
          if (!(await isDialogOpen(page))) {
            console.log("  ⚠️ 全局设置面板已关闭，尝试重新打开...");
            await openSettingsDialogFromWorkspace(page);
          }
          const result = await checkSingleTab(page, tab, globalIndex);
          results.push(result);
        } catch (err) {
          console.error(`  ❌ ${tab.label} 检查失败:`, err.message);
          results.push({
            tabId: tab.id,
            tabLabel: tab.label,
            error: err.message,
            timestamp: new Date().toISOString(),
          });
        }
      }
    } catch (err) {
      console.error("批次过程出错:", err);
      throw err;
    } finally {
      await Promise.race([
        context.close().catch((e) => console.warn("  ⚠️ context.close 失败:", e.message)),
        sleep(2000),
      ]);
    }
  }

  return results;
}

/**
 * 交叉链路检查：能力管理 -> 模型配置
 */
async function checkCrossLink(browser) {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  });
  await context.route("https://fonts.googleapis.com/**", (route) => route.abort());
  await context.route("https://fonts.gstatic.com/**", (route) => route.abort());
  const page = await context.newPage();

  try {
    console.log("\n=== 交叉链路检查 ===");
    await openGlobalSettings(page);

    const dialog = page.locator(DIALOG_SELECTOR).first();
    await dialog.locator("nav").locator('button:has-text("能力管理")').first().click({ force: true });
    await sleep(800);
    await dialog.locator("nav").locator('button:has-text("模型配置")').first().click({ force: true });
    await sleep(1000);

    const crossData = await extractDimensions(page, "llm", "模型配置");
    crossData.crossCheck = {
      type: "tab-switch-residue",
      fromTab: "capabilities",
      toTab: "llm",
    };

    const screenshotPath = path.join(ARTIFACTS_DIR, "cross-link-llm.png");
    if (!SKIP_SCREENSHOTS) {
      try {
        await page.screenshot({ path: screenshotPath, fullPage: false, timeout: 5000 });
      } catch (e) {
        console.warn("  ⚠️ 交叉链路截图失败:", e.message);
      }
    }

    console.log(`  内容残留: ${crossData.navigation.previousContentLeaked ? "⚠️ " + crossData.navigation.leakedLabels.join(", ") : "✅"}`);
    console.log(`  当前激活: ${crossData.statusConsistency.activeTabLabel || "❌"}`);
    return crossData;
  } catch (err) {
    console.error("交叉链路检查错误:", err);
    return { error: err.message, crossCheck: { type: "tab-switch-residue" } };
  } finally {
    // 应用可能持有 WebSocket/长连接，context.close() 会挂起等待，这里加超时兜底
    await Promise.race([
      context.close().catch((e) => console.warn("  ⚠️ context.close 失败:", e.message)),
      sleep(2000),
    ]);
  }
}

(async () => {
  acquireLock();

  let browser = null;
  let results = [];
  let crossResult = null;

  // 信号处理：收到终止信号时立即关闭浏览器并释放锁
  const handleSignal = async (signal) => {
    console.warn(`\n⚠️ 收到 ${signal}，开始清理...`);
    if (browser) {
      await Promise.race([
        browser.close().catch(() => {}),
        sleep(2000),
      ]);
    }
    releaseLock();
    process.exit(1);
  };
  process.on("SIGTERM", () => handleSignal("SIGTERM"));
  process.on("SIGINT", () => handleSignal("SIGINT"));

  try {
    ensureDir(ARTIFACTS_DIR);
    console.log("=== 全局控制面板 8 维度交互视觉评审 ===");
    console.log(`目标: ${BASE_URL}`);
    console.log(`Artifacts: ${ARTIFACTS_DIR}\n`);

    // 尝试检测后端健康，若后端不可达则给出明确警告（不阻塞，因为脚本仍可检测 UI 结构）
    const backendHealthy = await checkHealth(`${BASE_URL}/api/auth/session`);
    if (!backendHealthy) {
      console.warn("⚠️ 后端 /api/auth/session 未响应，工作区页面可能无法渲染，评审结果可能不准确。");
    }

    // 限制 Chromium 子进程数，降低 WSL 资源压力
    browser = await chromium.launch({
      headless: true,
      args: [
        "--single-process",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
      ],
    });

    results = await checkAllTabs(browser);
    crossResult = await checkCrossLink(browser);
  } catch (err) {
    console.error("执行出错:", err);
  } finally {
    // 应用长连接可能导致 browser.close() 挂起，竞争超时后强制退出
    if (browser) {
      await Promise.race([
        browser.close().catch((e) => console.warn("  ⚠️ browser.close 失败:", e.message)),
        sleep(3000),
      ]);
    }
    releaseLock();
  }

  const allResults = crossResult ? [...results, crossResult] : results;

  const report = {
    meta: {
      generatedAt: new Date().toISOString(),
      totalTabs: TABS.length,
      dimensions: [
        "交互状态一致性",
        "导航与视图切换",
        "布局与空间分配",
        "按钮可用性与操作引导",
        "输入控件与表单",
        "加载、错误与空状态",
        "文案与语义（产品口径）",
        "流式输出与历史恢复一致性",
      ],
      artifactsDir: ARTIFACTS_DIR,
      mode: "serial",
    },
    results: allResults,
    summary: {
      tabsWithLoading: allResults.filter((r) => r.loadingErrorEmpty?.isLoading).map((r) => r.tabLabel),
      tabsWithEmptyState: allResults.filter((r) => r.loadingErrorEmpty?.isEmptyState).map((r) => r.tabLabel),
      tabsWithError: allResults.filter((r) => r.loadingErrorEmpty?.hasError).map((r) => r.tabLabel),
      tabsWithLegacyTerms: allResults.filter((r) => r.copywriting?.containsLegacyTerms?.length > 0).map((r) => r.tabLabel),
      tabsWithEnglishStatus: allResults.filter((r) => r.copywriting?.containsEnglishStatus?.length > 0).map((r) => r.tabLabel),
      tabsWithLeakedContent: allResults.filter((r) => r.navigation?.previousContentLeaked).map((r) => r.tabLabel),
      tabsWithoutActiveState: allResults.filter((r) => !r.statusConsistency?.tabActive).map((r) => r.tabLabel),
    },
  };

  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2), "utf-8");

  console.log("\n=== 报告已生成 ===");
  console.log(`路径: ${REPORT_PATH}`);
  console.log("\n=== 摘要 ===");
  console.log(`仍在 Loading: ${report.summary.tabsWithLoading.join(", ") || "无"}`);
  console.log(`空状态: ${report.summary.tabsWithEmptyState.join(", ") || "无"}`);
  console.log(`激活态缺失: ${report.summary.tabsWithoutActiveState.join(", ") || "无"}`);
  console.log(`有错误: ${report.summary.tabsWithError.join(", ") || "无"}`);
  console.log(`有遗留术语: ${report.summary.tabsWithLegacyTerms.join(", ") || "无"}`);
  console.log(`有英文状态: ${report.summary.tabsWithEnglishStatus.join(", ") || "无"}`);
  console.log(`有内容残留: ${report.summary.tabsWithLeakedContent.join(", ") || "无"}`);

  // 应用可能持有长连接，browser.close() 会挂起，这里强制退出
  setTimeout(() => process.exit(0), 200);
})();
