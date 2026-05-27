import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

async function openWorkspaceFilesPanel(page: Page) {
  await expect(page.locator("textarea")).toBeVisible();
  const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
  if (!(await panel.isVisible())) {
    const fileTab = page.locator("button[aria-label='文件']");
    if (await fileTab.isVisible()) {
      await fileTab.click();
    } else {
      await page.getByRole("button", { name: "资产", exact: true }).click();
    }
  }
  await expect(panel).toBeVisible();
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
    const globalButton = page
      .getByRole("button", { name: "全局工作区", exact: true })
      .or(page.getByRole("button", { name: "全局资源", exact: true }))
      .first();
    await globalButton.click();
  }
  const panel = page.locator('[data-testid="workspace-global-resources-panel"]');
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("workspace-global-resources-tree-surface")).toBeVisible();
  return panel;
}

async function dispatchCtrlWheel(page: Page, deltaY: number) {
  await page.evaluate((wheelDeltaY) => {
    const viewport = document.querySelector("[data-canvas-viewport]");
    if (!viewport) {
      throw new Error("Canvas viewport not found");
    }
    const rect = viewport.getBoundingClientRect();
    viewport.dispatchEvent(
      new WheelEvent("wheel", {
        bubbles: true,
        cancelable: true,
        clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2,
        ctrlKey: true,
        deltaY: wheelDeltaY,
      }),
    );
  }, deltaY);
}

async function getCanvasNodePosition(page: Page, nodeId: string) {
  return page.locator(`[data-canvas-node-id="${nodeId}"]`).evaluate((element) => {
    const htmlElement = element as HTMLElement;
    const toPosition = (value: string) =>
      Math.round(Number(value.replace("px", "")) * 1000) / 1000;
    return {
      x: toPosition(htmlElement.style.left),
      y: toPosition(htmlElement.style.top),
    };
  });
}

async function getSavedCanvasNodePosition(
  api: APIRequestContext,
  workspaceId: string,
  fileName: string,
  nodeId: string,
) {
  const response = await api.get(
    `/api/workspaces/${workspaceId}/files/content/${fileName}`,
  );
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  const parsed = JSON.parse(String(body.content));
  const node = parsed.nodes.find((item: { id: string }) => item.id === nodeId);
  return {
    x: Math.round(Number(node?.x) * 1000) / 1000,
    y: Math.round(Number(node?.y) * 1000) / 1000,
  };
}

