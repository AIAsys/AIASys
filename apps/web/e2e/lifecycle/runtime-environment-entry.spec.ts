import { expect, test, type Page } from "@playwright/test";

import {
  buildAnalysisUrl,
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

async function waitForBackend(page: Page) {
  await expect
    .poll(
      async () => {
        const response = await page.request
          .get("http://127.0.0.1:13001/health", { timeout: 1_000 })
          .catch(() => null);
        return response?.ok() ?? false;
      },
      { timeout: 60_000 },
    )
    .toBe(true);
}

test.describe("Sandbox strategy workspace entry", () => {
  test("opens workspace sandbox settings from the chat input badge", async ({
    page,
  }, testInfo) => {
    const api = page.request;
    await waitForBackend(page);
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-沙盒策略入口-${Date.now()}`,
      initialConversationTitle: "沙盒策略入口会话",
    });

    try {
      await page.goto(
        buildAnalysisUrl({
          workspaceId: workspace.workspaceId,
          conversationId: workspace.currentConversationId,
        }),
        { waitUntil: "domcontentloaded" },
      );

      await expect(page.locator("textarea")).toBeVisible();

      const runtimeBadge = page.getByTestId("input-runtime-env");
      await expect(runtimeBadge).toBeVisible();
      await runtimeBadge.click();

      const dialog = page.getByTestId("runtime-environment-panel");
      await expect(dialog).toBeVisible();
      await expect(
        dialog.getByRole("heading", { name: "沙盒策略", exact: true }),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "本地沙盒 UV / Notebook 当前" }),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "Docker 沙盒 容器执行" }),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "工作区变量 注入 Shell / Python" }),
      ).toBeVisible();
      await expect(
        dialog.getByRole("button", { name: "Python 环境 UV 与解释器" }),
      ).toBeVisible();
      await expect(
        dialog.getByText("当前本地沙盒", { exact: true }),
      ).toBeVisible();

      await dialog.getByRole("button", { name: "Docker 沙盒 容器执行" }).click();
      const containerDialog = page.getByTestId("container-resources-panel");
      await expect(containerDialog).toBeVisible();
      await expect(dialog.getByText("Docker 沙盒材料", { exact: true })).toBeVisible();
      await expect(containerDialog.getByRole("button", { name: "登记 Docker 沙盒" })).toBeVisible();
      await containerDialog.getByRole("button", { name: "登记 Docker 沙盒" }).first().click();
      await expect(containerDialog.getByTestId("docker-sandbox-register-form")).toBeVisible();
      await expect(containerDialog.getByRole("button", { name: "登记已有容器" })).toBeVisible();
      await expect(containerDialog.getByRole("button", { name: "按镜像创建容器" })).toBeVisible();
      await expect(containerDialog.getByLabel("容器 ID 或名称")).toBeVisible();
      await dialog.getByRole("button", { name: "本地沙盒 UV / Notebook 当前" }).click();

      await page.screenshot({
        path: testInfo.outputPath("runtime-environment-entry.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
