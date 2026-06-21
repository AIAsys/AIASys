/**
 * useSubagentStream - 子 Agent 独立对话流 Hook
 *
 * 管理单个 Subagent Tab 的：
 * - 历史详情加载
 * - 继续对话消息列表
 * - 发送消息并消费 SSE 流
 * - 关闭/恢复子 Agent
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest } from "@/lib/api/httpClient";
import {
  closeSubagent,
  resumeSubagent,
  sendSubagentMessage,
  streamSubagentEvents,
} from "@/lib/api/subagents";
import type { SubAgentDetail } from "@/hooks/useExecutionTree";
import type { MessageChatItem } from "@/pages/WorkspacePage/types";

export interface UseSubagentStreamOptions {
  userId?: string;
  sessionId?: string;
  agentId?: string;
}

export interface UseSubagentStreamReturn {
  detail: SubAgentDetail | null;
  chatItems: MessageChatItem[];
  isLoading: boolean;
  isRunning: boolean;
  error: string | null;
  sendMessage: (message: string) => Promise<void>;
  close: () => Promise<void>;
  resume: () => Promise<void>;
}

function generateId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function createUserChatItem(message: string): MessageChatItem {
  return {
    type: "message",
    id: generateId("user"),
    sender: "user",
    role: "user",
    content: message,
    timestamp: new Date(),
  };
}

function createAiChatItem(text: string = "", isStreaming: boolean = true): MessageChatItem {
  return {
    type: "message",
    id: generateId("ai"),
    sender: "ai",
    role: "assistant",
    content: text,
    segments: text ? [{ type: "text", content: text }] : [],
    timestamp: new Date(),
    isStreaming,
  };
}

export function useSubagentStream(
  options: UseSubagentStreamOptions,
): UseSubagentStreamReturn {
  const { userId, sessionId, agentId } = options;

  const [detail, setDetail] = useState<SubAgentDetail | null>(null);
  const [chatItems, setChatItems] = useState<MessageChatItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isRunningRef = useRef(false);
  const abortControllerRef = useRef<AbortController | null>(null);
  const sseCleanupRef = useRef<(() => void) | null>(null);
  const mountedRef = useRef(true);
  // 记录已消费的 wire event_id，重连时从该位置继续，避免重复渲染
  const lastEventIdRef = useRef(0);

  // Keep isRunningRef in sync
  useEffect(() => {
    isRunningRef.current = isRunning;
  }, [isRunning]);

  // Track unmount to prevent SSE reconnect after unmount
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // 加载子 Agent 详情
  const loadDetail = useCallback(async () => {
    if (!userId || !sessionId || !agentId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiRequest<SubAgentDetail>(
        `/api/sessions/${userId}/${sessionId}/subagents/${agentId}`,
      );
      setDetail(data);
      // wire.jsonl 中 metadata 占第 0 行（event_id=1），detail.events 已跳过 metadata。
      // 已有 N 个事件时，最后一个事件 event_id=N+1，下一条新事件 event_id=N+2，因此 lastEventId=N+1。
      lastEventIdRef.current = (data.events?.length ?? 0) + 1;
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载详情失败");
    } finally {
      setIsLoading(false);
    }
  }, [userId, sessionId, agentId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  // SSE 事件处理器（初始连接和重连共用）
  const handleSseEvent = useCallback(
    (event: Record<string, unknown>) => {
      const eventId = typeof event.event_id === "number" ? event.event_id : null;
      if (eventId !== null && eventId <= lastEventIdRef.current) {
        return;
      }
      if (eventId !== null) {
        lastEventIdRef.current = eventId;
      }

      if (event.type === "content" && typeof event.text === "string") {
        const text = event.text;
        setChatItems((prev) => {
          const last = prev[prev.length - 1];
          if (last && last.sender === "ai" && last.isStreaming) {
            const updated = { ...last };
            updated.content = (updated.content || "") + text;
            updated.segments = [{ type: "text", content: updated.content }];
            return [...prev.slice(0, -1), updated];
          }
          return [...prev, createAiChatItem(text, true)];
        });
      } else if (event.type === "tool_call") {
        setChatItems((prev) => [
          ...prev,
          {
            type: "message",
            id: generateId("tool-call"),
            sender: "tool",
            role: "tool",
            content: `工具调用: ${String(event.tool_name || "unknown")}`,
            timestamp: new Date(),
          },
        ]);
      } else if (event.type === "tool_result") {
        setChatItems((prev) => [
          ...prev,
          {
            type: "message",
            id: generateId("tool-result"),
            sender: "tool",
            role: "tool",
            content: String(event.content || ""),
            timestamp: new Date(),
          },
        ]);
      } else if (event.type === "system_warning") {
        setError(String(event.text || "子 Agent 返回警告"));
      } else if (event.type === "ask_user_request") {
        const requestText =
          typeof event.request === "object" && event.request !== null
            ? String((event.request as Record<string, unknown>).prompt || "")
            : "";
        setChatItems((prev) => [
          ...prev,
          {
            type: "message",
            id: generateId("ask-user"),
            sender: "system",
            role: "system",
            content: requestText
              ? `[子 Agent 等待用户确认] ${requestText}`
              : "子 Agent 等待用户确认",
            timestamp: new Date(),
          },
        ]);
      } else if (
        event.type === "capability_confirmation" ||
        event.type === "subagent_capability_confirmation"
      ) {
        const toolName = String(event.tool_name || "unknown");
        setChatItems((prev) => [
          ...prev,
          {
            type: "message",
            id: generateId("capability-confirmation"),
            sender: "system",
            role: "system",
            content: `[子 Agent 能力确认] 工具: ${toolName}`,
            timestamp: new Date(),
          },
        ]);
      }
    },
    [],
  );

  const handleSseError = useCallback((err: string) => {
    console.warn("子 Agent SSE 错误:", err);
  }, []);

  // 建立独立 SSE 连接，用于接收其他来源（如 Host 触发）的子 Agent 事件
  useEffect(() => {
    if (!userId || !sessionId || !agentId || !detail) return;

    const cleanup = streamSubagentEvents(userId, sessionId, agentId, {
      lastEventId: lastEventIdRef.current,
      onEvent: handleSseEvent,
      onError: handleSseError,
    });

    sseCleanupRef.current = cleanup;
    return () => {
      cleanup();
      sseCleanupRef.current = null;
    };
  }, [userId, sessionId, agentId, detail, handleSseEvent, handleSseError]);

  const sendMessage = useCallback(
    async (message: string) => {
      if (!userId || !sessionId || !agentId || !message.trim() || isRunningRef.current) return;

      // 取消可能存在的旧 SSE，避免重复消费
      sseCleanupRef.current?.();

      isRunningRef.current = true;
      setIsRunning(true);
      setError(null);
      setChatItems((prev) => [...prev, createUserChatItem(message.trim())]);

      abortControllerRef.current = new AbortController();
      let aiItemId: string | null = null;
      let streamEventCount = 0;

      try {
        const response = await sendSubagentMessage(
          userId,
          sessionId,
          agentId,
          message.trim(),
        );

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let pendingLine = "";

        if (!reader) {
          throw new Error("No response body");
        }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          pendingLine += decoder.decode(value, { stream: true });
          const lines = pendingLine.split(/\r?\n/);
          pendingLine = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;
            const data = line.slice(5).trimStart();
            if (data === "[DONE]") break;

            try {
              const event = JSON.parse(data) as Record<string, unknown>;
              streamEventCount += 1;
              if (event.type === "content" && typeof event.text === "string") {
                const text = event.text;
                setChatItems((prev) => {
                  if (!aiItemId) {
                    const item = createAiChatItem(text, true);
                    aiItemId = item.id;
                    return [...prev, item];
                  }
                  return prev.map((item) => {
                    if (item.id !== aiItemId) return item;
                    const updatedContent = (item.content || "") + text;
                    return {
                      ...item,
                      content: updatedContent,
                      segments: [{ type: "text", content: updatedContent }],
                    };
                  });
                });
              } else if (event.type === "tool_call") {
                setChatItems((prev) => [
                  ...prev,
                  {
                    type: "message",
                    id: generateId("tool-call"),
                    sender: "tool",
                    role: "tool",
                    content: `工具调用: ${String(event.tool_name || "unknown")}`,
                    timestamp: new Date(),
                  },
                ]);
              } else if (event.type === "tool_result") {
                setChatItems((prev) => [
                  ...prev,
                  {
                    type: "message",
                    id: generateId("tool-result"),
                    sender: "tool",
                    role: "tool",
                    content: String(event.content || ""),
                    timestamp: new Date(),
                  },
                ]);
              } else if (event.type === "system_warning") {
                setError(String(event.text || "子 Agent 返回警告"));
              }
            } catch (parseError) {
              console.warn("SSE 事件解析失败", line, parseError);
            }
          }
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "发送消息失败");
      } finally {
        isRunningRef.current = false;
        setIsRunning(false);
        if (aiItemId) {
          setChatItems((prev) =>
            prev.map((item) =>
              item.id === aiItemId ? { ...item, isStreaming: false } : item,
            ),
          );
        }
        // 重新建立 SSE 连接，跳过本次已处理的事件，避免重复渲染
        if (mountedRef.current) {
          lastEventIdRef.current += streamEventCount;
          sseCleanupRef.current = streamSubagentEvents(userId, sessionId, agentId, {
            lastEventId: lastEventIdRef.current,
            onEvent: handleSseEvent,
            onError: handleSseError,
          });
        }
      }
    },
    [userId, sessionId, agentId, handleSseEvent, handleSseError],
  );

  const close = useCallback(async () => {
    if (!userId || !sessionId || !agentId) return;
    try {
      await closeSubagent(userId, sessionId, agentId);
      await loadDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : "关闭失败");
    }
  }, [userId, sessionId, agentId, loadDetail]);

  const resume = useCallback(async () => {
    if (!userId || !sessionId || !agentId) return;
    try {
      await resumeSubagent(userId, sessionId, agentId);
      await loadDetail();
    } catch (err) {
      setError(err instanceof Error ? err.message : "恢复失败");
    }
  }, [userId, sessionId, agentId, loadDetail]);

  return {
    detail,
    chatItems,
    isLoading,
    isRunning,
    error,
    sendMessage,
    close,
    resume,
  };
}
