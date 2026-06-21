/**
 * 子 Agent API 客户端
 *
 * 提供子 Agent 继续对话、关闭、恢复、独立 SSE 事件流等能力。
 */

import { apiFetch, apiRequest } from "@/lib/api/httpClient";

export interface SubagentMessageRequest {
  message: string;
}

export interface SubagentCloseResponse {
  success: boolean;
  agent_id: string;
}

export interface SubagentResumeResponse {
  success: boolean;
  agent_id: string;
}

export type SubagentEventCallback = (event: Record<string, unknown>) => void;
export type SubagentErrorCallback = (error: string) => void;
export type SubagentDoneCallback = () => void;

function getSubagentBasePath(
  userId: string,
  sessionId: string,
  agentId: string,
): string {
  return `/api/sessions/${userId}/${sessionId}/subagents/${agentId}`;
}

export async function sendSubagentMessage(
  userId: string,
  sessionId: string,
  agentId: string,
  message: string,
): Promise<Response> {
  return apiFetch(getSubagentBasePath(userId, sessionId, agentId) + "/message", {
    method: "POST",
    body: { message },
    timeoutMs: 300_000,
  });
}

export async function closeSubagent(
  userId: string,
  sessionId: string,
  agentId: string,
): Promise<SubagentCloseResponse> {
  return apiRequest<SubagentCloseResponse>(
    getSubagentBasePath(userId, sessionId, agentId) + "/close",
    { method: "POST" },
  );
}

export async function resumeSubagent(
  userId: string,
  sessionId: string,
  agentId: string,
): Promise<SubagentResumeResponse> {
  return apiRequest<SubagentResumeResponse>(
    getSubagentBasePath(userId, sessionId, agentId) + "/resume",
    { method: "POST" },
  );
}

export interface StreamSubagentEventsOptions {
  lastEventId?: number;
  onEvent?: SubagentEventCallback;
  onError?: SubagentErrorCallback;
  onDone?: SubagentDoneCallback;
  signal?: AbortSignal;
}

const MAX_RECONNECT_ATTEMPTS = 5;

function getReconnectDelayMs(attempt: number): number {
  const base = 1000;
  const maxDelay = 30000;
  const exponential = base * 2 ** attempt;
  const jitter = Math.random() * 1000;
  return Math.min(exponential + jitter, maxDelay);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal.aborted) {
      reject(new Error("Aborted"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new Error("Aborted"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function streamSubagentEvents(
  userId: string,
  sessionId: string,
  agentId: string,
  options: StreamSubagentEventsOptions = {},
): () => void {
  const { onEvent, onError, onDone, signal } = options;
  const abortController = new AbortController();

  if (signal) {
    if (signal.aborted) {
      abortController.abort();
    } else {
      signal.addEventListener("abort", () => abortController.abort(), {
        once: true,
      });
    }
  }

  let currentLastEventId = options.lastEventId ?? 0;
  let attempt = 0;
  let finished = false;

  const finish = () => {
    if (finished) return;
    finished = true;
    onDone?.();
  };

  (async () => {
    while (!abortController.signal.aborted) {
      const path =
        getSubagentBasePath(userId, sessionId, agentId) +
        `/events?last_event_id=${currentLastEventId}`;

      try {
        const response = await apiFetch(path, {
          method: "GET",
          signal: abortController.signal,
          timeoutMs: 0,
        });

        if (!response.ok) {
          if (response.status >= 400 && response.status < 500) {
            onError?.(`HTTP ${response.status}`);
            return;
          }
          throw new Error(`HTTP ${response.status}`);
        }

        attempt = 0;
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let pendingLine = "";

        if (!reader) {
          onError?.("No response body");
          return;
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) {
            finish();
            return;
          }

          pendingLine += decoder.decode(value, { stream: true });
          const lines = pendingLine.split(/\r?\n/);
          pendingLine = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trimStart();
            if (data === "[DONE]") {
              finish();
              return;
            }
            try {
              const event = JSON.parse(data) as Record<string, unknown>;
              const eventId = event.event_id;
              if (typeof eventId === "number") {
                currentLastEventId = Math.max(currentLastEventId, eventId);
              }
              onEvent?.(event);
            } catch (parseError) {
              console.warn("子 Agent SSE 事件解析失败", line, parseError);
            }
          }
        }
      } catch (error: unknown) {
        const err = error as Error;
        if (err.name === "AbortError" || err.message === "Aborted") {
          finish();
          return;
        }

        if (finished || abortController.signal.aborted) {
          return;
        }

        if (attempt >= MAX_RECONNECT_ATTEMPTS) {
          onError?.(err.message || "子 Agent SSE 连接失败，已超出最大重连次数");
          return;
        }

        try {
          await sleep(getReconnectDelayMs(attempt), abortController.signal);
        } catch {
          finish();
          return;
        }
        attempt += 1;
      }
    }
  })();

  return () => {
    abortController.abort();
  };
}
