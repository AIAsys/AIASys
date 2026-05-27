import { expect, test } from "@playwright/test";

import {
  addSessionMessage,
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";
import {
  CHUNK_1,
  installMockStreamingResponse,
} from "./streaming-render.mocks";

test.describe("Conversation compact entry browser regression", () => {
  test("input area exposes compact entry and triggers the compact action while idle", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: "浏览器回归-输入区压缩入口",
      initialConversationTitle: "输入区压缩会话",
      mode: "analysis",
    });
    let compactCalls = 0;

    try {
      await addSessionMessage(
        api,
        userId,
        workspace.currentConversationId,
        "这是一条用于 compact 回归的历史消息。",
        "assistant",
      );

      await page.route("**/api/sessions/**/compact", async (route) => {
        compactCalls += 1;
        await page.waitForTimeout(400);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ success: true }),
        });
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const compactButton = page.getByTestId("input-compact-conversation");
      await expect(page.locator("textarea")).toBeVisible();
      await expect(compactButton).toBeVisible();
      await expect(compactButton).toBeEnabled();

      await compactButton.click();
      await expect(compactButton).toBeDisabled();
      await expect(compactButton).toContainText("压缩中");
      await expect
        .poll(() => compactCalls, { timeout: 5_000 })
        .toBe(1);
      await expect(page.getByText("对话上下文已压缩")).toBeVisible({
        timeout: 10_000,
      });
      await expect(compactButton).toBeEnabled();
      await expect(compactButton).toContainText("压缩");
    } finally {
      await page.unroute("**/api/sessions/**/compact");
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("input area keeps compact entry disabled while the current branch is running", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: "浏览器回归-运行中压缩禁用",
      initialConversationTitle: "运行中压缩禁用会话",
      mode: "analysis",
    });

    try {
      await addSessionMessage(
        api,
        userId,
        workspace.currentConversationId,
        "这是一条用于 running 态 compact 禁用验证的历史消息。",
        "assistant",
      );
      await installMockStreamingResponse(page);

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const input = page.locator("textarea");
      const compactButton = page.getByTestId("input-compact-conversation");
      await expect(input).toBeVisible();
      await expect(compactButton).toBeVisible();
      await expect(compactButton).toBeEnabled();

      await input.fill("请模拟一段会让当前会话进入 running 态的流式回复");
      await input.press("Enter");

      await expect(page.getByText(CHUNK_1, { exact: true })).toBeVisible();
      await expect(compactButton).toBeDisabled();

      await expect
        .poll(async () => await input.isEnabled(), { timeout: 10_000 })
        .toBe(true);
      await expect(compactButton).toBeEnabled();
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
