import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

async function openWorkspaceFilesPanel(page: Page): Promise<Locator> {
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

function fileTreeNode(panel: Locator, fileName: string): Locator {
  return panel
    .locator(
      `[data-testid="workspace-file-tree-file-node"][data-file-path="${fileName}"]`,
    )
    .first();
}

function folderTreeNode(panel: Locator, folderPath: string): Locator {
  return panel
    .locator(
      `[data-testid="workspace-file-tree-folder-node"][data-file-path="${folderPath}"]`,
    )
    .first();
}

test.describe("Workspace file tree multi-select", () => {
  test.setTimeout(180_000);

  test("supports Ctrl multi-select across files and folders", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    const user = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件树多选-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件树多选会话",
    });

    const firstFileName = "multi-select/a-first.py";
    const secondFileName = "multi-select/b-second.md";
    const thirdFileName = "multi-select/c-third.json";

    try {
      for (const [path, content] of [
        [firstFileName, "print('first')\n"],
        [secondFileName, "# second\n"],
        [thirdFileName, '{"third": true}\n'],
      ] as const) {
        const response = await api.post(
          `/api/files/create/${user.userId}/${workspace.currentConversationId}?user_id=${user.userId}`,
          {
            data: { path, content, overwrite: true },
          },
        );
        expect(response.ok()).toBeTruthy();
      }

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await panel.getByRole("button", { name: "刷新" }).click();
      await expect.poll(async () => {
        const text = await panel
          .getByTestId("workspace-artifacts-file-count")
          .textContent();
        const match = text?.match(/(\d+)/);
        return match ? Number.parseInt(match[1], 10) : 0;
      }, { timeout: 15_000 }).toBeGreaterThanOrEqual(3);
      const folder = folderTreeNode(panel, "multi-select");
      const firstFile = fileTreeNode(panel, firstFileName);
      const secondFile = fileTreeNode(panel, secondFileName);
      const thirdFile = fileTreeNode(panel, thirdFileName);
      await expect(folder).toBeVisible();
      await expect(firstFile).toBeVisible();
      await expect(secondFile).toBeVisible();
      await expect(thirdFile).toBeVisible();

      await firstFile.click();
      await expect(firstFile).toHaveAttribute("data-selected", "true");
      await expect(
        panel.getByTestId("workspace-file-tree-multi-select-summary"),
      ).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "a-first.py" })).toBeVisible();

      await folder.click({ modifiers: ["Control"] });
      await expect(firstFile).toHaveAttribute("data-selected", "true");
      await expect(folder).toHaveAttribute("data-selected", "true");
      await expect(secondFile).toBeVisible();
      await expect(
        panel.getByTestId("workspace-file-tree-multi-select-summary"),
      ).toHaveText("已选 2 项");
      await expect(page.getByRole("heading", { name: "a-first.py" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "multi-select" })).toHaveCount(0);

      await secondFile.click({ modifiers: ["Control"] });
      await expect(folder).toHaveAttribute("data-selected", "true");
      await expect(firstFile).toHaveAttribute("data-selected", "true");
      await expect(secondFile).toHaveAttribute("data-selected", "true");
      await expect(
        panel.getByTestId("workspace-file-tree-multi-select-summary"),
      ).toHaveText("已选 3 项");
      await expect(page.getByRole("heading", { name: "a-first.py" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "b-second.md" })).toHaveCount(0);

      await thirdFile.click({ modifiers: ["Control"] });
      await expect(thirdFile).toHaveAttribute("data-selected", "true");
      await expect(
        panel.getByTestId("workspace-file-tree-multi-select-summary"),
      ).toHaveText("已选 4 项");
      await expect(page.getByRole("heading", { name: "a-first.py" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "c-third.json" })).toHaveCount(0);
      await page.screenshot({
        path: testInfo.outputPath("workspace-file-tree-mixed-selection.png"),
        fullPage: true,
      });

      await folder.click({ modifiers: ["Control"] });
      await expect(folder).toHaveAttribute("data-selected", "false");
      await expect(secondFile).toBeVisible();
      await expect(
        panel.getByTestId("workspace-file-tree-multi-select-summary"),
      ).toHaveText("已选 3 项");

      await thirdFile.click();
      await expect(folder).toHaveAttribute("data-selected", "false");
      await expect(firstFile).toHaveAttribute("data-selected", "false");
      await expect(secondFile).toHaveAttribute("data-selected", "false");
      await expect(thirdFile).toHaveAttribute("data-selected", "true");
      await expect(
        panel.getByTestId("workspace-file-tree-multi-select-summary"),
      ).toHaveCount(0);
      await expect(page.getByRole("heading", { name: "c-third.json" })).toBeVisible();

      await folder.click();
      await expect(folder).toHaveAttribute("data-selected", "true");
      await expect(thirdFile).toHaveCount(0);

      await page.screenshot({
        path: testInfo.outputPath("workspace-file-tree-multi-select.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
