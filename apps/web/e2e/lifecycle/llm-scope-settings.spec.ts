import { expect, test } from "@playwright/test";

import { createWorkspace, deleteWorkspace, registerLifecycleUser } from "./support";

test.describe("LLM scope settings", () => {
  test("sidebar workspace settings entry opens global LLM config and session config exposes model routing", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `LLM 分层设置回归-${Date.now()}`,
      mode: "analysis",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      await expect(
        page.getByText("工作区摘要", { exact: true }),
      ).toBeVisible();

      // 1. 全局模型配置入口：侧边栏工具菜单 -> 模型配置
      await page.getByTestId("sidebar-workspace-tools-menu-trigger").click();
      await page.getByTestId("sidebar-workspace-tools-llm-config").click();
      await expect(
        page.getByRole("heading", { name: "全局控制面板" }),
      ).toBeVisible();

      // 关闭全局面板
      await page.keyboard.press("Escape");
      await page.waitForTimeout(300);

      // 2. 会话级配置入口：输入框工具配置按钮
      await page.getByTestId("input-tool-config").click();
      const sessionDialog = page.getByRole("dialog").filter({
        hasText: "当前会话配置",
      });
      await expect(sessionDialog).toBeVisible();
      await expect(
        sessionDialog.getByText("任务模型路由", { exact: true }).or(
          sessionDialog.getByText("当前还没有可用的模型链路信息。"),
        ),
      ).toBeVisible();
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
