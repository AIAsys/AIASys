import { expect, test } from "@playwright/test";

import {
  buildAnalysisUrl,
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test.describe("AutoTask management entry", () => {
  test("opens both global auto task management and the workspace auto task view", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: "浏览器回归-自动化任务管理入口",
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

      // 全局自动化任务入口：点击侧边栏齿轮直接打开全局控制面板，再导航到自动化任务
      await page.getByTestId("sidebar-workspace-tools-menu-trigger").click();
      await expect(page.getByTestId("global-settings-dialog")).toBeVisible();
      await page.getByTestId("global-settings-nav-auto-tasks").click();
      await expect(
        page.getByRole("heading", { name: "全局自动化任务", exact: true }),
      ).toBeVisible();
      await expect(
        page.getByTestId("global-settings-nav-auto-tasks"),
      ).toHaveAttribute("aria-current", "page");
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
