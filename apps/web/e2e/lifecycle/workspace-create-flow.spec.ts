import { expect, test } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  extractSessionIdFromUrl,
  extractWorkspaceIdFromUrl,
  registerLifecycleUser,
} from "./support";

// 新建工作区核心旅程的浏览器回归。
// 历史说明：旧版断言过「工作区启动面板」「资产」按钮，产品改版后这些入口已移除，
// 2026-07 按当前 UX 重写：弹窗基本信息创建 → 路由进入新工作区 → 会话立即可用。
test.describe("Workspace create flow browser regression", () => {
  test("new workspace dialog uses workspace basics instead of legacy sandbox controls", async ({
    page,
  }) => {
    const api = page.request;
    const { workspaceId, currentSessionId } = await createWorkspace(api, {
      title: `浏览器回归-新建工作区弹窗-${Date.now()}`,
    });

    try {
      await page.goto(
        `/workspace?workspace_id=${workspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      await page.getByTestId("sidebar-new-task-expanded").click();

      const dialog = page.getByRole("dialog").filter({ hasText: "新建工作区" });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByLabel("任务名称")).toBeVisible();
      await expect(dialog.getByLabel("任务说明")).toBeVisible();
      // 未填名称时创建按钮不可用
      await expect(
        dialog.getByRole("button", { name: "创建工作区" }),
      ).toBeDisabled();

      // 历史遗留的沙盒控件不应再出现
      await expect(dialog.getByText("选择沙盒模式")).toHaveCount(0);
      await expect(
        dialog.getByRole("heading", { name: "本地沙盒" }),
      ).toHaveCount(0);
      await expect(
        dialog.getByRole("heading", { name: "Docker 沙盒" }),
      ).toHaveCount(0);

      await dialog.getByRole("button", { name: "取消" }).click();
    } finally {
      await deleteWorkspace(api, workspaceId);
    }
  });

  test("creating a workspace from the dialog lands on a usable workspace route", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const { workspaceId: sourceWorkspaceId, currentSessionId } =
      await createWorkspace(api, {
        title: `浏览器回归-新建工作区来源-${Date.now()}`,
      });
    const workspaceTitle = `浏览器回归-新建工作区-${Date.now()}`;
    let createdWorkspaceId: string | null = null;

    try {
      await page.goto(
        `/workspace?workspace_id=${sourceWorkspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      await page.getByTestId("sidebar-new-task-expanded").click();
      const dialog = page.getByRole("dialog").filter({ hasText: "新建工作区" });
      await expect(dialog).toBeVisible();
      await dialog.getByLabel("任务名称").fill(workspaceTitle);
      await dialog.getByLabel("任务说明").fill("浏览器回归：验证新建工作区核心旅程。");
      await dialog.getByRole("button", { name: "创建工作区" }).click();

      // 默认会创建 uv Python 环境，给足创建时间；
      // 注意轮询必须排除来源工作区，否则首页 URL 里已有的 id 会让断言立即误判通过
      await expect
        .poll(
          () => {
            const id = extractWorkspaceIdFromUrl(page.url());
            return id && id !== sourceWorkspaceId ? id : null;
          },
          { timeout: 90_000 },
        )
        .not.toBeNull();
      createdWorkspaceId = extractWorkspaceIdFromUrl(page.url());
      expect(createdWorkspaceId).toBeTruthy();

      // 新工作区路由下会话立即可用：输入框可用，且新会话元数据已创建（tokens 不 404）
      await expect(page.locator("textarea")).toBeEnabled();
      const newSessionId = extractSessionIdFromUrl(page.url());
      expect(newSessionId).toBeTruthy();
      const tokensResponse = await api.get(`/api/${userId}/${newSessionId}/tokens`);
      expect(tokensResponse.ok()).toBeTruthy();

      // 侧边栏工作区列表出现新工作区
      await expect(
        page.getByRole("button", { name: workspaceTitle }).first(),
      ).toBeVisible();
    } finally {
      await deleteWorkspace(api, createdWorkspaceId);
      await deleteWorkspace(api, sourceWorkspaceId);
    }
  });
});
