import { test, expect } from "@playwright/test";

test("debug onOpenInBrowserTab error", async ({ page }) => {
  const errors: { msg: string; url?: string; line?: number; stack?: string }[] = [];

  page.on("pageerror", (err) => {
    errors.push({ msg: err.message, stack: err.stack?.split("\n").slice(0, 6).join("\n") });
  });
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      const loc = msg.location();
      errors.push({
        msg: msg.text(),
        url: loc?.url,
        line: loc?.lineNumber,
        stack: msg.stacktrace()?.slices.slice(0, 5).map((s) => `${s.function}:${s.line}:${s.column}`).join("\n"),
      });
    }
  });

  await page.goto("http://localhost:13000", { waitUntil: "networkidle" });
  await page.waitForTimeout(5000);

  console.log("\n=== ALL ERRORS ===");
  errors.forEach((e, i) => {
    console.log(`\n[${i}] ${e.msg}`);
    if (e.url) console.log(`    at ${e.url}:${e.line}`);
    if (e.stack) console.log(`    stack: ${e.stack}`);
  });

  // Also check if onOpenInBrowserTab exists anywhere in the page JS
  const hasDefined = await page.evaluate(() => {
    // Try to find the function by checking if it's referenced in any script
    const scripts = Array.from(document.querySelectorAll("script"));
    let found = false;
    for (const s of scripts) {
      if (s.textContent?.includes("onOpenInBrowserTab is not defined")) {
        found = true;
        break;
      }
    }
    return found;
  });
  console.log("\nHas 'is not defined' in page scripts:", hasDefined);
});
