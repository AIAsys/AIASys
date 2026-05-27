import { expect, test } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test.describe("Workspace file read and edit modes", () => {
  test.setTimeout(240_000);

  test("keeps code preview and edit mode on the same editor surface while Markdown opens rendered", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    const user = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件读写模式-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件读写模式会话",
    });

    const codeFileName = "read-edit-scroll-smoke.py";
    const markdownFileName = "read-edit-markdown-smoke.md";
    const linkedMarkdownFileName = "read-edit-linked-target.md";
    const codeContent = Array.from(
      { length: 160 },
      (_, index) => `print("line ${String(index + 1).padStart(3, "0")}")`,
    ).join("\n");

    try {
      const createCodeFile = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: codeFileName,
            content: `${codeContent}\n`,
            overwrite: true,
          },
        },
      );
      expect(createCodeFile.ok()).toBeTruthy();

      const createMarkdownFile = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: markdownFileName,
            content: [
              "---",
              "id: mem_frontmatter_smoke",
              "scope: workspace",
              "user_id: local_default",
              "status: active",
              "---",
              "",
              "# Markdown Render Smoke",
              "",
              "This paragraph should render as a document.",
              "",
              `[Linked target](/workspace/${linkedMarkdownFileName})`,
              "",
            ].join("\n"),
            overwrite: true,
          },
        },
      );
      expect(createMarkdownFile.ok()).toBeTruthy();

      const createLinkedMarkdownFile = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: linkedMarkdownFileName,
            content: "# Linked Markdown Target\n\nOpened from Markdown preview.\n",
            overwrite: true,
          },
        },
      );
      expect(createLinkedMarkdownFile.ok()).toBeTruthy();

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
      if ((await panel.count()) === 0 || !(await panel.isVisible())) {
        const fileTab = page.locator("button[aria-label='文件']");
        if (await fileTab.isVisible()) {
          await fileTab.click();
        } else {
          await page.getByRole("button", { name: "当前工作区", exact: true }).click();
        }
      }
      await expect(panel).toBeVisible();
      await panel.getByPlaceholder("搜索文件或目录...").fill(codeFileName);
      await expect(panel.getByText(codeFileName, { exact: true })).toBeVisible();

      await panel
        .getByRole("button", {
          name: `打开 ${codeFileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();

      await expect(page.getByRole("heading", { name: codeFileName })).toBeVisible();
      await expect(page.getByText(`当前工作区 / ${codeFileName}`)).toBeVisible();
      await expect(page.getByText("分析产物")).toHaveCount(0);
      await expect(page.getByText("报告材料")).toHaveCount(0);
      await expect(page.getByText("索引已同步")).toHaveCount(0);
      const mainCanvas = page.getByTestId("canvas-drop-zone");
      await mainCanvas.getByRole("button", { name: "更多操作" }).click();
      await expect(page.getByRole("menuitem", { name: "沉浸预览" })).toBeVisible();
      await page.getByRole("menuitem", { name: "沉浸预览" }).click();
      const immersivePreview = page.getByTestId("immersive-file-preview");
      await expect(immersivePreview).toBeVisible();
      await expect(
        immersivePreview.getByRole("heading", { name: codeFileName }),
      ).toBeVisible();
      const immersiveBox = await immersivePreview.boundingBox();
      expect(immersiveBox?.x).toBeLessThanOrEqual(1);
      expect(immersiveBox?.y).toBeLessThanOrEqual(1);
      expect(immersiveBox?.width).toBeGreaterThanOrEqual(1438);
      expect(immersiveBox?.height).toBeGreaterThanOrEqual(898);
      await page.screenshot({
        path: testInfo.outputPath("immersive-file-preview.png"),
        fullPage: true,
      });
      await immersivePreview.getByRole("button", { name: "退出沉浸预览" }).click();
      await expect(immersivePreview).toHaveCount(0);
      await mainCanvas.getByRole("button", { name: "更多操作" }).click();
      await page.getByRole("menuitem", { name: "沉浸预览" }).click();
      await expect(immersivePreview).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(immersivePreview).toHaveCount(0);
      await expect(page.getByText("文件信息")).toHaveCount(0);
      await mainCanvas.getByRole("button", { name: "更多操作" }).click();
      await page.getByRole("menuitem", { name: "查看文件信息" }).click();
      await expect(page.getByText("文件信息")).toBeVisible();
      await expect(page.getByText("本地属性")).toBeVisible();
      await expect(page.getByText("来源运行")).toHaveCount(0);
      await expect(page.getByText("本会话产物")).toHaveCount(0);
      await page.screenshot({
        path: testInfo.outputPath("local-file-info-panel.png"),
        fullPage: true,
      });
      await page.getByRole("button", { name: "关闭文件信息" }).click();
      const readOnlyEditor = page.getByTestId("workspace-code-editor").first();
      await expect(readOnlyEditor).toBeVisible();
      await expect(readOnlyEditor.locator(".cm-content[contenteditable='false']")).toBeVisible();
      await expect(readOnlyEditor.getByText('print("line 001")')).toBeVisible();

      await readOnlyEditor.locator(".cm-scroller").evaluate((node) => {
        node.scrollTop = node.scrollHeight;
      });
      await expect(readOnlyEditor.getByText('print("line 160")')).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("code-read-mode-scroll-bottom.png"),
        fullPage: true,
      });

      await panel
        .getByRole("button", {
          name: `打开 ${codeFileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "编辑文件" }).click();

      const editableContent = page.locator(".cm-content[contenteditable='true']").first();
      await expect(page.getByTestId("workspace-code-editor").first()).toBeVisible();
      await expect(editableContent).toBeVisible();

      await panel.getByPlaceholder("搜索文件或目录...").fill(markdownFileName);
      await expect(panel.getByText(markdownFileName, { exact: true })).toBeVisible();
      await panel
        .getByRole("button", {
          name: `打开 ${markdownFileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();

      await expect(page.getByRole("heading", { name: markdownFileName })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Markdown Render Smoke" })).toBeVisible();
      await expect(page.getByText("# Markdown Render Smoke")).toHaveCount(0);
      await expect(page.getByText("id: mem_frontmatter_smoke")).toHaveCount(0);
      await expect(page.getByText("scope: workspace")).toHaveCount(0);
      await page.getByRole("button", { name: "Linked target" }).click();
      await expect(
        page.getByRole("heading", { name: linkedMarkdownFileName }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Linked Markdown Target" }),
      ).toBeVisible();
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("shows a rendering state while HTML preview iframe is still loading", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    await registerLifecycleUser(page.request);
    const workspace = await createWorkspace(page.request, {
      title: `浏览器回归-HTML预览加载态-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "HTML 预览加载态会话",
    });

    const htmlFileName = "html-rendering-state-smoke.html";
    const slowStylePath = "/slow-html-preview-style.css";
    const htmlContent = [
      "<!doctype html>",
      '<html lang="zh-CN">',
      "<head>",
      '<meta charset="utf-8" />',
      `<link rel="stylesheet" href="${slowStylePath}" />`,
      "<title>HTML Rendering Smoke</title>",
      "</head>",
      "<body>",
      "<main>HTML iframe rendered marker</main>",
      "</body>",
      "</html>",
    ].join("\n");

    await page.route(`**${slowStylePath}`, async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 6_000));
      await route.fulfill({
        status: 200,
        contentType: "text/css",
        body: "body{font-family:sans-serif;background:#ffffff;color:#111827}",
      });
    });

    try {
      const createHtmlFile = await page.request.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: htmlFileName,
            content: htmlContent,
            overwrite: true,
          },
        },
      );
      expect(createHtmlFile.ok()).toBeTruthy();

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
      if ((await panel.count()) === 0 || !(await panel.isVisible())) {
        const fileTab = page.locator("button[aria-label='文件']");
        if (await fileTab.isVisible()) {
          await fileTab.click();
        } else {
          await page.getByRole("button", { name: "当前工作区", exact: true }).click();
        }
      }
      await expect(panel).toBeVisible();
      await panel.getByPlaceholder("搜索文件或目录...").fill(htmlFileName);
      await expect(panel.getByText(htmlFileName, { exact: true })).toBeVisible();

      await panel
        .getByRole("button", {
          name: `打开 ${htmlFileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();

      await expect(page.getByRole("heading", { name: htmlFileName })).toBeVisible();
      await expect(page.getByTestId("html-preview-rendering")).toBeVisible();
      await expect(page.getByTestId("html-preview-rendering")).toContainText(
        "正在渲染 HTML 预览",
      );
      await page.screenshot({
        path: testInfo.outputPath("html-preview-rendering-state.png"),
        fullPage: true,
      });
      await expect(page.getByTestId("html-preview-rendering")).toBeHidden();
      await expect(
        page.frameLocator("[data-testid='html-preview-frame']").getByText(
          "HTML iframe rendered marker",
        ),
      ).toBeVisible();
    } finally {
      await deleteWorkspace(page.request, workspace.workspaceId);
    }
  });
});
