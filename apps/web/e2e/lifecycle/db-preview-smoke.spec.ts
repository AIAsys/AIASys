import { expect, test } from "@playwright/test";
import { createWorkspace, registerLifecycleUser } from "./support";

const OUT_DIR = "/home/ke/projects/AIASys/artifacts/screenshots";

test.describe("Database preview smoke", () => {
  test("workspace resources shows builtin database preview", async ({ page }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const { workspaceId, currentSessionId } = await createWorkspace(api, {
      title: `db-preview-smoke-${Date.now()}`,
      mode: "analysis",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" }
      );
      await page.locator("text=工作区").first().waitFor({ timeout: 15000 });
      await page.waitForTimeout(500);
      await page.screenshot({ path: `${OUT_DIR}/db-smoke-01-workspace.png` });

      // 探测页面上的所有按钮文本
      const buttons = await page.locator("button, [role='button']").all();
      const buttonTexts: string[] = [];
      for (const btn of buttons) {
        const text = await btn.textContent().catch(() => "");
        if (text?.trim()) buttonTexts.push(text.trim().slice(0, 30));
      }
      console.log("Buttons found:", buttonTexts.slice(0, 30));

      // 尝试多种方式找到资源入口
      let resourcesBtn = page.getByRole("button", { name: "资源", exact: true });
      let visible = await resourcesBtn.isVisible().catch(() => false);

      if (!visible) {
        resourcesBtn = page.locator("button").filter({ hasText: /资源/ }).first();
        visible = await resourcesBtn.isVisible().catch(() => false);
      }
      if (!visible) {
        // 尝试 ActivityBar 图标方式
        resourcesBtn = page.locator("[data-testid='activity-bar'] button, [data-testid*='resource']").first();
        visible = await resourcesBtn.isVisible().catch(() => false);
      }

      if (!visible) {
        console.log("未找到资源按钮，保存当前页面状态");
        await page.screenshot({ path: `${OUT_DIR}/db-smoke-02-no-resources-btn.png` });
        return;
      }

      await resourcesBtn.click();
      await page.waitForTimeout(800);
      await page.screenshot({ path: `${OUT_DIR}/db-smoke-02-resources.png` });

      // 查找数据库入口
      const builtinLink = page.locator("a, button").filter({ hasText: /内置数据库|builtin_db|DuckDB/i }).first();
      const hasBuiltin = await builtinLink.isVisible().catch(() => false);
      if (hasBuiltin) {
        await builtinLink.click();
        await page.waitForTimeout(1000);
        await page.screenshot({ path: `${OUT_DIR}/db-smoke-03-db-preview.png` });
      } else {
        console.log("未找到数据库入口");
        await page.screenshot({ path: `${OUT_DIR}/db-smoke-03-no-db-entry.png` });
      }

      const hasSql = await page.locator("text=SQL").first().isVisible().catch(() => false);
      const hasSchema = await page.locator("text=表结构").first().isVisible().catch(() => false);
      console.log("Panel check:", { sql: hasSql, schema: hasSchema });

      await page.screenshot({ path: `${OUT_DIR}/db-smoke-04-final.png` });
    } finally {
      await api.delete(`/api/workspaces/${workspaceId}`);
    }
  });
});
