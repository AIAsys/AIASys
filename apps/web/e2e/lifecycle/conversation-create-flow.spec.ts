import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  addSessionMessage,
  createWorkspace,
  deleteSession,
  deleteWorkspace,
  extractSessionIdFromUrl,
  registerLifecycleUser,
} from "./support";

async function getConversationCount(
  api: APIRequestContext,
  workspaceId: string,
): Promise<number> {
  const response = await api.get(`/api/workspaces/${workspaceId}`);
  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { conversations?: unknown[] };
  return body.conversations?.length ?? 0;
}

test.describe("Conversation create flow browser regression", () => {
  // 回归 issue #147：工作区内点击“新建会话”后，新会话的 tokens/llm-selection
  // 短暂 404，随后界面回退到旧会话。根因是前端未调用 /api/sessions/create，
  // 后端没有新会话元数据，工作区列表刷新后路由同步把会话回退到旧会话。
  test("clicking 新建会话 switches to the new session stably without 404 or fallback", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const { workspaceId, currentSessionId } = await createWorkspace(api, {
      title: `浏览器回归-新建会话-${Date.now()}`,
    });
    let newSessionId: string | null = null;

    const notFoundUrls: string[] = [];
    page.on("response", (response) => {
      if (response.status() === 404) {
        notFoundUrls.push(response.url());
      }
    });

    try {
      // 旧会话先种一条消息，保证“当前工作区已经存在一个可正常访问的旧对话”
      await addSessionMessage(api, userId, currentSessionId, "旧会话的种子消息");

      await page.goto(
        `/workspace?workspace_id=${workspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();
      // 等旧会话历史恢复完成，确保当前会话非空
      await expect(page.getByText("旧会话的种子消息")).toBeVisible({
        timeout: 15_000,
      });

      await page.locator('button[title="新建会话"]').first().click();

      // URL 应切换到新 session
      await expect
        .poll(
          () => {
            const sid = extractSessionIdFromUrl(page.url());
            return sid && sid !== currentSessionId ? sid : null;
          },
          { timeout: 15_000 },
        )
        .not.toBeNull();
      newSessionId = extractSessionIdFromUrl(page.url());
      expect(newSessionId).toBeTruthy();

      // 稳定观察窗口：URL 不得回退到旧会话（issue #147 的核心症状）
      await page.waitForTimeout(5_000);
      expect(extractSessionIdFromUrl(page.url())).toBe(newSessionId);

      // 后端已创建新会话元数据：tokens / llm-selection 不能 404
      // 注意 tokens 端点挂在 /api/{user}/{session}/tokens（无 /sessions 前缀）
      const tokensResponse = await api.get(
        `/api/${userId}/${newSessionId}/tokens`,
      );
      expect(tokensResponse.ok()).toBeTruthy();
      const llmSelectionResponse = await api.get(
        `/api/sessions/${userId}/${newSessionId}/llm-selection`,
      );
      expect(llmSelectionResponse.ok()).toBeTruthy();

      // 前端捕获的 404 中不得包含新会话的 tokens / llm-selection 请求
      const sessionNotFound = notFoundUrls.filter(
        (url) =>
          newSessionId &&
          url.includes(newSessionId) &&
          (url.includes("/tokens") || url.includes("llm-selection")),
      );
      expect(sessionNotFound).toEqual([]);

      // 新会话应出现在侧边栏会话列表中
      await expect(page.getByText("新会话").first()).toBeVisible();
    } finally {
      await deleteWorkspace(api, workspaceId);
      await deleteSession(api, userId, newSessionId);
    }
  });

  // 空白会话上点击“新建会话”不重复创建，只给轻提示（防止列表堆积同名空会话）
  test("clicking 新建会话 on an empty session does not create another session", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const { workspaceId, currentSessionId } = await createWorkspace(api, {
      title: `浏览器回归-空白不新建-${Date.now()}`,
    });

    try {
      await page.goto(
        `/workspace?workspace_id=${workspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();
      // 等空会话的历史恢复与列表水合结束，避免恢复进行中误判
      await page.waitForTimeout(1_500);

      await page.locator('button[title="新建会话"]').first().click();

      // 轻提示可见
      await expect(
        page.getByText("当前已是空白会话，可直接输入"),
      ).toBeVisible();
      // URL 不变，仍停留在原会话
      expect(extractSessionIdFromUrl(page.url())).toBe(currentSessionId);
      // 后端会话数不增加
      expect(await getConversationCount(api, workspaceId)).toBe(1);
    } finally {
      await deleteWorkspace(api, workspaceId);
    }
  });

  // 创建接口失败时：停留在原会话并给出可见错误提示，不乐观切换
  test("create failure keeps the current session and shows an error toast", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const { workspaceId, currentSessionId } = await createWorkspace(api, {
      title: `浏览器回归-新建失败-${Date.now()}`,
    });

    try {
      await addSessionMessage(api, userId, currentSessionId, "旧会话的种子消息");

      await page.goto(
        `/workspace?workspace_id=${workspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();
      await expect(page.getByText("旧会话的种子消息")).toBeVisible({
        timeout: 15_000,
      });

      // 拦截创建接口，模拟后端失败
      await page.route("**/api/sessions/create", (route) =>
        route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "mock create failure" }),
        }),
      );

      await page.locator('button[title="新建会话"]').first().click();

      // 错误提示可见，且停留在原会话
      await expect(page.getByText("会话创建失败，请重试")).toBeVisible();
      expect(extractSessionIdFromUrl(page.url())).toBe(currentSessionId);
      await page.waitForTimeout(1_000);
      expect(extractSessionIdFromUrl(page.url())).toBe(currentSessionId);
      expect(await getConversationCount(api, workspaceId)).toBe(1);

      await page.unroute("**/api/sessions/create");
    } finally {
      await deleteWorkspace(api, workspaceId);
    }
  });

  // 连点三次只创建一条新会话（创建在途防重入 + 空白会话不重复新建）
  test("triple clicking 新建会话 creates exactly one new session", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const { workspaceId, currentSessionId } = await createWorkspace(api, {
      title: `浏览器回归-连点防重-${Date.now()}`,
    });
    let newSessionId: string | null = null;

    try {
      await addSessionMessage(api, userId, currentSessionId, "旧会话的种子消息");
      const countBefore = await getConversationCount(api, workspaceId);

      await page.goto(
        `/workspace?workspace_id=${workspaceId}&session_id=${currentSessionId}`,
        { waitUntil: "domcontentloaded" },
      );
      await expect(page.locator("textarea")).toBeVisible();
      await expect(page.getByText("旧会话的种子消息")).toBeVisible({
        timeout: 15_000,
      });

      const newButton = page.locator('button[title="新建会话"]').first();
      await newButton.click();
      await newButton.click();
      await newButton.click();

      // URL 切换到新会话且稳定
      await expect
        .poll(
          () => {
            const sid = extractSessionIdFromUrl(page.url());
            return sid && sid !== currentSessionId ? sid : null;
          },
          { timeout: 15_000 },
        )
        .not.toBeNull();
      newSessionId = extractSessionIdFromUrl(page.url());

      // 后端只多出一条会话
      await expect
        .poll(() => getConversationCount(api, workspaceId), {
          timeout: 10_000,
        })
        .toBe(countBefore + 1);
    } finally {
      await deleteWorkspace(api, workspaceId);
      await deleteSession(api, userId, newSessionId);
    }
  });
});
