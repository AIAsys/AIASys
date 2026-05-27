import { expect, test } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
  seedWorkspaceFile,
} from "./support";

test.describe("Workspace file tabbed split pane", () => {
  test.setTimeout(180_000);

  test("opens files in tabs, switches tabs, splits panes horizontally and vertically, and returns home on close", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    const user = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-分栏标签-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "分栏标签会话",
    });

    const file1Name = "tab-split-file-1.py";
    const file2Name = "tab-split-file-2.md";

    try {
      await seedWorkspaceFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        filePath: file1Name,
        content: "print('file 1 from tab split test')\n",
      });

      await seedWorkspaceFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        filePath: file2Name,
        content: "# File 2 for tab split test\n\nThis is a markdown file.\n",
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();

      // Open artifacts panel
      const fileTab = page.locator("button[aria-label='文件']");
      if (await fileTab.isVisible()) {
        await fileTab.click();
      } else {
        await page.getByRole("button", { name: "资产", exact: true }).click();
      }

      const panel = page.locator('[data-testid="workspace-artifacts-panel"]');
      await expect(panel).toBeVisible();

      const openFileInCanvas = async (fileName: string) => {
        await panel
          .getByRole("button", {
            name: `打开 ${fileName} 的文件操作菜单`,
            exact: true,
          })
          .click();
        await page.getByRole("menuitem", { name: "在主画布打开" }).click();
        await expect(
          page.getByRole("heading", { name: fileName }),
        ).toBeVisible();
      };

      // Scenario 1: Open two files, verify two tabs appear
      await openFileInCanvas(file1Name);

      // Take a screenshot after opening the first file
      await page.screenshot({
        path: testInfo.outputPath("tab-split-pane-1-first-file.png"),
        fullPage: true,
      });

      await openFileInCanvas(file2Name);

      // Both tab divs should be present (each tab div has title matching the file name)
      const file1TabDiv = page.locator(`div[title="${file1Name}"]`).first();
      const file2TabDiv = page.locator(`div[title="${file2Name}"]`).first();
      await expect(file1TabDiv).toBeVisible();
      await expect(file2TabDiv).toBeVisible();

      // Scenario 2: Tab switching
      // file2 is active (opened last), switch to file1
      await file1TabDiv.click();
      await expect(page.getByRole("heading", { name: file1Name })).toBeVisible();

      // Switch back to file2
      await file2TabDiv.click();
      await expect(page.getByRole("heading", { name: file2Name })).toBeVisible();

      // Scenario 3: Split right (horizontal split)
      // The split-right button has title="向右拆分" and uses Columns2 icon
      const splitRightBtn = page.locator('button[title="向右拆分"]');
      await expect(splitRightBtn).toBeVisible();
      await splitRightBtn.click();

      // After horizontal split, file2 (the active tab) moves to the right pane.
      // Both panes have active tabs, so two split-right buttons should exist.
      await expect(page.locator('button[title="向右拆分"]')).toHaveCount(2);

      // Both file headings should be visible - each pane shows its active tab
      await expect(page.getByRole("heading", { name: file1Name })).toBeVisible();
      await expect(page.getByRole("heading", { name: file2Name })).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("tab-split-pane-2-split-right.png"),
        fullPage: true,
      });

      // Scenario 4: Split down (vertical split) on the active pane (right pane with file2)
      const splitDownBtns = page.locator('button[title="向下拆分"]');
      await expect(splitDownBtns.first()).toBeVisible();

      // Find which pane has file2 active and click its split-down button
      const file2TabDivs = page.locator(`div[title="${file2Name}"]`);
      // file2 is in the right pane; its tab bar contains the split-down button
      const file2PaneTabBar = file2TabDivs.first().locator("xpath=ancestor::div[contains(@class, 'flex h-9')]");
      const file2SplitDownBtn = file2PaneTabBar.locator('button[title="向下拆分"]');
      await file2SplitDownBtn.click();

      // After vertical split, the single-tab pane duplicates file2 so the split
      // never leaves the user with an empty pane.
      await expect(
        page.locator('[data-testid="canvas-drop-zone"]'),
      ).toHaveCount(3);
      await expect(
        page.getByText("当前没有打开的对象"),
      ).toHaveCount(0);

      // file1 remains visible; file2 is visible in both vertically split panes.
      await expect(
        page.getByRole("heading", { name: file1Name }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: file2Name }),
      ).toHaveCount(2);

      await page.screenshot({
        path: testInfo.outputPath("tab-split-pane-3-split-down.png"),
        fullPage: true,
      });

      // Scenario 5: Close all tabs, verify return to workspace home/file view
      // Close duplicated file2 tabs first.
      // The close button (X icon) is inside the tab div and has title="关闭标签".
      for (let attempt = 0; attempt < 3; attempt += 1) {
        const file2TabCount = await page.locator(`div[title="${file2Name}"]`).count();
        if (file2TabCount === 0) break;
        await page
          .locator(`div[title="${file2Name}"]`)
          .first()
          .locator('button[title="关闭标签"]')
          .click();
        await page.waitForTimeout(200);
      }

      // Now only file1 remains in a single pane. Close it.
      const file1CloseBtn = page.locator(`div[title="${file1Name}"]`)
        .first()
        .locator('button[title="关闭标签"]');
      await file1CloseBtn.click();

      // After all tabs are closed, the workspace returns to the default view.
      // Verify no tab headings remain visible.
      await expect(
        page.getByRole("heading", { name: file1Name }),
      ).not.toBeVisible();
      await expect(
        page.getByRole("heading", { name: file2Name }),
      ).not.toBeVisible();

      // The artifacts panel should remain visible (the file view returns)
      await expect(panel).toBeVisible();

      // No split buttons should exist (no tabs open)
      await expect(page.locator('button[title="向右拆分"]')).toHaveCount(0);
      await expect(page.locator('button[title="向下拆分"]')).toHaveCount(0);

      await page.screenshot({
        path: testInfo.outputPath("tab-split-pane-4-all-closed.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
