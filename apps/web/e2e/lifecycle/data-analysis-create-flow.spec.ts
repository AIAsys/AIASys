import { expect, test } from "@playwright/test";

import { gotoAnalysisSession } from "./data-analysis-helpers";
import {
  createSession,
  createWorkspace,
  deleteSession,
  deleteWorkspace,
  extractSessionIdFromUrl,
  extractWorkspaceIdFromUrl,
  registerLifecycleUser,
} from "./support";

test.describe("DataAnalysis create flow browser regression", () => {
  test("empty session shows the workspace startup panel instead of legacy execution-space entry", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const sessionId = await createSession(api, {
      title: "浏览器回归-工作区启动面板",
      sandboxMode: "local",
    });

    try {
      await gotoAnalysisSession(page, sessionId);

      await expect(page.getByText("工作区启动面板", { exact: true })).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "从一个工作区开始" }),
      ).toBeVisible();
      await expect(page.getByText("还没有工作区", { exact: true })).toBeVisible();
      await expect(page.getByText("先创建一个长期任务工作区，后续再在里面展开多个会话、资源范围和执行记录。")).toBeVisible();
      await expect(page.getByRole("button", { name: /查看执行详情/i })).toHaveCount(0);
    } finally {
      await deleteSession(api, userId, sessionId);
    }
  });

  test("new task dialog uses workspace basics instead of legacy sandbox controls", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const sessionId = await createSession(api, {
      title: "浏览器回归-新建任务弹窗",
      sandboxMode: "local",
    });

    try {
      await gotoAnalysisSession(page, sessionId);
      await page.getByTestId("sidebar-new-task-expanded").click();

      const dialog = page.getByRole("dialog").filter({ hasText: "新建任务" });
      await expect(dialog).toBeVisible();
      await expect(dialog.getByLabel("任务名称")).toBeVisible();
      await expect(dialog.getByLabel("任务说明")).toBeVisible();
      await expect(dialog.getByRole("button", { name: "创建任务" })).toBeDisabled();

      await expect(dialog.getByText("选择沙盒模式")).toHaveCount(0);
      await expect(dialog.getByText("默认连续", { exact: true })).toHaveCount(0);
      await expect(dialog.getByText("清空当前对话", { exact: true })).toHaveCount(0);
      await expect(dialog.getByRole("heading", { name: "本地沙盒" })).toHaveCount(0);
      await expect(dialog.getByRole("heading", { name: "Docker 沙盒" })).toHaveCount(0);
    } finally {
      await deleteSession(api, userId, sessionId);
    }
  });

  test("creating a new task activates a workspace route and keeps the new branch usable", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const sourceSessionId = await createSession(api, {
      title: "浏览器回归-创建任务源会话",
      sandboxMode: "local",
    });
    const workspaceTitle = `浏览器回归-新建任务-${Date.now()}`;
    let createdWorkspaceId: string | null = null;
    let createdSessionId: string | null = null;

    try {
      await gotoAnalysisSession(page, sourceSessionId);
      await page.getByTestId("sidebar-new-task-expanded").click();

      const dialog = page.getByRole("dialog").filter({ hasText: "新建任务" });
      await expect(dialog).toBeVisible();
      await dialog.getByLabel("任务名称").fill(workspaceTitle);
      await dialog.getByLabel("任务说明").fill("正式验证 workspace-first 新建任务流。");
      await dialog.getByRole("button", { name: "创建任务" }).click();

      await expect
        .poll(() => extractWorkspaceIdFromUrl(page.url()), { timeout: 30_000 })
        .not.toBeNull();

      createdWorkspaceId = extractWorkspaceIdFromUrl(page.url());
      createdSessionId = extractSessionIdFromUrl(page.url());
      expect(createdWorkspaceId).toBeTruthy();
      expect(createdSessionId).toBeTruthy();

      await expect(page.getByText("当前工作区", { exact: true })).toBeVisible();
      await expect(
        page.getByRole("button", { name: workspaceTitle }).first(),
      ).toBeVisible();
      await expect(page.locator("textarea")).toBeEnabled();
    } finally {
      await deleteWorkspace(api, createdWorkspaceId);
      await deleteSession(api, userId, createdSessionId);
      await deleteSession(api, userId, sourceSessionId);
    }
  });

  test("new workspace conversations expose workspace config assets immediately", async ({
    page,
  }) => {
    const api = page.request;
    const { workspaceId, currentConversationId } = await createWorkspace(api, {
      title: `浏览器回归-工作区偏好文件-${Date.now()}`,
      mode: "analysis",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspaceId}&session_id=${currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      await expect(page.getByRole("button", { name: "资产", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "资产", exact: true }).click();
      await expect(page.getByText("工作区资产", { exact: true })).toBeVisible();
      await expect(page.getByText("1 文件", { exact: true })).toBeVisible();
      await expect(page.getByText("config", { exact: true })).toBeVisible();
    } finally {
      await deleteWorkspace(api, workspaceId);
    }
  });
});
