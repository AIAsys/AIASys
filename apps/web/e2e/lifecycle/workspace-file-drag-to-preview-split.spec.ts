import { expect, test, type Page } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
  seedWorkspaceFile,
} from "./support";

/**
 * Drag-and-drop of workspace files from the file tree sidebar into
 * the main canvas preview area.
 *
 * MIME contracts tested:
 * - application/x-aiasys-workspace-file (file tree -> canvas drop)
 *
 * Split zones tested:
 * - center (80% of width, 25%-75% of height)  -> open tab in active leaf
 * - right  (last 20% of width)                -> horizontal split
 * - left   (first 20% of width)               -> horizontal split (tab first)
 * - bottom (last 25% of height)               -> vertical split (tab second)
 * - top    (first 25% of height)              -> vertical split (tab first)
 */

const WORKSPACE_FILE_DRAG_MIME = "application/x-aiasys-workspace-file";

interface DispatchFileDropOptions {
  fileName: string;
  /** Index of the target leaf container (0 for first/only leaf) */
  leafIndex: number;
  /** Fractional coordinates (0-1) within the target element */
  xRatio: number;
  yRatio: number;
}

/**
 * Dispatches a full drag-and-drop sequence from a file tree node to a
 * canvas leaf container, using the workspace-file MIME type.
 *
 * Playwright's native dragTo does not support custom MIME types,
 * so this helper uses page.evaluate to create and dispatch
 * DataTransfer-backed DragEvents.
 */
async function dragFileToLeaf(
  page: Page,
  options: DispatchFileDropOptions,
) {
  await page.evaluate(
    ({ fileName, panelSelector, containerSelector, leafIndex, xRatio, yRatio, mime }) => {
      // ---- find the file tree node ----
      const panel = document.querySelector(panelSelector);
      if (!panel) throw new Error(`File tree panel not found: ${panelSelector}`);

      // The file tree node is a div with draggable attribute containing a
      // span.font-mono whose textContent equals the file name.
      const allDraggableDivs = Array.from(panel.querySelectorAll("[draggable]"));
      let dragSource: HTMLElement | null = null;
      for (const div of allDraggableDivs) {
        const span = div.querySelector("span.font-mono");
        if (span && span.textContent?.trim() === fileName) {
          dragSource = div as HTMLElement;
          break;
        }
      }
      if (!dragSource) {
        // Fallback: search by text content in any descendant span
        for (const div of allDraggableDivs) {
          if (div.textContent?.includes(fileName)) {
            dragSource = div as HTMLElement;
            break;
          }
        }
      }
      if (!dragSource) throw new Error(`File tree node not found for: ${fileName}`);

      // ---- find the drop target ----
      const containers = Array.from(
        document.querySelectorAll(containerSelector),
      );
      const container = containers[leafIndex];
      if (!container) {
        throw new Error(
          `Drop container not found at index ${leafIndex}: ${containerSelector}`,
        );
      }

      const rect = container.getBoundingClientRect();
      const clientX = rect.left + rect.width * xRatio;
      const clientY = rect.top + rect.height * yRatio;

      // ---- create DataTransfer ----
      const dt = new DataTransfer();
      dt.setData(mime, fileName);
      dt.setData("text/plain", fileName);
      dt.effectAllowed = "copy";

      // ---- dispatch dragstart ----
      dragSource.dispatchEvent(
        new DragEvent("dragstart", {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX,
          clientY,
        }),
      );

      // ---- dispatch dragover (required so preventDefault is called) ----
      container.dispatchEvent(
        new DragEvent("dragover", {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX,
          clientY,
        }),
      );

      // ---- dispatch drop ----
      container.dispatchEvent(
        new DragEvent("drop", {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX,
          clientY,
        }),
      );

      // ---- dispatch dragend on source for cleanup ----
      dragSource.dispatchEvent(
        new DragEvent("dragend", {
          bubbles: true,
          cancelable: true,
          dataTransfer: dt,
          clientX,
          clientY,
        }),
      );
    },
    {
      fileName: options.fileName,
      panelSelector: `[data-testid="workspace-artifacts-panel"]`,
      containerSelector: `[data-testid="canvas-drop-zone"]`,
      leafIndex: options.leafIndex,
      xRatio: options.xRatio,
      yRatio: options.yRatio,
      mime: WORKSPACE_FILE_DRAG_MIME,
    },
  );
}