test.describe("Canvas preview ctrl wheel", () => {
  test("ctrl wheel zooms canvas preview, renders Markdown text, and opens immersive mode", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-Canvas缩放-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "Canvas缩放会话",
    });

    const canvasFileName = `canvas-wheel-${Date.now()}.canvas`;
    const linkedMarkdownFileName = `canvas-linked-${Date.now()}.md`;
    const linkUrl =
      "/analysis?overlay=knowledge_graph&graph_id=7c5d82cc-af08-4b49-966c-f";
    const fileNodeSubpath = "#初始位置";
    const markdownNodeText = [
      "# Canvas Markdown Smoke",
      "",
      "- item one",
      "- item two",
      "",
      "[Open linked note](/workspace/" + linkedMarkdownFileName + ")",
      "",
      "```ts",
      "const marker = 'canvas-markdown';",
      "```",
    ].join("\n");
    const canvasContent = `${JSON.stringify(
      {
        foreignDocumentField: { keep: true },
        nodes: [
          {
            id: "node-markdown",
            type: "text",
            x: 120,
            y: 80,
            width: 420,
            height: 300,
            text: markdownNodeText,
            color: "2",
          },
          {
            id: "node-file",
            type: "file",
            x: 1040,
            y: 360,
            width: 320,
            height: 170,
            file: linkedMarkdownFileName,
            subpath: fileNodeSubpath,
            custom: { aiasys: { node_type: "legacy-evidence" } },
            foreignNodeField: { keep: true },
          },
          {
            id: "node-link",
            type: "link",
            x: 600,
            y: 40,
            width: 360,
            height: 132,
            url: linkUrl,
            color: "1",
          },
        ],
        edges: [
          {
            id: "edge-markdown-file",
            fromNode: "node-markdown",
            toNode: "node-file",
            custom: { aiasys: { edge_type: "legacy-supports" } },
            foreignEdgeField: "keep",
          },
        ],
      },
      null,
      2,
    )}\n`;

    try {
      const createFileResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: canvasFileName,
            content: canvasContent,
            overwrite: false,
          },
        },
      );
      expect(createFileResponse.ok()).toBeTruthy();

      const createLinkedMarkdownResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: linkedMarkdownFileName,
            content: "# Canvas Linked Target\n\nOpened from a Canvas Markdown link.\n",
            overwrite: false,
          },
        },
      );
      expect(createLinkedMarkdownResponse.ok()).toBeTruthy();

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await panel.getByPlaceholder("搜索文件或目录...").fill(canvasFileName);
      if (!(await panel.getByText(canvasFileName, { exact: true }).isVisible())) {
        await panel.getByRole("button", { name: "刷新" }).click();
      }

      await expect(panel.getByText(canvasFileName, { exact: true })).toBeVisible();
      await panel
        .getByRole("button", {
          name: `打开 ${canvasFileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();

      const viewport = page.locator("[data-canvas-viewport]");
      await expect(viewport).toBeVisible();
      const zoomLabel = page.getByTestId("canvas-zoom-label");
      await expect(zoomLabel).toHaveText("100%");
      await expect(
        page.getByRole("heading", { name: "Canvas Markdown Smoke" }),
      ).toBeVisible();
      await expect(page.getByText("item one")).toBeVisible();
      await expect(page.getByText("# Canvas Markdown Smoke")).toHaveCount(0);
      await expect(page.getByText(linkUrl, { exact: true })).toBeVisible();
      await expect(page.getByText(fileNodeSubpath, { exact: true })).toBeVisible();
      await expect(page.getByRole("button", { name: "打开链接" })).toHaveCount(1);

      const linkNode = page.locator('[data-canvas-node-id="node-link"]');
      await expect(
        linkNode.locator("svg").filter({
          has: page.locator("path[d='M15 3h6v6']"),
        }),
      ).toHaveCount(1);

      await dispatchCtrlWheel(page, -160);
      await expect(zoomLabel).not.toHaveText("100%");
      const zoomedInLabel = await zoomLabel.textContent();
      expect(Number(zoomedInLabel?.replace("%", ""))).toBeGreaterThan(100);

      await dispatchCtrlWheel(page, 240);
      await expect.poll(async () => {
        const label = await zoomLabel.textContent();
        return Number(label?.replace("%", ""));
      }).toBeLessThan(Number(zoomedInLabel?.replace("%", "")));

      await page.locator('[data-canvas-node-id="node-file"]').click();
      const propertiesPanel = page.getByTestId("canvas-properties-panel");
      await expect(propertiesPanel).toBeVisible();
      const subpathInput = propertiesPanel.getByLabel("内部位置");
      await expect(subpathInput).toHaveValue(fileNodeSubpath);
      await subpathInput.fill("#验证结论");
      await expect(page.getByText("#验证结论", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "撤销" }).click({ force: true });
      await expect(page.getByText("#验证结论", { exact: true })).toHaveCount(0);
      await expect(page.getByText(fileNodeSubpath, { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "重做" }).click({ force: true });
      await expect(page.getByText("#验证结论", { exact: true })).toBeVisible();
      await expect(propertiesPanel.getByLabel("节点语义")).toHaveCount(0);
      await expect(propertiesPanel.getByLabel("节点状态")).toHaveCount(0);
      await propertiesPanel.getByRole("button", { name: "关闭属性面板" }).click();
      await expect(propertiesPanel).toHaveCount(0);

      const fileOpenButtons = page
        .locator('[data-canvas-node-id="node-file"]')
        .getByRole("button", { name: "打开文件" });
      await fileOpenButtons.click();
      await expect(
        page.getByRole("heading", { name: linkedMarkdownFileName }),
      ).toBeVisible();
      await panel.getByPlaceholder("搜索文件或目录...").fill(canvasFileName);
      await panel
        .getByRole("button", {
          name: `打开 ${canvasFileName} 的文件操作菜单`,
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();
      await expect(page.locator("[data-canvas-viewport]")).toBeVisible();

      await page
        .getByRole("button", { name: "选择连线 edge-markdown-file" })
        .click({ force: true });
      await expect(propertiesPanel).toBeVisible();
      await propertiesPanel.getByLabel("标签").fill("支持证据");
      await expect(propertiesPanel.getByLabel("连线语义")).toHaveCount(0);
      await propertiesPanel.getByLabel("连线箭头").click();
      await page.getByRole("option", { name: "隐藏" }).click();

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/files/content/${canvasFileName}`,
          );
          expect(response.ok()).toBeTruthy();
          const body = await response.json();
          const parsed = JSON.parse(String(body.content));
          return {
            subpath: parsed.nodes.find(
              (node: { id: string }) => node.id === "node-file",
            )?.subpath,
            nodeType: parsed.nodes.find(
              (node: { id: string }) => node.id === "node-file",
            )?.custom?.aiasys?.node_type,
            edgeLabel: parsed.edges.find(
              (edge: { id: string }) => edge.id === "edge-markdown-file",
            )?.label,
            edgeType: parsed.edges.find(
              (edge: { id: string }) => edge.id === "edge-markdown-file",
            )?.custom?.aiasys?.edge_type,
            edgeToEnd: parsed.edges.find(
              (edge: { id: string }) => edge.id === "edge-markdown-file",
            )?.toEnd,
            foreignDocumentField: parsed.foreignDocumentField,
            foreignNodeField: parsed.nodes.find(
              (node: { id: string }) => node.id === "node-file",
            )?.foreignNodeField,
            foreignEdgeField: parsed.edges.find(
              (edge: { id: string }) => edge.id === "edge-markdown-file",
            )?.foreignEdgeField,
          };
        })
        .toEqual({
          subpath: "#验证结论",
          nodeType: "legacy-evidence",
          edgeLabel: "支持证据",
          edgeType: "legacy-supports",
          edgeToEnd: "none",
          foreignDocumentField: { keep: true },
          foreignNodeField: { keep: true },
          foreignEdgeField: "keep",
        });

      await propertiesPanel.getByRole("button", { name: "关闭属性面板" }).click();
      await expect(propertiesPanel).toHaveCount(0);

      const beforeAutoLayoutPosition = await getCanvasNodePosition(page, "node-file");
      await page.getByRole("button", { name: "中心发散整理" }).click();
      const afterAutoLayoutPosition = await getCanvasNodePosition(page, "node-file");
      expect(afterAutoLayoutPosition).not.toEqual(beforeAutoLayoutPosition);
      await expect.poll(
        () => getSavedCanvasNodePosition(api, workspace.workspaceId, canvasFileName, "node-file"),
        { timeout: 10_000 },
      ).toEqual(afterAutoLayoutPosition);

      await page.keyboard.press(process.platform === "darwin" ? "Meta+Z" : "Control+Z");
      await expect.poll(
        () => getCanvasNodePosition(page, "node-file"),
        { timeout: 5_000 },
      ).toEqual(beforeAutoLayoutPosition);
      await page.keyboard.press(process.platform === "darwin" ? "Meta+Y" : "Control+Y");
      await expect.poll(
        () => getCanvasNodePosition(page, "node-file"),
        { timeout: 5_000 },
      ).toEqual(afterAutoLayoutPosition);

      const beforeDragPosition = await getCanvasNodePosition(page, "node-markdown");
      const markdownNodeBox = await page
        .locator('[data-canvas-node-id="node-markdown"]')
        .boundingBox();
      expect(markdownNodeBox).not.toBeNull();
      if (!markdownNodeBox) {
        throw new Error("node-markdown bounding box not found");
      }
      await page.mouse.move(
        markdownNodeBox.x + markdownNodeBox.width / 2,
        markdownNodeBox.y + markdownNodeBox.height / 2,
      );
      await page.mouse.down();
      await page.mouse.move(
        markdownNodeBox.x + markdownNodeBox.width / 2 + 92,
        markdownNodeBox.y + markdownNodeBox.height / 2 + 56,
        { steps: 8 },
      );
      await page.mouse.up();
      const afterDragPosition = await getCanvasNodePosition(page, "node-markdown");
      expect(afterDragPosition).not.toEqual(beforeDragPosition);
      await expect.poll(
        () => getSavedCanvasNodePosition(api, workspace.workspaceId, canvasFileName, "node-markdown"),
        { timeout: 10_000 },
      ).toEqual(afterDragPosition);
      await page.keyboard.press(process.platform === "darwin" ? "Meta+Z" : "Control+Z");
      await expect.poll(
        () => getCanvasNodePosition(page, "node-markdown"),
        { timeout: 5_000 },
      ).toEqual(beforeDragPosition);
      await page.keyboard.press(process.platform === "darwin" ? "Meta+Y" : "Control+Y");
      await expect.poll(
        () => getCanvasNodePosition(page, "node-markdown"),
        { timeout: 5_000 },
      ).toEqual(afterDragPosition);

      await page.getByTestId("canvas-immersive-preview-button").click();
      const immersivePreview = page.getByTestId("immersive-file-preview");
      await expect(immersivePreview).toBeVisible();
      await expect(
        immersivePreview.locator("[data-canvas-viewport]"),
      ).toBeVisible();
      await expect(
        immersivePreview.getByRole("button", { name: "适配画布" }),
      ).toBeVisible();
      await immersivePreview.getByRole("button", { name: "适配画布" }).click();
      await expect(immersivePreview.getByTestId("canvas-zoom-label")).toBeVisible();
      await page.screenshot({
        path: testInfo.outputPath("canvas-immersive-preview.png"),
        fullPage: true,
      });
      await immersivePreview.getByRole("button", { name: "退出沉浸预览" }).click();
      await expect(immersivePreview).toHaveCount(0);

      await page.getByRole("button", { name: "Open linked note" }).click();
      await expect(
        page.getByRole("heading", { name: linkedMarkdownFileName }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Canvas Linked Target" }),
      ).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("canvas-preview-ctrl-wheel.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("opens and persists global workspace canvas without writing current workspace", async ({
    page,
  }, testInfo) => {
    test.setTimeout(180_000);
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-全局Canvas-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "全局 Canvas 会话",
    });

    const globalDir = `global-canvas-smoke-${Date.now()}`;
    const canvasFileName = `${globalDir}/board.canvas`;
    const linkedMarkdownFileName = `${globalDir}/linked-note.md`;
    const canvasContent = `${JSON.stringify(
      {
        globalDocumentField: { keep: true },
        nodes: [
          {
            id: "global-text",
            type: "text",
            x: 120,
            y: 90,
            width: 440,
            height: 260,
            text: [
              "# Global Canvas Markdown",
              "",
              "全局工作区 Canvas 内容。",
              "",
              `[Open global note](/global/${linkedMarkdownFileName})`,
            ].join("\n"),
            color: "3",
          },
          {
            id: "global-file",
            type: "file",
            x: 680,
            y: 120,
            width: 340,
            height: 180,
            file: linkedMarkdownFileName,
            subpath: "#全局初始位置",
            custom: { aiasys: { node_type: "legacy-hypothesis" } },
            globalNodeField: { keep: true },
          },
        ],
        edges: [],
      },
      null,
      2,
    )}\n`;

    try {
      const createCanvasResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/global-workspace/create`,
        {
          data: {
            path: canvasFileName,
            content: canvasContent,
            overwrite: true,
          },
        },
      );
      expect(createCanvasResponse.ok()).toBeTruthy();

      const createMarkdownResponse = await api.post(
        `/api/workspaces/${workspace.workspaceId}/global-workspace/create`,
        {
          data: {
            path: linkedMarkdownFileName,
            content: "# Global Linked Target\n\nOpened from a global Canvas link.\n",
            overwrite: true,
          },
        },
      );
      expect(createMarkdownResponse.ok()).toBeTruthy();

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openGlobalResourcesPanel(page);
      const canvasTreeNode = panel.locator(
        `[data-testid="workspace-file-tree-file-node"][data-file-path="${canvasFileName}"]`,
      );
      await panel.getByPlaceholder("搜索全局工作区...").fill("board.canvas");
      if (!(await canvasTreeNode.isVisible())) {
        await panel.getByRole("button", { name: "刷新" }).click();
      }

      await expect(canvasTreeNode).toBeVisible();
      await canvasTreeNode
        .getByRole("button", {
          name: "打开 board.canvas 的文件操作菜单",
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();

      const viewport = page.locator("[data-canvas-viewport]");
      await expect(viewport).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Global Canvas Markdown" }),
      ).toBeVisible();
      await expect(page.getByText("全局工作区 Canvas 内容。")).toBeVisible();
      await expect(page.getByText("#全局初始位置", { exact: true })).toBeVisible();
      await expect(page.getByText(`全局工作区 / ${canvasFileName}`)).toBeVisible();

      await page.locator('[data-canvas-node-id="global-file"]').click();
      const propertiesPanel = page.getByTestId("canvas-properties-panel");
      await expect(propertiesPanel).toBeVisible();
      await propertiesPanel.getByLabel("内部位置").fill("#全局验证位置");
      await expect(page.getByText("#全局验证位置", { exact: true })).toBeVisible();
      await expect(propertiesPanel.getByLabel("节点语义")).toHaveCount(0);

      await expect
        .poll(async () => {
          const response = await api.get(
            `/api/workspaces/${workspace.workspaceId}/global-workspace/content/${canvasFileName}`,
          );
          expect(response.ok()).toBeTruthy();
          const body = await response.json();
          const parsed = JSON.parse(String(body.content));
          const node = parsed.nodes.find(
            (item: { id: string }) => item.id === "global-file",
          );
          return {
            subpath: node?.subpath,
            nodeType: node?.custom?.aiasys?.node_type,
            globalDocumentField: parsed.globalDocumentField,
            globalNodeField: node?.globalNodeField,
          };
        })
        .toEqual({
          subpath: "#全局验证位置",
          nodeType: "legacy-hypothesis",
          globalDocumentField: { keep: true },
          globalNodeField: { keep: true },
        });

      const currentWorkspaceContentResponse = await api.get(
        `/api/workspaces/${workspace.workspaceId}/files/content/${canvasFileName}`,
      );
      expect(currentWorkspaceContentResponse.status()).toBe(404);

      await propertiesPanel.getByRole("button", { name: "关闭属性面板" }).click();
      await expect(propertiesPanel).toHaveCount(0);
      await page.getByRole("button", { name: "Open global note" }).click();
      await expect(
        page.getByRole("heading", { name: "linked-note.md" }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: "Global Linked Target" }),
      ).toBeVisible();
      await expect(page.getByText(`全局工作区 / ${linkedMarkdownFileName}`)).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("global-workspace-canvas-preview.png"),
        fullPage: true,
      });
    } finally {
      await Promise.allSettled([
        api.delete(
          `/api/workspaces/${workspace.workspaceId}/global-workspace/${linkedMarkdownFileName}`,
          { timeout: 5_000 },
        ),
        api.delete(
          `/api/workspaces/${workspace.workspaceId}/global-workspace/${canvasFileName}`,
          { timeout: 5_000 },
        ),
        api.delete(
          `/api/workspaces/${workspace.workspaceId}/global-workspace/${globalDir}?recursive=true`,
          { timeout: 5_000 },
        ),
      ]);
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
