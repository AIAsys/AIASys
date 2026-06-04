import { expect, test } from "@playwright/test";

test("delete workspace uses in-app dialog instead of browser confirm", async ({
  page,
}) => {
  const nativeDialogs: string[] = [];
  page.on("dialog", async (dialog) => {
    nativeDialogs.push(`${dialog.type()}:${dialog.message()}`);
    await dialog.dismiss();
  });

  await page.goto("http://127.0.0.1:13100/analysis", {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {
    // 本地流式请求可能会让 networkidle 不稳定，允许继续走页面探测。
  });
  await page.waitForTimeout(3000);

  const firstMoreActions = page
    .getByRole("button", { name: "更多操作" })
    .first();
  await expect(firstMoreActions).toBeVisible({ timeout: 30000 });
  await firstMoreActions.click();

  const deleteWorkspaceItem = page.getByText("删除工作区", { exact: true }).last();
  await expect(deleteWorkspaceItem).toBeVisible({ timeout: 10000 });
  await deleteWorkspaceItem.click();

  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible({ timeout: 10000 });
  await expect(
    dialog.getByText(/该工作区下的所有会话和工作区文件都会被删除/),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "删除工作区", exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "取消", exact: true }),
  ).toBeVisible();

  expect(nativeDialogs).toEqual([]);
});
