#!/usr/bin/env node
/**
 * 通用工作区截图脚本。
 *
 * 用法：
 *   node scripts/capture-workspace.mjs <workspace_id> <session_id> <case-name>
 *
 * case-name 决定截图策略，当前支持：
 *   - sales-insight
 *   - notebook-analysis
 *   - canvas-workflow
 *   - knowledge-base-qa
 *   - knowledge-graph
 *   - data-table
 *   - agent-config
 *   - autotask
 */
import { chromium } from "playwright";
import { mkdir } from "fs/promises";
import path from "path";

const BASE_URL = "http://127.0.0.1:13000";
const OUTPUT_DIR = path.resolve("../../images/readme");

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForStable(page, selector, timeout = 30000) {
  await page.waitForSelector(selector, { timeout }).catch(() => {});
  await page
    .waitForFunction(
      (sel) => {
        const el = document.querySelector(sel);
        return el && el.innerText.length > 0;
      },
      selector,
      { timeout }
    )
    .catch(() => {});
  await sleep(500);
}

async function screenshotPage(page, name, fullPage = false) {
  const outPath = path.join(OUTPUT_DIR, `${name}.png`);
  await page.screenshot({ path: outPath, fullPage });
  console.log(`Saved ${outPath}`);
}

async function screenshotElement(page, name, selector, clipPadding = 0) {
  const el = await page.$(selector);
  if (!el) {
    console.warn(`Element not found: ${selector}`);
    return;
  }
  const box = await el.boundingBox();
  if (!box) {
    console.warn(`No bounding box for: ${selector}`);
    return;
  }
  const outPath = path.join(OUTPUT_DIR, `${name}.png`);
  await page.screenshot({
    path: outPath,
    clip: {
      x: Math.max(0, box.x - clipPadding),
      y: Math.max(0, box.y - clipPadding),
      width: box.width + clipPadding * 2,
      height: box.height + clipPadding * 2,
    },
  });
  console.log(`Saved ${outPath}`);
}

async function clickByText(page, text, options = {}) {
  const locator = page.locator(`text=${text}`).first();
  await locator.click(options).catch((e) => console.warn(`Click '${text}' failed: ${e.message}`));
  await sleep(800);
}

async function openFileByName(page, fileName) {
  await clickByText(page, fileName);
}

async function openNestedFile(page, folderName, fileName) {
  await clickByText(page, folderName);
  await sleep(300);
  await clickByText(page, fileName);
}

async function captureSalesInsight(page) {
  await screenshotPage(page, "demo-sales-overview", true);
  await openFileByName(page, "sales_insight.md");
  await screenshotPage(page, "demo-sales-report", true);
  await openNestedFile(page, "charts", "monthly_revenue");
  await screenshotPage(page, "demo-sales-chart", true);
  await openFileByName(page, "clean_orders.csv");
  await screenshotPage(page, "demo-sales-csv", true);
}

async function captureNotebookAnalysis(page) {
  await screenshotPage(page, "demo-notebook-overview", true);
  await openNestedFile(page, "notebooks", "demo_analysis.ipynb");
  // Wait for notebook preview to render
  await sleep(2000);
  await screenshotPage(page, "demo-notebook-chart", true);
}

async function capturePaperToKnowledge(page) {
  await openFileByName(page, "literature_brief.md");
  await sleep(1500);
  await screenshotPage(page, "demo-paper-literature", true);
  // Open the CSV matrix; use a more reliable locator and wait for the tab title to change
  const matrixFile = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: "paper_matrix.csv" }).first();
  await matrixFile.click();
  await sleep(2500);
  await screenshotPage(page, "demo-paper-matrix", true);
}

async function captureCanvasWorkflow(page) {
  await openNestedFile(page, "canvas", "sales_workflow.canvas");
  await sleep(2000);
  // Enter immersive canvas preview for maximum space
  const immersiveBtn = await page.$('[data-testid="canvas-immersive-preview-button"]').catch(() => null);
  if (immersiveBtn) {
    await immersiveBtn.click();
    await sleep(1000);
  }
  // Try common zoom-to-fit shortcuts
  await page.keyboard.press("0");
  await sleep(800);
  await page.keyboard.press("1");
  await sleep(800);
  await screenshotPage(page, "demo-canvas-workflow", true);
}

