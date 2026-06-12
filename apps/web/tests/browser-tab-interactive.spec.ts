import { test, expect } from "@playwright/test";

test("debug onOpenInBrowserTab error - interactive", async ({ page }) => {
  const errors: { msg: string; stack?: string }[] = [];

  page.on("pageerror", (err) => {
    errors.push({ msg: err.message, stack: err.stack });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      errors.push({ msg: msg.text(), stack: msg.stacktrace()?.slices.map((s) => `${s.function}:${s.line}:${s.column}`).join("\n") });
    }
  });

  await page.goto("http://localhost:13000", { waitUntil: "networkidle" });
  await page.waitForTimeout(3000);

  // Try clicking the "+" button
  const plusBtn = page.locator('[title="新建"]').first();
  if (await plusBtn.count() > 0) {
    await plusBtn.click();
    await page.waitForTimeout(1000);
  }

  // Also try right-clicking on a file in the tree
  const fileRow = page.locator('.tree-row[data-file]').first();
  if (await fileRow.count() > 0) {
    await fileRow.click({ button: "right" });
    await page.waitForTimeout(500);
  }

  console.log("\n=== ALL ERRORS AFTER INTERACTION ===");
  errors.forEach((e, i) => {
    console.log(`\n[${i}] ${e.msg}`);
    if (e.stack) console.log(`    ${e.stack}`);
  });

  expect(errors.filter(e => e.msg.includes("onOpenInBrowserTab") || e.msg.includes("onNewBrowserTab"))).toHaveLength(0);
});
