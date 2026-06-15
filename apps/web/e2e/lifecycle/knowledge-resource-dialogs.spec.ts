import { expect, test } from "@playwright/test";

import {
  buildAnalysisUrl,
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test.describe("Workspace resource entries", () => {
  test("workspace resource entry moves from sidebar gear dialogs into the analysis canvas", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: "浏览器回归-知识资源入口",
      initialConversationTitle: "知识资源入口会话",
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

      // 点击侧边栏齿轮直接打开全局控制面板，知识资源入口不再出现在齿轮菜单中
      await page.getByTestId("sidebar-workspace-tools-menu-trigger").click();
      await expect(page.getByTestId("global-settings-dialog")).toBeVisible();
      await expect(
        page.getByRole("button", { name: "资源管理", exact: true }),
      ).toHaveCount(0);
      await page.keyboard.press("Escape");

      await page.getByRole("button", { name: "数据查询", exact: true }).click();
      await expect(page).toHaveURL(
        new RegExp(`/workspace\\?workspace_id=${workspace.workspaceId}`),
      );
      await expect(
        page.getByText("数据库连接", { exact: true }).first(),
      ).toBeVisible();
      await expect(
        page.getByText(/暂无外部数据库连接|添加外部数据库/).first(),
      ).toBeVisible();
      await expect(
        page.getByRole("dialog", { name: "资源管理", exact: true }),
      ).toHaveCount(0);
      await expect(
        page.getByTestId("resource-management-dialog-tab-knowledge_base"),
      ).toHaveCount(0);
      await expect(
        page.getByTestId("resource-management-dialog-tab-knowledge_graph"),
      ).toHaveCount(0);
      await expect(
        page.getByTestId("resource-management-dialog-tab-database"),
      ).toHaveCount(0);
      await expect(
        page.getByRole("button", { name: "当前工作区", exact: true }).first(),
      ).toBeVisible();
      await expect(
        page.getByRole("button", { name: "数据查询", exact: true }).first(),
      ).toBeVisible();
      await page.getByRole("button", { name: "当前工作区", exact: true }).first().click();
      await expect(
        page.locator('[data-testid="workspace-artifacts-panel"]'),
      ).toBeVisible();
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
