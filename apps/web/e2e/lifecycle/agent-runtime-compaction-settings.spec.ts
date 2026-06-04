import { expect, test } from "@playwright/test";

import { createWorkspace, deleteWorkspace, registerLifecycleUser } from "./support";

test.describe("Agent runtime compaction settings", () => {
  test("branch settings can save runtime compaction overrides and reload them", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `自动压缩策略回归-${Date.now()}`,
      mode: "analysis",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      await page.getByTestId("input-tool-config").click();
      const sessionDialog = page.getByRole("dialog").filter({
        hasText: "当前会话配置",
      });
      await expect(sessionDialog).toBeVisible();

      const reservedInput = sessionDialog.getByTestId(
        "agent-runtime-reserved-context-size",
      );
      const ratioInput = sessionDialog.getByTestId(
        "agent-runtime-compaction-trigger-ratio",
      );
      const saveButton = sessionDialog.getByTestId("agent-runtime-save");

      await expect(reservedInput).toHaveValue("50000");
      await expect(ratioInput).toHaveValue("0.85");

      await reservedInput.fill("32000");
      await ratioInput.fill("0.67");
      await saveButton.scrollIntoViewIfNeeded();
      const saveRequest = page.waitForResponse((response) => {
        return (
          response.url().includes("/api/agent-config/analysis/runtime") &&
          response.request().method() === "PUT"
        );
      });
      await saveButton.evaluate((node: HTMLElement) => node.click());
      const saveResponse = await saveRequest;
      expect(saveResponse.ok()).toBeTruthy();

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/agent-config/analysis/editor?session_id=${workspace.currentConversationId}`,
          );
          const payload = (await response.json()) as {
            reserved_context_size: number;
            compaction_trigger_ratio: number;
            runtime_source: string;
            has_local_runtime_override: boolean;
          };
          return JSON.stringify(payload);
        })
        .toContain('"reserved_context_size":32000');

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/agent-config/analysis/editor?session_id=${workspace.currentConversationId}`,
          );
          const payload = (await response.json()) as {
            reserved_context_size: number;
            compaction_trigger_ratio: number;
            runtime_source: string;
            has_local_runtime_override: boolean;
          };
          return [
            payload.compaction_trigger_ratio,
            payload.runtime_source,
            payload.has_local_runtime_override,
          ].join("|");
        })
        .toBe("0.67|session_override|true");

      await page.reload({ waitUntil: "domcontentloaded" });
      await page.getByTestId("input-tool-config").click();

      const reloadedDialog = page.getByRole("dialog").filter({
        hasText: "当前会话配置",
      });
      await expect(reloadedDialog).toBeVisible();
      await expect(
        reloadedDialog.getByTestId("agent-runtime-reserved-context-size"),
      ).toHaveValue("32000");
      await expect(
        reloadedDialog.getByTestId("agent-runtime-compaction-trigger-ratio"),
      ).toHaveValue("0.67");
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
