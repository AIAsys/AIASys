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
      initialConversationTitle: "自动化任务管理入口会话",
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

      await page.getByTestId("sidebar-workspace-tools-menu-trigger").click();
      await page.getByText("全局任务管理", { exact: true }).click();
      await page
        .getByTestId("sidebar-workspace-tools-auto-task-management")
        .click();
      await expect(
        page.getByRole("heading", { name: "全局自动化任务管理", exact: true }),
      ).toBeVisible();
      await page.keyboard.press("Escape");

      await page.getByRole("button", { name: "自动化任务", exact: true }).click();
      await expect(
        page.getByText("当前工作区还没有自动化任务", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "新建自动化任务" }),
      ).toBeVisible();

      await page.getByRole("button", { name: "新建自动化任务" }).click();
      await page.getByText("连续推进", { exact: true }).click();
      await expect(page.getByText("停止条件", { exact: true })).toBeVisible();
      await expect(
        page.getByText("预算耗尽时停止", { exact: true }),
      ).toHaveCount(0);
      await expect(page.getByText("预算耗尽", { exact: true })).toHaveCount(0);
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
