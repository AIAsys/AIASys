#!/usr/bin/env node
/**
 * README 演示图批量生成脚本。
 *
 * 用法：
 *   node scripts/committed/capture-readme-demos.mjs <case-name>
 *
 * 支持 case-name（对应 l2-user-scenario-tests/cases）：
 *   - demo-001-sales-insight      -> demo-sales-*.png
 *   - demo-009-canvas-workflow-map -> demo-canvas-workflow.png
 *   - demo-013-data-table         -> demo-data-table.png
 *   - demo-014-database-query     -> demo-db-query-overview.png
 *   - demo-010-pdf-translation-skill -> demo-pdf-translation-dual.png
 *   - demo-012-env-vars           -> demo-env-vars-overview.png
 *
 * 流程：先调用 run_case.py 创建工作区并运行 Agent，然后使用 Playwright
 * 截图到项目根目录 images/readme/，分辨率 3200x2000（1600x1000 @ DSF=2）。
 */
import { spawn } from "child_process";
import { chromium } from "playwright";
import { mkdir } from "fs/promises";
import path from "path";
import { fileURLToPath } from "url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, "../../../..");
const IMAGES_DIR = path.join(ROOT, "images/readme");
const EVAL_ROOT = path.resolve(ROOT, "..", "AIASys-eval");
const BASE_URL = "http://127.0.0.1:13000";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function runCase(caseName, title) {
  const caseDir = path.join(EVAL_ROOT, "l2-user-scenario-tests/cases", caseName);
  const script = path.join(EVAL_ROOT, "l2-user-scenario-tests/scripts/run_case.py");
  console.log(`[*] 运行 case: ${caseName} -> ${title}`);
  return new Promise((resolve, reject) => {
    const child = spawn("python3", [script, caseDir, title], {
      cwd: path.dirname(script),
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => {
      stdout += d;
      process.stdout.write(d);
    });
    child.stderr.on("data", (d) => {
      stderr += d;
      process.stderr.write(d);
    });
    child.on("close", (code) => {
      const ws = stdout.match(/workspace_id:\s*([a-f0-9-]+)/);
      const ss = stdout.match(/session_id:\s*([a-f0-9-]+)/);
      if (!ws || !ss) {
        console.error("\n[ERROR] 无法从 run_case.py 输出解析 workspace_id/session_id");
        return reject(new Error("parse ids failed"));
      }
      resolve({ workspaceId: ws[1], sessionId: ss[1], code, stdout, stderr });
    });
  });
}

async function launchBrowser() {
  const browser = await chromium.launch({
    headless: true,
    args: ["--single-process", "--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
  });
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1000 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  return { browser, context, page };
}

async function gotoWorkspace(page, workspaceId, sessionId) {
  const url = `${BASE_URL}/workspace?workspace_id=${workspaceId}&session_id=${sessionId}`;
  console.log(`[*] 打开 ${url}`);
  try {
    await page.goto(url, { waitUntil: "load", timeout: 30000 });
  } catch (e) {
    console.warn("[WARN] goto load timeout, continuing");
  }
  await sleep(4000);
  // 等待文件树出现
  await page
    .waitForSelector('[data-testid="workspace-file-tree-file-node"]', { timeout: 30000 })
    .catch(() => console.warn("[WARN] 未检测到文件树节点"));
  await sleep(500);
}

async function screenshot(page, name) {
  const outPath = path.join(IMAGES_DIR, `${name}.png`);
  await page.screenshot({ path: outPath, fullPage: false, type: "png", timeout: 60000 });
  console.log(`[OK] ${outPath}`);
}

function treeNode(page, text, kind = "file-or-folder") {
  if (kind === "folder") {
    return page.locator('[data-testid="workspace-file-tree-folder-node"]').filter({ hasText: text }).first();
  }
  if (kind === "file") {
    return page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: text }).first();
  }
  return page
    .locator('[data-testid="workspace-file-tree-file-node"], [data-testid="workspace-file-tree-folder-node"]')
    .filter({ hasText: text })
    .first();
}

async function clickNode(page, text, kind = "file-or-folder") {
  const locator = treeNode(page, text, kind);
  if (await locator.count()) {
    await locator.click({ timeout: 10000 });
    await sleep(600);
  } else {
    console.warn(`[WARN] 未找到节点: ${text}`);
  }
}

async function openFolder(page, folderName) {
  const locator = treeNode(page, folderName, "folder");
  if (!(await locator.count())) return false;
  await locator.click();
  await sleep(400);
  return true;
}

async function searchAndClickFile(page, keyword) {
  const input = page.locator('input[placeholder="搜索文件或目录..."]').first();
  if (!(await input.count())) return false;
  await input.fill(keyword);
  await sleep(700);
  const node = page
    .locator('[data-testid="workspace-file-tree-file-node"]')
    .filter({ hasText: keyword })
    .first();
  if (await node.count()) {
    await node.click();
    await sleep(1000);
    return true;
  }
  return false;
}

