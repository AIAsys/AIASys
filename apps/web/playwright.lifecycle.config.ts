import { defineConfig } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");
const baseURL = process.env.PLAYWRIGHT_BASE_URL || "http://localhost:13000";

export default defineConfig({
  testDir: "./e2e/lifecycle",
  fullyParallel: false,
  workers: 1,
  timeout: 120_000,
  expect: {
    timeout: 15_000,
  },
  outputDir: "./test-results/lifecycle",
  reporter: [
    ["list"],
    ["html", { open: "never", outputFolder: "./playwright-report/lifecycle" }],
  ],
  use: {
    baseURL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "retain-on-failure",
  },
  webServer: {
    command: "./dev.sh",
    cwd: repoRoot,
    url: baseURL,
    reuseExistingServer: true,
    timeout: 240_000,
    stdout: "pipe",
    stderr: "pipe",
  },
});
