import { expect, test } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

test.describe("CSV large file preview", () => {
  test.setTimeout(240_000);

  test("uses paged preview and edits only the current page", async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 1440, height: 900 });

    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-CSV分页-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "CSV 分页会话",
    });

    const csvFileName = "browser-regression/large-preview.csv";
    const csvLines = ["col_a,col_b,col_c"];
    for (let index = 1; index <= 260; index += 1) {
      csvLines.push(`${index},${index * 10},${index * 100}`);
    }

    try {
      const createCsvFile = await api.post(
        `/api/workspaces/${workspace.workspaceId}/files/create`,
        {
          data: {
            path: csvFileName,
            content: `${csvLines.join("\n")}\n`,
            overwrite: true,
          },
        },
      );
      expect(createCsvFile.ok()).toBeTruthy();

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
      await panel.getByPlaceholder("搜索文件或目录...").fill("large-preview.csv");
      await expect(panel.getByText("large-preview.csv", { exact: true })).toBeVisible();
      await panel
        .getByRole("button", {
          name: "打开 large-preview.csv 的文件操作菜单",
          exact: true,
        })
        .click();
      await page.getByRole("menuitem", { name: "在主画布打开" }).click();

      const preview = page.getByTestId("csv-preview");
      await expect(preview).toBeVisible();
      await expect(preview.locator('a[download]')).toHaveCount(0);
      await expect(preview.getByText("col_a")).toBeVisible();
      const firstRow = preview.locator("tbody tr").first();
      await expect(firstRow.locator("td").nth(0)).toHaveText("1");
      await expect(firstRow.locator("td").nth(1)).toHaveText("1");
      await expect(firstRow.locator("td").nth(2)).toHaveText("10");
      await expect(firstRow.locator("td").nth(3)).toHaveText("100");

      await page.getByTestId("csv-preview-next-page").click();
      const nextPageFirstRow = preview.locator("tbody tr").first();
      await expect(nextPageFirstRow.locator("td").nth(0)).toHaveText("101");
      await expect(nextPageFirstRow.locator("td").nth(1)).toHaveText("101");
      await expect(nextPageFirstRow.locator("td").nth(2)).toHaveText("1010");
      await expect(nextPageFirstRow.locator("td").nth(3)).toHaveText("10100");
      await page.screenshot({
        path: testInfo.outputPath("csv-preview-page-2.png"),
        fullPage: true,
      });

      await page.getByTestId("csv-preview-toggle-edit").click();
      const cell = preview.locator("tbody tr").nth(0).locator("td").nth(1);
      await cell.click();
      const input = preview.locator("input[type='text']").first();
      await expect(input).toBeVisible();
      await input.fill("9999");
      await input.press("Enter");
      await page.getByTestId("csv-preview-save").click();

      await expect(page.getByText("保存中")).toHaveCount(0);
      await expect(preview.getByText("9999")).toBeVisible();
      await page.getByTestId("csv-preview-prev-page").click();
      await expect(firstRow.locator("td").nth(1)).toHaveText("1");
      await page.getByTestId("csv-preview-next-page").click();
      await expect(preview.locator("tbody tr").first().locator("td").nth(1)).toHaveText("9999");
      await page.screenshot({
        path: testInfo.outputPath("csv-preview-page-1-edited.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