async function captureSales(page) {
  await screenshot(page, "demo-sales-overview");
  await clickNode(page, "sales_insight.md", "file");
  await sleep(1200);
  await screenshot(page, "demo-sales-report");

  if (await searchAndClickFile(page, "chart1_monthly_trend")) {
    await sleep(1200);
    await screenshot(page, "demo-sales-chart");
  }
}

async function captureCanvas(page) {
  if (await searchAndClickFile(page, "sales_workflow.canvas")) {
    await sleep(2500);
    // 尝试进入沉浸预览
    const immersive = await page.$('[data-testid="canvas-immersive-preview-button"]').catch(() => null);
    if (immersive) {
      await immersive.click();
      await sleep(1200);
    }
    await page.keyboard.press("0");
    await sleep(600);
    await page.keyboard.press("1");
    await sleep(600);
  }
  await screenshot(page, "demo-canvas-workflow");
}

async function captureDataTable(page) {
  // 表文件名常以 .table.db 结尾，可能含中文
  const table = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: /\.table\.db$/ }).first();
  if (await table.count()) {
    await table.click();
    await sleep(2500);
  } else if (await searchAndClickFile(page, ".table.db")) {
    await sleep(2500);
  }
  await screenshot(page, "demo-data-table");
}

async function captureDatabase(page) {
  // 优先找 demo.db / sales.db，否则点击任意 .db
  const known = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: /^(demo|sales)\.db$/ }).first();
  const anyDb = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: /\.db$/ }).first();
  const target = (await known.count()) ? known : anyDb;
  if (await target.count()) {
    await target.click();
    await sleep(2500);
  }
  await screenshot(page, "demo-db-query-overview");
}

async function capturePDF(page) {
  const dual = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: /-dual\.pdf$/ }).first();
  if (await dual.count()) {
    await dual.click();
    await sleep(5000);
  } else if (await searchAndClickFile(page, "-dual.pdf")) {
    await sleep(5000);
  }
  await screenshot(page, "demo-pdf-translation-dual");
}

async function captureEnvVars(page) {
  // 打开工作区设置弹窗（默认即环境变量页）
  const settingsBtn = page.locator('[data-testid="workspace-context-open-settings"]').first();
  if (await settingsBtn.count()) {
    await settingsBtn.click();
    await sleep(1500);
  }
  await screenshot(page, "demo-env-vars-overview");
}

const STRATEGIES = {
  "demo-001-sales-insight": captureSales,
  "demo-009-canvas-workflow-map": captureCanvas,
  "demo-013-data-table": captureDataTable,
  "demo-014-database-query": captureDatabase,
  "demo-010-pdf-translation-skill": capturePDF,
  "demo-012-env-vars": captureEnvVars,
};

async function main() {
  const args = process.argv.slice(2);
  let caseName;
  let workspaceId;
  let sessionId;

  if (args.length === 1) {
    caseName = args[0];
  } else if (args.length === 3 && STRATEGIES[args[2]]) {
    workspaceId = args[0];
    sessionId = args[1];
    caseName = args[2];
  } else {
    console.error(`用法: node ${path.basename(__filename)} <case-name>`);
    console.error(`   或: node ${path.basename(__filename)} <workspace_id> <session_id> <case-name>`);
    console.error(`支持: ${Object.keys(STRATEGIES).join(", ")}`);
    process.exit(1);
  }

  if (!STRATEGIES[caseName]) {
    console.error(`未知 case-name: ${caseName}`);
    process.exit(1);
  }

  await mkdir(IMAGES_DIR, { recursive: true });

  if (!workspaceId || !sessionId) {
    const title = caseName
      .replace("demo-001-sales-insight", "Demo Sales Insight")
      .replace("demo-009-canvas-workflow-map", "Demo Canvas Workflow")
      .replace("demo-013-data-table", "Demo Data Table")
      .replace("demo-014-database-query", "Demo DB Query")
      .replace("demo-010-pdf-translation-skill", "Demo PDF Translation")
      .replace("demo-012-env-vars", "Demo Env Vars");
    const ids = await runCase(caseName, title);
    workspaceId = ids.workspaceId;
    sessionId = ids.sessionId;
    console.log(`[*] workspace_id=${workspaceId}, session_id=${sessionId}`);
  } else {
    console.log(`[*] 复用 workspace_id=${workspaceId}, session_id=${sessionId}`);
  }

  const { browser, context, page } = await launchBrowser();
  try {
    await gotoWorkspace(page, workspaceId, sessionId);
    await STRATEGIES[caseName](page);
    console.log("[*] 截图完成");
  } finally {
    await context.close();
    await browser.close();
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
