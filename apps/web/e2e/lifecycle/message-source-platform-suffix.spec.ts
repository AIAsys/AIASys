import { expect, test } from "@playwright/test";

import {
  addSessionMessage,
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test("chat history shows platform source as plain message suffix", async ({
  page,
}) => {
  const api = page.request;
  const { userId } = await registerLifecycleUser(api);
  const workspace = await createWorkspace(api, {
    title: `来源平台尾标回归-${Date.now()}`,
    mode: "analysis",
    initialConversationTitle: "来源平台尾标会话",
  });

  try {
    await addSessionMessage(
      api,
      userId,
      workspace.currentSessionId,
      "这条消息是从微信进来的。\n\n（来自微信）",
      "user",
    );
    await addSessionMessage(
      api,
      userId,
      workspace.currentSessionId,
      "已看到来源尾标测试消息。",
      "assistant",
    );

    await page.goto(
      `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
      {
        waitUntil: "domcontentloaded",
      },
    );

    await expect(page.locator("textarea")).toBeVisible();
    await expect(
      page.getByText("这条消息是从微信进来的。"),
    ).toBeVisible();
    await expect(page.getByText("（来自微信）")).toBeVisible();
    await expect(
      page.getByText("已看到来源尾标测试消息。", { exact: true }),
    ).toBeVisible();
  } finally {
    await deleteWorkspace(api, workspace.workspaceId);
  }
});
