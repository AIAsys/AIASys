import { expect, test, type Page } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
  seedWorkspaceFile,
} from "./support";

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
  return panel;
}

test.describe("Graph preview panel", () => {
  test("workspace graph preview keeps one create-node entry and uses the inspector form", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    const user = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-图谱预览-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "图谱预览会话",
    });

    const graphFileName = `ui-graph-${Date.now()}.db`;
    const graphPath = `graphs/${graphFileName}`;
    const nodeName = `浏览器验收节点-${Date.now()}`;
    const targetNodeName = `浏览器验收目标-${Date.now()}`;

    try {
      await seedWorkspaceFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        filePath: `../${graphPath}`,
        content: "",
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await expect(panel.getByText(graphFileName, { exact: true })).toBeVisible();
      await panel.getByText(graphFileName, { exact: true }).click();

      await expect(page.getByText("知识图谱资产")).toBeVisible();
      const createButton = page.getByTestId("graph-preview-create-node-button");
      await expect(createButton).toBeVisible();
      await expect(
        page.getByRole("button", { name: "新建节点", exact: true }),
      ).toHaveCount(1);
      await expect(page.getByTestId("graph-preview-node-inspector")).toBeVisible();

      await createButton.click();
      const inspector = page.getByTestId("graph-preview-node-inspector");
      await expect(inspector.getByText("新建节点", { exact: true })).toBeVisible();
      await expect(inspector.getByPlaceholder("输入节点名称")).toBeVisible();
      await inspector.getByPlaceholder("输入节点名称").fill(nodeName);
      await inspector.getByPlaceholder("concept").fill("concept");
      await inspector.getByPlaceholder("可选，补充这个节点的说明").fill(
        "用于验证知识图谱预览的新建节点表单布局。",
      );
      await expect(
        page.getByRole("button", { name: "新建节点", exact: true }),
      ).toHaveCount(1);

      await page.screenshot({
        path: testInfo.outputPath("graph-preview-create-node-form.png"),
        fullPage: true,
      });

      await inspector.getByRole("button", { name: "保存", exact: true }).click();
      await expect(inspector.getByText("节点详情", { exact: true })).toBeVisible();
      await expect(inspector.getByText(nodeName, { exact: true })).toBeVisible();
      await expect(
        page.getByRole("button", { name: "新建节点", exact: true }),
      ).toHaveCount(1);

      await createButton.click();
      await expect(inspector.getByText("新建节点", { exact: true })).toBeVisible();
      await inspector.getByPlaceholder("输入节点名称").fill(targetNodeName);
      await inspector.getByPlaceholder("concept").fill("concept");
      await inspector.getByRole("button", { name: "保存", exact: true }).click();
      await expect(inspector.getByText("节点详情", { exact: true })).toBeVisible();
      await expect(inspector.getByText(targetNodeName, { exact: true })).toBeVisible();

      const connectButton = page.getByTestId("graph-preview-connect-node-button");
      await expect(connectButton).toBeVisible();
      await connectButton.click();
      await expect(page.getByTestId("graph-preview-connect-node-form")).toBeVisible();
      await page.getByTestId("graph-preview-connect-target-search").fill(nodeName);
      const targetResults = page.getByTestId("graph-preview-connect-target-results");
      await expect(targetResults.getByRole("button", { name: new RegExp(nodeName) })).toBeVisible();
      await targetResults.getByRole("button", { name: new RegExp(nodeName) }).click();
      await inspector.getByPlaceholder("related_to").fill("supports");
      await inspector.getByPlaceholder("可选，补充这条关系的说明").fill(
        "用于验证知识图谱预览的手工关系创建。",
      );

      await page.screenshot({
        path: testInfo.outputPath("graph-preview-connect-node-form.png"),
        fullPage: true,
      });

      await inspector.getByRole("button", { name: "保存关系", exact: true }).click();
      await expect(inspector.getByText("节点详情", { exact: true })).toBeVisible();
      await expect(page.getByTestId("graph-preview-selected-node-relation-count")).toHaveText("1");
      await expect(inspector.getByText(nodeName, { exact: true })).toBeVisible();
      await expect(inspector.getByText("supports", { exact: true })).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("graph-preview-created-node.png"),
        fullPage: true,
      });

      const deleteButton = page.getByTestId("graph-preview-delete-node-button");
      await expect(deleteButton).toBeVisible();
      await deleteButton.click();
      await expect(page.getByRole("alertdialog")).toBeVisible();
      await expect(page.getByText(`将删除“${targetNodeName}”`)).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("graph-preview-delete-node-confirm.png"),
        fullPage: true,
      });

      await page.getByTestId("graph-preview-confirm-delete-node-button").click();
      await expect(page.getByRole("alertdialog")).toBeHidden();
      await expect(inspector.getByText("未选择节点", { exact: true })).toBeVisible();
      await expect(inspector.getByText("1", { exact: true })).toBeVisible();
      await expect(inspector.getByText("0", { exact: true })).toBeVisible();
      await expect(inspector.getByText(targetNodeName, { exact: true })).toHaveCount(0);
      await expect(inspector.getByText("supports", { exact: true })).toHaveCount(0);

      await page.screenshot({
        path: testInfo.outputPath("graph-preview-deleted-node.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
