import { expect, test, type Page } from "@playwright/test";

import {
  createWorkspace,
  deleteWorkspace,
  registerLifecycleUser,
} from "./support";

const FIRST_BLOCK = "长流式内容第一段";
const LAST_BLOCK = "长流式内容最终段";

async function installLongStreamingResponse(page: Page) {
  await page.addInitScript(
    ({ firstBlock, lastBlock }) => {
      const originalFetch = window.fetch.bind(window);
      const encoder = new TextEncoder();

      window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
        const url =
          typeof input === "string"
            ? input
            : input instanceof URL
              ? input.href
              : input.url;

        if (!url.includes("/api/agent/execute/stream")) {
          return originalFetch(input, init);
        }

        const chunks = Array.from({ length: 48 }, (_, index) => {
          const label =
            index === 0
              ? firstBlock
              : index === 47
                ? lastBlock
                : `长流式内容第 ${String(index + 1).padStart(2, "0")} 段`;
          return `${label}\n\n这是一段用于撑高右侧对话滚动容器的回归文本。当前段落会持续追加，确保流式输出期间 scrollHeight 不断增长。\n\n`;
        });

        const body = new ReadableStream({
          start(controller) {
            controller.enqueue(
              encoder.encode(
                'data: {"type":"status","message":"开始生成长回复..."}\n\n',
              ),
            );

            chunks.forEach((chunk, index) => {
              window.setTimeout(() => {
                controller.enqueue(
                  encoder.encode(
                    `data: ${JSON.stringify({
                      type: "content",
                      content_type: "text",
                      text: chunk,
                    })}\n\n`,
                  ),
                );
                if (index === chunks.length - 1) {
                  controller.enqueue(encoder.encode("data: [DONE]\n\n"));
                  controller.close();
                }
              }, 80 + index * 120);
            });
          },
        });

        return new Response(body, {
          status: 200,
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
          },
        });
      };
    },
    {
      firstBlock: FIRST_BLOCK,
      lastBlock: LAST_BLOCK,
    },
  );
}

test.describe("Streaming chat scroll control", () => {
  test("keeps following at bottom, pauses after manual upward scroll, and resumes from the bottom button", async ({
    page,
  }) => {
    const api = page.request;
    await registerLifecycleUser(api);
    const workspace = await createWorkspace(api, {
      title: `浏览器回归-流式滚动控制-${Date.now()}`,
      mode: "analysis",
      initialConversationTitle: "流式滚动控制会话",
    });

    try {
      await installLongStreamingResponse(page);
      await page.goto(
        `/analysis?workspace_id=${workspace.workspaceId}&session_id=${workspace.currentConversationId}`,
        { waitUntil: "domcontentloaded" },
      );

      const input = page.locator("textarea");
      const scrollContainer = page.getByTestId("chat-scroll-container");
      await expect(input).toBeVisible();
      await expect(scrollContainer).toBeVisible();

      await input.fill("请输出一段很长的流式回复，用来验证滚动控制");
      await input.press("Enter");

      await expect(page.getByText(FIRST_BLOCK)).toBeVisible();
      await expect
        .poll(
          async () =>
            scrollContainer.evaluate(
              (element) =>
                element.scrollHeight - element.scrollTop - element.clientHeight,
            ),
          { timeout: 10_000 },
        )
        .toBeLessThanOrEqual(120);

      await expect
        .poll(
          async () =>
            scrollContainer.evaluate((element) => element.scrollHeight),
          { timeout: 10_000 },
        )
        .toBeGreaterThan(1200);

      const pausedTop = await scrollContainer.evaluate((element) => {
        element.scrollTop = Math.max(0, element.scrollHeight * 0.35);
        element.dispatchEvent(new Event("scroll", { bubbles: true }));
        return element.scrollTop;
      });

      await expect(page.getByTestId("chat-scroll-to-bottom")).toBeVisible();

      await page.waitForTimeout(1500);
      const topAfterMoreChunks = await scrollContainer.evaluate(
        (element) => element.scrollTop,
      );
      expect(Math.abs(topAfterMoreChunks - pausedTop)).toBeLessThan(80);

      await expect(page.getByText(LAST_BLOCK)).toBeVisible({ timeout: 10_000 });
      await page.getByTestId("chat-scroll-to-bottom").click();
      await expect(page.getByTestId("chat-scroll-to-bottom")).toHaveCount(0);
      await expect
        .poll(
          async () =>
            scrollContainer.evaluate(
              (element) =>
                element.scrollHeight - element.scrollTop - element.clientHeight,
            ),
          { timeout: 5_000 },
        )
        .toBeLessThanOrEqual(120);
    } finally {
      await deleteWorkspace(api, workspace.workspaceId);
    }
  });
});
