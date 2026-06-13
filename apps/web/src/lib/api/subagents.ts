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

export function streamSubagentEvents(
  userId: string,
  sessionId: string,
  agentId: string,
  options: StreamSubagentEventsOptions = {},
): () => void {
  const { lastEventId = 0, onEvent, onError, onDone, signal } = options;
  const abortController = new AbortController();

  if (signal) {
    if (signal.aborted) {
      abortController.abort();
    } else {
      signal.addEventListener("abort", () => abortController.abort(), { once: true });
    }
  }

  const path =
    getSubagentBasePath(userId, sessionId, agentId) +
    `/events?last_event_id=${lastEventId}`;

  (async () => {
    try {
      const response = await apiFetch(path, {
        method: "GET",
        signal: abortController.signal,
        timeoutMs: 0,
      });

      if (!response.ok) {
        onError?.(`HTTP ${response.status}`);
        return;
      }

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
          onDone?.();
          break;
        }

        pendingLine += decoder.decode(value, { stream: true });
        const lines = pendingLine.split(/\r?\n/);
        pendingLine = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data:")) continue;
          const data = line.slice(5).trimStart();
          if (data === "[DONE]") {
            onDone?.();
            return;
          }
          try {
            const event = JSON.parse(data) as Record<string, unknown>;
            onEvent?.(event);
          } catch (parseError) {
            console.warn("子 Agent SSE 事件解析失败", line, parseError);
          }
        }
      }
    } catch (error: unknown) {
      const err = error as Error;
      if (err.name === "AbortError") {
        onDone?.();
        return;
      }
      onError?.(err.message || "Unknown error");
    }
  })();

  return () => {
    abortController.abort();
  };
}
