import { writeFile } from "node:fs/promises";

import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import { createWorkspace, deleteWorkspace, registerLifecycleUser } from "./support";

async function openWorkspaceFilesPanel(page: Page) {
  await expect(page.locator("textarea")).toBeVisible();
  const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
  if (!(await panel.isVisible())) {
    const fileTab = page.locator("button[aria-label='文件']");
    if (await fileTab.isVisible()) {
      await fileTab.click();
    } else {
      await page.getByRole("button", { name: "文件", exact: true }).click();
    }
  }
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("workspace-artifacts-tree-surface")).toBeVisible();
  return panel;
}

async function openGlobalResourcesPanel(page: Page) {
  await expect(page.locator("textarea")).toBeVisible();
  const globalTab = page
    .locator("button[aria-label='全局工作区'], button[aria-label='全局资源']")
    .first();
  if ((await globalTab.count()) > 0 && (await globalTab.isVisible())) {
    await globalTab.click();
  } else {
    await page
      .getByRole("button", { name: "全局工作区", exact: true })
      .or(page.getByRole("button", { name: "全局资源", exact: true }))
      .first()
      .click();
  }
  const panel = page.locator('[data-testid="workspace-global-resources-panel"]');
  await expect(panel).toBeVisible();
  await expect(
    panel.getByTestId("workspace-global-resources-tree-surface"),
  ).toBeVisible();
  return panel;
}

async function deleteGlobalFiles(
  api: APIRequestContext,
  workspaceId: string,
  fileNames: string[],
) {
  await Promise.all(
    fileNames.map((fileName) =>
      api
        .delete(
          `/api/workspaces/${workspaceId}/global-workspace/${encodeURIComponent(fileName)}`,
        )
        .catch(() => null),
    ),
  );
}

