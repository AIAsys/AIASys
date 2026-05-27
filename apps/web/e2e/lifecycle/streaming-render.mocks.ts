import type { Page } from "@playwright/test";

export const CHUNK_1 = "AlphaFlowChunkOne";
export const CHUNK_2 = "BetaFlowChunkTwo";
export const CHUNK_3 = "GammaFlowChunkThree";

export async function installMockStreamingResponse(page: Page) {
  await page.addInitScript(
    ({ chunk1, chunk2, chunk3 }) => {
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

        const frames = [
          {
            delayMs: 10,
            payload: 'data: {"type":"status","message":"开始分析任务..."}\n\n',
          },
          {
            delayMs: 40,
            payload: `data: {"type":"content","content_type":"text","text":"${chunk1}"}\n\n`,
          },
          {
            delayMs: 700,
            payload:
              'data: {"type":"tool_call","tool_call_id":"tc-1","tool_name":"IPythonBox","arguments":{"code":"print(42)"}}\n\n',
          },
          {
            delayMs: 80,
            payload:
              'data: {"type":"tool_result","tool_call_id":"tc-1","tool_name":"IPythonBox","content":"42","is_error":false}\n\n',
          },
          {
            delayMs: 700,
            payload: `data: {"type":"content","content_type":"text","text":"${chunk2}"}\n\n`,
          },
          {
            delayMs: 700,
            payload: `data: {"type":"content","content_type":"text","text":"${chunk3}"}\n\n`,
          },
          {
            delayMs: 40,
            payload: "data: [DONE]\n\n",
          },
        ];

        const body = new ReadableStream({
          start(controller) {
            let elapsed = 0;

            frames.forEach((frame, index) => {
              elapsed += frame.delayMs;
              window.setTimeout(() => {
                controller.enqueue(encoder.encode(frame.payload));
                if (index === frames.length - 1) {
                  controller.close();
                }
              }, elapsed);
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
      chunk1: CHUNK_1,
      chunk2: CHUNK_2,
      chunk3: CHUNK_3,
    },
  );
}

export async function installMockLocalNotebookFlow(page: Page) {
  await page.addInitScript(() => {
    const originalFetch = window.fetch.bind(window);
    const encoder = new TextEncoder();
    let runCompleted = false;

    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === "string"
          ? input
          : input instanceof URL
            ? input.href
            : input.url;

      if (url.includes("/api/sessions/status/")) {
        const sessionId = url.split("/").pop() || "unknown-session";
        const executionRecordCount = runCompleted ? 1 : 0;
        const lastRuntimeState = runCompleted ? "available" : "fresh";

        return new Response(
          JSON.stringify({
            session_id: sessionId,
            status: "active",
            title: "浏览器回归-本地执行流不闪退",
            message_count: 2,
            is_empty: false,
            can_edit_mcp: false,
            has_execution_journal: true,
            execution_record_count: executionRecordCount,
            recovery_policy: "journal_only",
            last_runtime_state: lastRuntimeState,
          }),
          {
            status: 200,
            headers: {
              "Content-Type": "application/json",
            },
          },
        );
      }

      if (url.includes("/api/agent/execution/") && url.endsWith("/flow")) {
        await new Promise((resolve) => window.setTimeout(resolve, 200));
        return new Response(JSON.stringify({ history: [] }), {
          status: 200,
          headers: {
            "Content-Type": "application/json",
          },
        });
      }

      if (!url.includes("/api/agent/execute/stream")) {
        return originalFetch(input, init);
      }

      const frames = [
        {
          delayMs: 20,
          payload:
            'data: {"type":"status","message":"开始本地分析任务..."}\n\n',
        },
        {
          delayMs: 40,
          payload:
            'data: {"type":"tool_call","tool_call_id":"tc-local-1","tool_name":"LocalIPythonBox","arguments":{"code":"print(98)"}}\n\n',
        },
        {
          delayMs: 60,
          payload:
            'data: {"type":"tool_result","tool_call_id":"tc-local-1","tool_name":"LocalIPythonBox","content":"98","is_error":false}\n\n',
        },
        {
          delayMs: 40,
          payload:
            'data: {"type":"content","content_type":"text","text":"本地执行完成。"}\n\n',
        },
        {
          delayMs: 20,
          payload: "data: [DONE]\n\n",
        },
      ];

      const body = new ReadableStream({
        start(controller) {
          let elapsed = 0;

          frames.forEach((frame, index) => {
            elapsed += frame.delayMs;
            window.setTimeout(() => {
              controller.enqueue(encoder.encode(frame.payload));
              if (index === frames.length - 1) {
                runCompleted = true;
                controller.close();
              }
            }, elapsed);
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
  });
}
