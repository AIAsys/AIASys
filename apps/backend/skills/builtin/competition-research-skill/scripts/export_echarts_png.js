#!/usr/bin/env node
/**
 * Export ECharts JSON configs to PNG images using Playwright.
 *
 * Usage:
 *   node export_echarts_png.js --input <file_or_dir> --output <dir> [--width 1200] [--height 600]
 *
 * Environment:
 *   PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH — optional custom chromium path
 */

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

function parseArgs(argv) {
  const args = { width: 1200, height: 600 };
  for (let i = 2; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--input" || arg === "-i") args.input = argv[++i];
    else if (arg === "--output" || arg === "-o") args.output = argv[++i];
    else if (arg === "--width" || arg === "-w") args.width = parseInt(argv[++i], 10);
    else if (arg === "--height" || arg === "-h") args.height = parseInt(argv[++i], 10);
  }
  if (!args.input || !args.output) {
    console.error("Usage: node export_echarts_png.js --input <file_or_dir> --output <dir> [--width 1200] [--height 600]");
    process.exit(1);
  }
  return args;
}

function buildHtml(configJson) {
  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body { margin: 0; background: #fff; }
#chart { width: 100vw; height: 100vh; }
</style>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
</head>
<body>
<div id="chart"></div>
<script>
const cfg = ${JSON.stringify(configJson)};
const chart = echarts.init(document.getElementById('chart'), null, { renderer: 'canvas' });
chart.setOption(cfg);
window.__ECHARTS_READY__ = true;
</script>
</body>
</html>`;
}

async function exportSingle(browser, inputPath, outputPath, width, height) {
  const config = JSON.parse(fs.readFileSync(inputPath, "utf-8"));
  const html = buildHtml(config);

  const page = await browser.newPage({ viewport: { width, height } });
  await page.setContent(html, { waitUntil: "networkidle" });
  await page.waitForFunction(() => window.__ECHARTS_READY__ === true, { timeout: 30000 });

  // Give a small buffer for final render
  await page.waitForTimeout(500);

  const chartEl = await page.$("#chart");
  await chartEl.screenshot({ path: outputPath, type: "png" });
  await page.close();
  console.log(`Exported: ${outputPath}`);
}

async function main() {
  const args = parseArgs(process.argv);
  const inputStat = fs.statSync(args.input);

  const launchOpts = { headless: true };
  if (process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH) {
    launchOpts.executablePath = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
  }
  const browser = await chromium.launch(launchOpts);

  try {
    if (inputStat.isDirectory()) {
      const files = fs.readdirSync(args.input)
        .filter(f => f.endsWith(".echarts.json"))
        .sort();
      if (files.length === 0) {
        console.error("No .echarts.json files found in input directory.");
        process.exit(1);
      }
      fs.mkdirSync(args.output, { recursive: true });
      for (const file of files) {
        const inputPath = path.join(args.input, file);
        const outputPath = path.join(args.output, file.replace(".echarts.json", ".png"));
        await exportSingle(browser, inputPath, outputPath, args.width, args.height);
      }
    } else {
      fs.mkdirSync(path.dirname(args.output), { recursive: true });
      await exportSingle(browser, args.input, args.output, args.width, args.height);
    }
  } finally {
    await browser.close();
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