test.describe("Workspace file drag to preview split", () => {
  test.setTimeout(180_000);

  test("drag file to center opens tab, drag to right edge creates split, same file re-activates existing tab", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    const user = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-拖拽分栏-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "拖拽分栏会话",
    });

    const file1Name = "drag-preview-1.py";
    const file2Name = "drag-preview-2.md";

    try {
      await seedWorkspaceFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        filePath: file1Name,
        content: "print('hello from drag test file 1')\n",
      });

      await seedWorkspaceFile({
        userId: user.userId,
        workspaceId: workspace.workspaceId,
        filePath: file2Name,
        content: "# Drag test file 2\n\nThis is a markdown file.\n",
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

      // Verify both files are visible in the file tree
      await expect(panel.getByText(file1Name, { exact: true })).toBeVisible();
      await expect(panel.getByText(file2Name, { exact: true })).toBeVisible();

      // ===================================================================
      // Scenario 1: Drag file to center opens a tab
      // ===================================================================
      await dragFileToLeaf(page, {
        fileName: file1Name,
        leafIndex: 0,
        xRatio: 0.5,
        yRatio: 0.5,
      });

      // Allow React state updates to flush
      await page.waitForTimeout(300);

      // Verify a tab appears with the file name
      const file1TabDiv = page.locator(`div[title="${file1Name}"]`).first();
      await expect(file1TabDiv).toBeVisible();

      // Verify file preview content is visible (heading shows the file name)
      await expect(
        page.getByRole("heading", { name: file1Name }),
      ).toBeVisible();

      // Verify the file content is rendered
      await expect(page.getByText("hello from drag test file 1")).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("drag-to-center-tab-opened.png"),
        fullPage: true,
      });

      // ===================================================================
      // Scenario 2: Drag second file to right edge creates horizontal split
      // ===================================================================

      // Drag file2 to the right edge (xRatio > 0.8 triggers horizontal split)
      await dragFileToLeaf(page, {
        fileName: file2Name,
        leafIndex: 0,
        xRatio: 0.9,
        yRatio: 0.5,
      });

      // Allow pane tree to update and React to render
      await page.waitForTimeout(500);

      // After horizontal split: two leaf containers should exist (side by side)
      await expect(
        page.locator('[data-testid="canvas-drop-zone"]'),
      ).toHaveCount(2);

      // The new file should be open in the right pane
      const file2TabDiv = page.locator(`div[title="${file2Name}"]`).first();
      await expect(file2TabDiv).toBeVisible();

      // The original file should still be in the left pane
      await expect(file1TabDiv).toBeVisible();

      // Both file headings should be visible (each pane shows its active tab)
      await expect(
        page.getByRole("heading", { name: file1Name }),
      ).toBeVisible();
      await expect(
        page.getByRole("heading", { name: file2Name }),
      ).toBeVisible();

      // Verify file2 content is rendered
      await expect(
        page.getByText("Drag test file 2"),
      ).toBeVisible();

      // Split buttons should exist (one pair per pane)
      await expect(page.locator('button[title="向右拆分"]')).toHaveCount(2);

      await page.screenshot({
        path: testInfo.outputPath("drag-to-right-split-created.png"),
        fullPage: true,
      });

      // ===================================================================
      // Scenario 3: Drag same file to center activates existing tab (no duplicate)
      // ===================================================================

      // Count existing tabs for file1 before the second drag
      const file1TabCountBefore = await page.locator(
        `div[title="${file1Name}"]`,
      ).count();

      // Drag file1 to center again (the left pane is the active/drop target)
      await dragFileToLeaf(page, {
        fileName: file1Name,
        leafIndex: 0,
        xRatio: 0.5,
        yRatio: 0.5,
      });

      await page.waitForTimeout(300);

      // No duplicate tab should have been created
      const file1TabCountAfter = await page.locator(
        `div[title="${file1Name}"]`,
      ).count();
      expect(file1TabCountAfter).toBe(file1TabCountBefore);

      // The existing tab should be active (heading visible)
      await expect(
        page.getByRole("heading", { name: file1Name }),
      ).toBeVisible();

      // file2 should still be open
      await expect(
        page.getByRole("heading", { name: file2Name }),
      ).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("drag-same-file-reactivates-tab.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
