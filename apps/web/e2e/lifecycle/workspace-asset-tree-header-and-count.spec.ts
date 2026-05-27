import { expect, test, type Page } from "@playwright/test";

import {
  getWorkspaceRoot,
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
      await page.getByRole("button", { name: "文件", exact: true }).click();
    }
  }
  await expect(panel).toBeVisible();
  await expect(
    panel.getByTestId("workspace-artifacts-tree-surface"),
  ).toBeVisible();
  return panel;
}

async function openGlobalResourcesPanel(page: Page) {
  const globalTab = page.locator("button[aria-label='全局资源']");
  if (await globalTab.isVisible()) {
    await globalTab.click();
  } else {
    await page.getByRole("button", { name: "全局资源", exact: true }).click();
  }
  const panel = page.locator('[data-testid="workspace-global-resources-panel"]');
  await expect(panel).toBeVisible();
  await expect(panel.getByText("全局工作区", { exact: true })).toBeVisible();
  return panel;
}

test.describe("Workspace asset tree header and count", () => {
  test("workspace artifacts shows compact header with correct file and directory counts", async ({
    page,
  }, testInfo) => {
    const api = page.request;
    const user = await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件树头部-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件树头部会话",
    });

    try {
      // 通过 API 预置 2 个文件
      await api.post(`/api/files/create/${user.userId}/${workspace.currentConversationId}?user_id=${user.userId}`, {
        data: {
          path: "browser-regression/readme.md",
          content: "# Browser regression test",
          overwrite: false,
        },
      });
      await api.post(`/api/files/create/${user.userId}/${workspace.currentConversationId}?user_id=${user.userId}`, {
        data: {
          path: "browser-regression/summary.md",
          content: "## Summary",
          overwrite: false,
        },
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);

      // 验证紧凑头部中的计数徽标
      await expect(
        panel.getByTestId("workspace-artifacts-file-count"),
      ).toHaveText("2 文件");
      await expect(
        panel.getByTestId("workspace-artifacts-directory-count"),
      ).toHaveText("1 目录");

      // 通过 API 再创建 1 个文件，然后刷新
      await api.post(`/api/files/create/${user.userId}/${workspace.currentConversationId}?user_id=${user.userId}`, {
        data: {
          path: "browser-regression/data.csv",
          content: "a,b\n1,2",
          overwrite: false,
        },
      });

      await panel.getByRole("button", { name: "刷新" }).click();

      // 验证文件数增加了
      await expect.poll(async () => {
        const text = await panel.getByTestId("workspace-artifacts-file-count").textContent();
        const match = text?.match(/(\d+)/);
        return match ? parseInt(match[1], 10) : 0;
      }, { timeout: 15_000 }).toBeGreaterThan(2);

      await page.screenshot({
        path: testInfo.outputPath("workspace-artifacts-header-count.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace artifacts tree stays mounted when switching activity tabs", async ({
    page,
  }) => {
    const api = page.request;
    const user = await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件树保活-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件树保活会话",
    });

    const treePath = `/api/workspaces/${workspace.workspaceId}/resources/tree`;
    let currentTreeRequestCount = 0;
    page.on("request", (request) => {
      const url = new URL(request.url());
      if (url.pathname === treePath) {
        currentTreeRequestCount += 1;
      }
    });

    try {
      const response = await api.post(
        `/api/files/create/${user.userId}/${workspace.currentConversationId}?user_id=${user.userId}`,
        {
          data: {
            path: "keep-alive/readme.md",
            content: "# Keep alive",
            overwrite: true,
          },
        },
      );
      expect(response.ok()).toBeTruthy();

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await expect(panel.getByText("readme.md", { exact: true })).toBeVisible();
      await expect.poll(async () => {
        const before = currentTreeRequestCount;
        await page.waitForTimeout(250);
        return currentTreeRequestCount === before && before > 0;
      }, { timeout: 15_000 }).toBe(true);
      const requestCountAfterInitialLoad = currentTreeRequestCount;

      await page.getByRole("button", { name: "全局工作区", exact: true }).click();
      await expect(page.locator('[data-testid="workspace-global-resources-panel"]')).toBeVisible();

      await page.getByRole("button", { name: "数据查询", exact: true }).click();
      await expect(page.getByText("数据库连接", { exact: true })).toBeVisible();

      await page.getByRole("button", { name: "当前工作区", exact: true }).click();
      await expect(panel).toBeVisible();
      await expect(panel.getByText("readme.md", { exact: true })).toBeVisible();
      await expect
        .poll(() => currentTreeRequestCount, { timeout: 3_000 })
        .toBe(requestCountAfterInitialLoad);
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace artifacts can create an empty folder from the panel action", async ({
    page,
  }) => {
    const api = page.request;
    const user = await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-新建文件夹-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "新建文件夹会话",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await panel.getByRole("button", { name: "新建文件夹" }).click();

      const folderPath = `browser-regression/empty-${Date.now()}`;
      await page.locator("#new-folder-path").fill(folderPath);
      await page.getByRole("button", { name: "创建文件夹" }).click();

      await expect(
        panel.getByText(folderPath.split("/").at(-1) || folderPath, {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        panel.getByText("__aiasys_folder__.md", { exact: true }),
      ).toHaveCount(0);
      await expect(
        panel.getByTestId("workspace-artifacts-directory-count"),
      ).toHaveText("2 目录");
      await expect(
        panel.getByTestId("workspace-artifacts-file-count"),
      ).toHaveText("0 文件");
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace artifacts root context menu creates folder from count area", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件树根菜单-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件树根菜单会话",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await panel
        .getByTestId("workspace-artifacts-file-count")
        .click({ button: "right" });

      const rootMenu = page.getByTestId("workspace-artifacts-root-menu");
      await expect(rootMenu).toBeVisible();
      await expect(
        rootMenu.getByRole("menuitem", { name: "新建文件", exact: true }),
      ).toBeVisible();
      await expect(
        rootMenu.getByRole("menuitem", { name: "上传文件", exact: true }),
      ).toBeVisible();
      await expect(
        rootMenu.getByRole("menuitem", { name: "刷新", exact: true }),
      ).toBeVisible();
      await rootMenu
        .getByRole("menuitem", { name: "新建文件夹", exact: true })
        .click();

      const folderPath = `browser-regression/context-empty-${Date.now()}`;
      await page.locator("#new-folder-path").fill(folderPath);
      await page.getByRole("button", { name: "创建文件夹" }).click();

      await expect(
        panel.getByText(folderPath.split("/").at(-1) || folderPath, {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        panel.getByText("__aiasys_folder__.md", { exact: true }),
      ).toHaveCount(0);
      await expect(
        panel.getByTestId("workspace-artifacts-file-count"),
      ).toHaveText("0 文件");
      await expect(
        panel.getByTestId("workspace-artifacts-directory-count"),
      ).toHaveText("2 目录");
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace artifacts root context menu opens from file tree blank area", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-文件树空白菜单-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "文件树空白菜单会话",
    });

    try {
      await api.post(`/api/files/create/${user.userId}/${workspace.currentConversationId}?user_id=${user.userId}`, {
        data: {
          path: "browser-regression/existing.md",
          content: "# Existing file",
          overwrite: false,
        },
      });

      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await panel
        .getByTestId("workspace-artifacts-tree-surface")
        .click({ button: "right", position: { x: 80, y: 220 } });

      const rootMenu = page.getByTestId("workspace-artifacts-root-menu");
      await expect(rootMenu).toBeVisible();
      await rootMenu
        .getByRole("menuitem", { name: "新建文件夹", exact: true })
        .click();

      const folderPath = `browser-regression/blank-empty-${Date.now()}`;
      await page.locator("#new-folder-path").fill(folderPath);
      await page.getByRole("button", { name: "创建文件夹" }).click();

      await expect(
        panel.getByText(folderPath.split("/").at(-1) || folderPath, {
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        panel.getByText("__aiasys_folder__.md", { exact: true }),
      ).toHaveCount(0);
      await expect(
        panel.getByTestId("workspace-artifacts-directory-count"),
      ).toHaveText("2 目录");
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("workspace artifacts accepts logical and HTTP paths and exposes folder copy options", async ({
    page,
    context,
  }) => {
    const api = page.request;
    const user = await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-路径引用-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "路径引用会话",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openWorkspaceFilesPanel(page);
      await panel.getByRole("button", { name: "新建文件夹" }).click();

      const folderPath = `browser-regression/path-input-${Date.now()}`;
      await page.locator("#new-folder-path").fill(`/workspace/${folderPath}/`);
      await page.getByRole("button", { name: "创建文件夹" }).click();

      const folderName = folderPath.split("/").at(-1) || folderPath;
      await expect(panel.getByText(folderName, { exact: true })).toBeVisible();
      await expect(
        panel.getByText("__aiasys_folder__.md", { exact: true }),
      ).toHaveCount(0);

      const urlPath = `${folderPath}/from-http.md`;
      const fileUrl = new URL(
        `/api/files/download/${user.userId}/${workspace.currentConversationId}/${urlPath}`,
        "http://127.0.0.1:13000",
      ).toString();
      await panel.getByRole("button", { name: "新建文件", exact: true }).click();
      await page.locator("#new-file-path").fill(fileUrl);
      await page.getByRole("button", { name: "创建并打开" }).click();
      await expect(panel.getByText("from-http.md", { exact: true })).toBeVisible();

      await context.grantPermissions(["clipboard-read", "clipboard-write"], {
        origin: "http://localhost:13000",
      });
      await panel.getByText(folderName, { exact: true }).click({ button: "right" });
      const folderMenu = page.getByRole("menu");
      await expect(
        folderMenu.getByRole("menuitem", { name: "复制绝对路径" }),
      ).toBeVisible();
      await expect(
        folderMenu.getByRole("menuitem", { name: "复制资源路径" }),
      ).toBeVisible();
      await expect(
        folderMenu.getByText(
          `${getWorkspaceRoot(user.userId, workspace.workspaceId)}/${folderPath}`,
          { exact: true },
        ),
      ).toBeVisible();
      await folderMenu.getByRole("menuitem", { name: "复制绝对路径" }).click();
      await expect
        .poll(() => page.evaluate(() => navigator.clipboard.readText()))
        .toBe(`${getWorkspaceRoot(user.userId, workspace.workspaceId)}/${folderPath}`);

      await panel.getByText(folderName, { exact: true }).click({ button: "right" });
      await page.getByRole("menu").getByRole("menuitem", { name: "复制资源路径" }).click();
      await expect
        .poll(() => page.evaluate(() => navigator.clipboard.readText()))
        .toBe(`/workspace/${folderPath}`);
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("global resources shows compact header and refresh button works", async ({
    page,
  }, testInfo) => {
    const api = page.request;
    const user = await registerLifecycleUser(api);

    const workspace = await createWorkspace(api, {
      title: `浏览器回归-全局资源头部-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "全局资源头部会话",
    });

    try {
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const panel = await openGlobalResourcesPanel(page);

      // 验证紧凑头部可见
      await expect(
        panel.getByText("全局工作区", { exact: true }),
      ).toBeVisible();

      // 计数徽标可见（即使为 0）
      await expect(
        panel.getByTestId("workspace-global-resources-file-count"),
      ).toBeVisible();

      // 点击刷新
      await panel.getByRole("button", { name: "刷新" }).click();

      // 刷新后头部仍然稳定
      await expect(
        panel.getByText("全局工作区", { exact: true }),
      ).toBeVisible();

      await page.screenshot({
        path: testInfo.outputPath("workspace-global-resources-header-count.png"),
        fullPage: true,
      });
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
