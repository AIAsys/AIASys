import { expect, test } from "@playwright/test";

import { buildAnalysisUrl, createWorkspace, deleteWorkspace, registerLifecycleUser } from "./support";

test.describe("LLM scope settings", () => {
  test("sidebar gear opens global LLM config directly", async ({ page }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `LLM 分层设置回归-${Date.now()}`,
    });

    try {
      await page.goto(
        buildAnalysisUrl({
          workspaceId: workspace.workspaceId,
          conversationId: workspace.currentConversationId,
        }),
        {
          waitUntil: "domcontentloaded",
        },
      );

      await expect(page.locator("textarea")).toBeVisible();

      // 点击侧边栏齿轮直接打开全局控制面板（默认模型配置）
      await page.getByTestId("sidebar-workspace-tools-menu-trigger").click();
      await expect(page.getByTestId("global-settings-dialog")).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "模型配置", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByTestId("global-settings-nav-llm"),
      ).toHaveAttribute("aria-current", "page");
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