test.describe("Workspace artifacts upload flow", () => {
  test("right panel upload enters workspace assets and next-turn attachments", async ({
    page,
  }, testInfo) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-右栏上传-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "右栏上传会话",
    });

    const fixturePath = testInfo.outputPath("right-panel-upload.txt");
    await writeFile(
      fixturePath,
      "right panel upload smoke\n这是一份给工作区资产上传链路使用的测试文件。\n",
      "utf-8",
    );

    let executePayload: Record<string, unknown> | null = null;

    try {
      await page.route("**/api/agent/execute/stream", async (route) => {
        const rawBody = route.request().postData() || "{}";
        executePayload = JSON.parse(rawBody) as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "Cache-Control": "no-cache",
          },
          body:
            'data: {"type":"content","content_type":"text","text":"已收到附件。"}\n\n' +
            "data: [DONE]\n\n",
        });
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const panel = await openWorkspaceFilesPanel(page);

      const fileChooserPromise = page.waitForEvent("filechooser");
      await panel.getByTestId("workspace-artifacts-upload-button").click();
      const chooser = await fileChooserPromise;
      await chooser.setFiles(fixturePath);

      await expect(
        page.getByText("待随下一条消息发送 1 个附件", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("right-panel-upload.txt", { exact: true }).first(),
      ).toBeVisible();

      await page.locator("textarea").fill("请确认你收到了刚上传的文件。");
      await page.locator('button[title="发送"]').click();

      await expect
        .poll(() => executePayload, { timeout: 15_000 })
        .not.toBeNull();

      expect(executePayload?.prompt).toBe("请确认你收到了刚上传的文件。");
      expect(executePayload?.attachments).toEqual([
        "/workspace/right-panel-upload.txt",
      ]);

      await expect(page.getByText("已收到附件。", { exact: true })).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("workspace-artifacts-upload-flow.png"),
        fullPage: true,
      });
    } finally {
      await page.unroute("**/api/agent/execute/stream");
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("right panel paste enters next-turn attachments and outgoing request", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-右栏粘贴-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "右栏粘贴会话",
    });

    let executePayload: Record<string, unknown> | null = null;

    try {
      await page.route("**/api/agent/execute/stream", async (route) => {
        const rawBody = route.request().postData() || "{}";
        executePayload = JSON.parse(rawBody) as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "Cache-Control": "no-cache",
          },
          body:
            'data: {"type":"content","content_type":"text","text":"已收到粘贴附件。"}\n\n' +
            "data: [DONE]\n\n",
        });
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const panel = await openWorkspaceFilesPanel(page);

      await panel.evaluate((panelElement) => {
        const dataTransfer = new DataTransfer();
        const file = new File(
          ["pasted from browser regression"],
          "right-panel-pasted.txt",
          { type: "text/plain" },
        );
        dataTransfer.items.add(file);
        const pasteEvent = new Event("paste", {
          bubbles: true,
          cancelable: true,
          composed: true,
        });
        Object.defineProperty(pasteEvent, "clipboardData", {
          value: dataTransfer,
        });
        panelElement.dispatchEvent(pasteEvent);
      });

      await expect(
        page.getByText("待随下一条消息发送 1 个附件", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("right-panel-pasted.txt", { exact: true }).first(),
      ).toBeVisible();

      await page.locator("textarea").fill("请确认你收到了刚粘贴的文件。");
      await page.locator('button[title="发送"]').click();

      await expect
        .poll(() => executePayload, { timeout: 15_000 })
        .not.toBeNull();

      expect(executePayload?.prompt).toBe("请确认你收到了刚粘贴的文件。");
      expect(executePayload?.attachments).toEqual([
        "/workspace/right-panel-pasted.txt",
      ]);

      await expect(
        page.getByText("已收到粘贴附件。", { exact: true }),
      ).toBeVisible();
    } finally {
      await page.unroute("**/api/agent/execute/stream");
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("right panel drag drop enters next-turn attachments and outgoing request", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-右栏拖拽-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "右栏拖拽会话",
    });

    let executePayload: Record<string, unknown> | null = null;

    try {
      await page.route("**/api/agent/execute/stream", async (route) => {
        const rawBody = route.request().postData() || "{}";
        executePayload = JSON.parse(rawBody) as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "Cache-Control": "no-cache",
          },
          body:
            'data: {"type":"content","content_type":"text","text":"已收到拖拽附件。"}\n\n' +
            "data: [DONE]\n\n",
        });
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const panel = await openWorkspaceFilesPanel(page);

      await panel.evaluate((element) => {
        const dataTransfer = new DataTransfer();
        const file = new File(
          ["dragged from browser regression"],
          "right-panel-dragged.txt",
          { type: "text/plain" },
        );
        dataTransfer.items.add(file);
        element.dispatchEvent(
          new DragEvent("dragenter", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
        element.dispatchEvent(
          new DragEvent("dragover", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
      });

      await expect(
        page.getByText("松开鼠标把文件加入当前会话", { exact: true }),
      ).toBeVisible();

      await panel.evaluate((element) => {
        const dataTransfer = new DataTransfer();
        const file = new File(
          ["dragged from browser regression"],
          "right-panel-dragged.txt",
          { type: "text/plain" },
        );
        dataTransfer.items.add(file);
        element.dispatchEvent(
          new DragEvent("drop", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
      });

      await expect(
        page.getByText("待随下一条消息发送 1 个附件", { exact: true }),
      ).toBeVisible();
      await expect(
        page.getByText("right-panel-dragged.txt", { exact: true }).first(),
      ).toBeVisible();

      await page.locator("textarea").fill("请确认你收到了刚拖拽的文件。");
      await page.locator('button[title="发送"]').click();

      await expect
        .poll(() => executePayload, { timeout: 15_000 })
        .not.toBeNull();

      expect(executePayload?.prompt).toBe("请确认你收到了刚拖拽的文件。");
      expect(executePayload?.attachments).toEqual([
        "/workspace/right-panel-dragged.txt",
      ]);

      await expect(
        page.getByText("已收到拖拽附件。", { exact: true }),
      ).toBeVisible();
    } finally {
      await page.unroute("**/api/agent/execute/stream");
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("composer paste uploads generic files and sends them as next-turn attachments", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-输入框粘贴-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "输入框粘贴会话",
    });

    let executePayload: Record<string, unknown> | null = null;

    try {
      await page.route("**/api/agent/execute/stream", async (route) => {
        const rawBody = route.request().postData() || "{}";
        executePayload = JSON.parse(rawBody) as Record<string, unknown>;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "Cache-Control": "no-cache",
          },
          body:
            'data: {"type":"content","content_type":"text","text":"已收到输入框粘贴附件。"}\n\n' +
            "data: [DONE]\n\n",
        });
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const composer = page.locator("textarea");
      await expect(composer).toBeVisible();

      await composer.evaluate((element) => {
        const dataTransfer = new DataTransfer();
        const file = new File(
          ["pasted from composer regression"],
          "composer-pasted.txt",
          { type: "text/plain" },
        );
        dataTransfer.items.add(file);
        const pasteEvent = new Event("paste", {
          bubbles: true,
          cancelable: true,
          composed: true,
        });
        Object.defineProperty(pasteEvent, "clipboardData", {
          value: dataTransfer,
        });
        element.dispatchEvent(pasteEvent);
      });

      await expect(
        page.getByText("composer-pasted.txt", { exact: true }).first(),
      ).toBeVisible();

      await composer.fill("请确认你收到了输入框里粘贴的文件。");
      await page.locator('button[title="发送"]').click();

      await expect
        .poll(() => executePayload, { timeout: 15_000 })
        .not.toBeNull();

      expect(executePayload?.prompt).toBe("请确认你收到了输入框里粘贴的文件。");
      expect(executePayload?.attachments).toEqual([
        "/workspace/composer-pasted.txt",
      ]);

      await expect(
        page.getByText("已收到输入框粘贴附件。", { exact: true }),
      ).toBeVisible();
    } finally {
      await page.unroute("**/api/agent/execute/stream");
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("global workspace file tree accepts button paste and drag uploads", async ({
    page,
  }, testInfo) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-全局上传-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "全局上传会话",
    });

    const suffix = `${Date.now()}`;
    const buttonFileName = `global-button-upload-${suffix}.txt`;
    const pastedFileName = `global-pasted-upload-${suffix}.txt`;
    const draggedFileName = `global-dragged-upload-${suffix}.txt`;
    const uploadedFileNames = [buttonFileName, pastedFileName, draggedFileName];
    const buttonFixturePath = testInfo.outputPath(buttonFileName);
    await writeFile(buttonFixturePath, "global button upload smoke\n", "utf-8");

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        {
          waitUntil: "domcontentloaded",
        },
      );

      const panel = await openGlobalResourcesPanel(page);

      const fileChooserPromise = page.waitForEvent("filechooser");
      await panel.getByTestId("workspace-global-resources-upload-button").click();
      const chooser = await fileChooserPromise;
      await chooser.setFiles(buttonFixturePath);
      await expect(panel.getByText(buttonFileName, { exact: true })).toBeVisible();

      await panel.evaluate((panelElement, name) => {
        const dataTransfer = new DataTransfer();
        const file = new File(["global pasted upload smoke\n"], name, {
          type: "text/plain",
        });
        dataTransfer.items.add(file);
        const pasteEvent = new Event("paste", {
          bubbles: true,
          cancelable: true,
          composed: true,
        });
        Object.defineProperty(pasteEvent, "clipboardData", {
          value: dataTransfer,
        });
        panelElement.dispatchEvent(pasteEvent);
      }, pastedFileName);
      await expect(panel.getByText(pastedFileName, { exact: true })).toBeVisible();

      await panel.evaluate((element, name) => {
        const dataTransfer = new DataTransfer();
        const file = new File(["global dragged upload smoke\n"], name, {
          type: "text/plain",
        });
        dataTransfer.items.add(file);
        element.dispatchEvent(
          new DragEvent("dragenter", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
        element.dispatchEvent(
          new DragEvent("dragover", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
      }, draggedFileName);

      await expect(
        page.getByText("松开鼠标把文件加入全局工作区", { exact: true }),
      ).toBeVisible();

      await panel.evaluate((element, name) => {
        const dataTransfer = new DataTransfer();
        const file = new File(["global dragged upload smoke\n"], name, {
          type: "text/plain",
        });
        dataTransfer.items.add(file);
        element.dispatchEvent(
          new DragEvent("drop", {
            bubbles: true,
            cancelable: true,
            dataTransfer,
          }),
        );
      }, draggedFileName);
      await expect(panel.getByText(draggedFileName, { exact: true })).toBeVisible();

      for (const fileName of uploadedFileNames) {
        const response = await api.get(
          `/api/workspaces/${workspace.workspaceId}/global-workspace/content/${encodeURIComponent(fileName)}`,
        );
        expect(response.ok()).toBeTruthy();
      }

      await page.screenshot({
        path: testInfo.outputPath("global-workspace-upload-flow.png"),
        fullPage: true,
      });
    } finally {
      await deleteGlobalFiles(api, workspace.workspaceId, uploadedFileNames);
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
