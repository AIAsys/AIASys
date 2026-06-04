import { expect, test } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test.describe("Workspace file main canvas editor", () => {
  test.setTimeout(180_000);

  test("opens editable files in the main canvas with split preview and saves through the file API", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-主画布编辑-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "主画布编辑会话",
    });
    const fileName = "main-canvas-edit-smoke.py";

    try {
      const createResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: fileName,
            content: "print('before main canvas editor')\n",
            overwrite: true,
          },
        },
      );
      expect(createResponse.ok()).toBeTruthy();

      const listResponse = await api.get(
        `/api/workspaces/${workspace.workspaceId}/files/list?recursive=true`,
      );
      expect(listResponse.ok()).toBeTruthy();
      const listBody = (await listResponse.json()) as {
        files: Array<{ name?: string; path?: string }>;
      };
      expect(
        listBody.files.some(
          (file) => file.name === fileName || file.path === `/workspace/${fileName}`,
        ),
      ).toBeTruthy();

      const legacyListResponse = await api.get(
        `/api/files/list/local_default/${workspace.currentConversationId}`,
        {
          failOnStatusCode: false,
        },
      );
      expect(legacyListResponse.status()).toBe(404);

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      await page.getByRole("button", { name: "当前工作区", exact: true }).click();

      const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
      await expect(panel).toBeVisible();
      await expect(panel.getByTestId("workspace-artifacts-tab-global-assets")).toHaveCount(0);
      await expect(panel.getByText(fileName, { exact: true })).toBeVisible();

      await panel
        .getByRole("button", {
          name: `打开 ${fileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();
      await expect(page.getByRole("heading", { name: fileName })).toBeVisible();
      await expect(
        page.getByText("before main canvas editor", { exact: false }),
      ).toBeVisible();

      await panel
        .getByRole("button", {
          name: `打开 ${fileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "编辑文件" }).click();

      const editor = page.getByTestId("workspace-code-editor");
      await expect(editor).toBeVisible();
      await expect(page.locator(".fixed.right-0.w-\\[500px\\]")).toHaveCount(0);

      const editableContent = editor.locator(".cm-content[contenteditable='true']");
      await expect(editableContent).toBeVisible();
      await editableContent.click();
      await page.keyboard.press(process.platform === "darwin" ? "Meta+A" : "Control+A");
      await page.keyboard.type("print('saved from main canvas editor')\n");

      await expect(
        editor
          .locator(".cm-content")
          .getByText("saved from main canvas editor", { exact: false })
          .first(),
      ).toBeVisible();

      await page.getByRole("button", { name: "保存", exact: true }).click();
      await expect(page.getByText("已同步", { exact: true })).toBeVisible();

      const response = await api.get(
        `/api/workspaces/${workspace.workspaceId}/files/content/${fileName}`,
      );
      expect(response.ok()).toBeTruthy();
      const body = (await response.json()) as { content: string };
      expect(body.content).toContain("saved from main canvas editor");

      await page.screenshot({
        path: testInfo.outputPath("workspace-file-main-canvas-editor.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
