import { expect, test } from "@playwright/test";

import {
  createSession,
  createWorkspace,
  deleteSession,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";
import { gotoAnalysisSession } from "./data-analysis-helpers";
import {
  CHUNK_1,
  CHUNK_2,
  CHUNK_3,
  installMockLocalNotebookFlow,
  installMockStreamingResponse,
} from "./streaming-render.mocks";

test.describe("DataAnalysis streaming browser regression", () => {
  test("renders host text incrementally while preserving tool call cards", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const sessionId = await createSession(api, {
      title: "浏览器回归-流式增量渲染",
      sandboxMode: "local",
    });

    try {
      await installMockStreamingResponse(page);
      await gotoAnalysisSession(page, sessionId);

      const input = page.locator("textarea");
      await input.fill("请模拟一段带工具调用的流式回复");
      await input.press("Enter");

      await expect(page.getByText(CHUNK_1, { exact: true })).toBeVisible();
      await expect(page.getByText(CHUNK_2, { exact: true })).toHaveCount(0);
      await expect(page.getByText(CHUNK_3, { exact: true })).toHaveCount(0);

      await expect(page.getByText("IPythonBox", { exact: true })).toBeVisible();

      await expect
        .poll(async () => {
          const bodyText = (await page.locator("body").textContent()) || "";
          return bodyText.includes(CHUNK_2) && !bodyText.includes(CHUNK_3);
        }, {
          timeout: 15_000,
        })
        .toBe(true);
      await expect
        .poll(async () => (await page.locator("body").textContent()) || "", {
          timeout: 15_000,
        })
        .toContain(CHUNK_3);

      await expect
        .poll(async () => await input.isEnabled(), { timeout: 10_000 })
        .toBe(true);
    } finally {
      await deleteSession(api, userId, sessionId);
    }
  });

  test("refreshes token usage after streaming turns in the same branch", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-上下文统计刷新-${Date.now()}`,
      initialConversationTitle: "上下文统计刷新会话",
      mode: "analysis",
    });
    const sessionId = workspace.currentConversationId;
    let tokenStatsCalls = 0;
    let streamStarted = false;

    try {
      await page.route(
        `**/api/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/tokens`,
        async (route) => {
          tokenStatsCalls += 1;
          const contextTokens = streamStarted ? 1234 : 0;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              tokens_used: 0,
              token_budget: null,
              context_tokens: contextTokens,
              context_window: 200000,
              context_usage_pct: contextTokens === 0 ? 0 : 0.6,
              budget_status: "active",
            }),
          });
        },
      );
      await page.route("**/api/agent/execute/stream", async (route) => {
        streamStarted = true;
        await route.fulfill({
          status: 200,
          contentType: "text/event-stream",
          headers: {
            "Cache-Control": "no-cache",
          },
          body: [
            `data: {"type":"content","content_type":"text","text":"${CHUNK_1}"}`,
            "data: [DONE]",
            "",
          ].join("\n\n"),
        });
      });
      await gotoAnalysisSession(page, sessionId, workspace.workspaceId);

      await expect(page.getByTestId("context-usage-value")).toHaveText("0/200K");

      const input = page.locator("textarea");
      await input.fill("请模拟一段用于刷新上下文统计的回复");
      await input.press("Enter");

      await expect(page.getByText(CHUNK_1, { exact: true })).toBeVisible();
      await expect
        .poll(async () => await page.getByTestId("context-usage-value").textContent(), {
          timeout: 10_000,
        })
        .toBe("1K/200K");
      expect(tokenStatsCalls).toBeGreaterThanOrEqual(2);
    } finally {
      await page.unroute(
        `**/api/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/tokens`,
      );
      await page.unroute("**/api/agent/execute/stream");
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });

  test("keeps LocalIPythonBox execution detail accessible after stream completion", async ({
    page,
  }) => {
    const api = page.request;
    const { userId } = await registerLifecycleUser(api);
    const sessionId = await createSession(api, {
      title: "浏览器回归-本地执行流不闪退",
      sandboxMode: "local",
    });

    try {
      await installMockLocalNotebookFlow(page);
      await gotoAnalysisSession(page, sessionId);

      const input = page.locator("textarea");
      await input.fill("请运行一段本地 python 代码");
      await input.press("Enter");

      const toolDetailButton = page.getByRole("button", {
        name: "LocalIPythonBox 点击查看详情 →",
      });
      await expect(toolDetailButton).toBeVisible();
      await expect(page.getByRole("button", { name: "查看执行记录" })).toBeVisible();
      await toolDetailButton.click();

      await expect(page.getByText("本地笔记本执行")).toBeVisible();
      await expect(page.getByText("输入参数")).toBeVisible();
      await expect(page.getByText("执行结果")).toBeVisible();
      await expect(page.getByText("print(98)")).toBeVisible();
      await expect(page.getByText("98", { exact: true })).toBeVisible();

      await expect
        .poll(async () => await input.isEnabled(), { timeout: 10_000 })
        .toBe(true);

      await page.waitForTimeout(3000);

      await expect(toolDetailButton).toBeVisible();
      await expect(page.getByText("本地笔记本执行")).toBeVisible();
      await expect(page.getByText("print(98)")).toBeVisible();
      await expect(page.getByText("98", { exact: true })).toBeVisible();
    } finally {
      await deleteSession(api, userId, sessionId);
    }
  });
});