async function captureKnowledgeBaseQA(page) {
  await openFileByName(page, "kb_qa_report.md");
  await sleep(1500);
  await screenshotPage(page, "demo-knowledge-base-qa", true);
}

async function captureKnowledgeGraph(page) {
  await openFileByName(page, "graph_summary.md");
  await sleep(1500);
  await screenshotPage(page, "demo-knowledge-graph-exploration", true);
}

async function captureDataTable(page) {
  // Find the .table.db file in the tree and click it
  const tableFile = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: ".table.db" }).first();
  await tableFile.click();
  await sleep(2500);
  await screenshotPage(page, "demo-data-table", true);
}

async function captureAgentConfig(page) {
  // Agent config lives in workspace settings panel, not a file
  await screenshotPage(page, "demo-agent-workspace-settings", true);
}

async function captureAutotask(page) {
  await screenshotPage(page, "demo-autotask-run", true);
}

async function captureEnvVars(page) {
  await screenshotPage(page, "demo-env-vars-overview", true);
  // Open env vars panel from activity bar (document icon)
  const envBtn = page.locator('[data-testid="activity-bar-env-vars"]').first();
  if (await envBtn.count()) {
    await envBtn.click();
    await sleep(1500);
    await screenshotPage(page, "demo-env-vars-panel", true);
  }
}

async function captureDatabaseQuery(page) {
  await screenshotPage(page, "demo-db-query-overview", true);
  // Try to open database file (.db)
  const dbFile = page.locator('[data-testid="workspace-file-tree-file-node"]').filter({ hasText: ".db" }).first();
  if (await dbFile.count()) {
    await dbFile.click();
    await sleep(2500);
    await screenshotPage(page, "demo-db-query-preview", true);
  }
}

async function captureModelConfig(page) {
  // Open model config panel from activity bar or settings
  const modelBtn = page.locator('[data-testid="activity-bar-model-config"]').first();
  if (await modelBtn.count()) {
    await modelBtn.click();
    await sleep(1500);
    await screenshotPage(page, "demo-model-config-panel", true);
  } else {
    await screenshotPage(page, "demo-model-config-panel", true);
  }
}

async function captureWorkspaceTemplate(page) {
  await screenshotPage(page, "demo-workspace-template", true);
}

const STRATEGIES = {
  "sales-insight": captureSalesInsight,
  "notebook-analysis": captureNotebookAnalysis,
  "paper-to-knowledge": capturePaperToKnowledge,
  "canvas-workflow": captureCanvasWorkflow,
  "knowledge-base-qa": captureKnowledgeBaseQA,
  "knowledge-graph": captureKnowledgeGraph,
  "data-table": captureDataTable,
  "agent-config": captureAgentConfig,
  autotask: captureAutotask,
  "env-vars": captureEnvVars,
  "database-query": captureDatabaseQuery,
  "model-config": captureModelConfig,
  "workspace-template": captureWorkspaceTemplate,
};

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 3) {
    console.error("Usage: node scripts/capture-workspace.mjs <workspace_id> <session_id> <case-name>");
    process.exit(1);
  }

  const [workspaceId, sessionId, caseName] = args;
  const strategy = STRATEGIES[caseName];
  if (!strategy) {
    console.error(`Unknown case-name: ${caseName}. Supported: ${Object.keys(STRATEGIES).join(", ")}`);
    process.exit(1);
  }

  await mkdir(OUTPUT_DIR, { recursive: true });

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    viewport: { width: 1920, height: 1080 },
  });
  const page = await context.newPage();

  const workspaceUrl = `${BASE_URL}/workspace?workspace_id=${workspaceId}&session_id=${sessionId}`;
  console.log(`Opening ${workspaceUrl}`);
  await page.goto(workspaceUrl, { waitUntil: "networkidle" });
  await sleep(2000);
  await waitForStable(page, "[data-testid='workspace-page']", 30000).catch(() =>
    console.log("workspace-page not found, continuing")
  );

  await strategy(page);

  await context.close();
  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
