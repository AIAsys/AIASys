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

  const abortControllerRef = useRef<AbortController | null>(null);
  const sseCleanupRef = useRef<(() => void) | null>(null);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载详情失败");
    } finally {
      setIsLoading(false);
    }
  }, [userId, sessionId, agentId]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  // 建立独立 SSE 连接，用于接收其他来源（如 Host 触发）的子 Agent 事件
  useEffect(() => {
    if (!userId || !sessionId || !agentId) return;

    const cleanup = streamSubagentEvents(userId, sessionId, agentId, {
      onEvent: (event) => {
        // 只处理来自外部的事件；sendMessage 产生的事件由 sendMessage 自己处理
        if (isRunning) return;
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
        }
      },
      onError: (err) => {
        console.warn("子 Agent SSE 错误:", err);
      },
    });

    sseCleanupRef.current = cleanup;
    return () => {
      cleanup();
      sseCleanupRef.current = null;
    };
  }, [userId, sessionId, agentId, isRunning]);

  const sendMessage = useCallback(
    async (message: string) => {
      if (!userId || !sessionId || !agentId || !message.trim() || isRunning) return;

      // 取消可能存在的旧 SSE，避免重复消费
      sseCleanupRef.current?.();

      setIsRunning(true);
      setError(null);
      setChatItems((prev) => [...prev, createUserChatItem(message.trim())]);

      abortControllerRef.current = new AbortController();
      let aiItemId: string | null = null;

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
        setIsRunning(false);
        if (aiItemId) {
          setChatItems((prev) =>
            prev.map((item) =>
              item.id === aiItemId ? { ...item, isStreaming: false } : item,
            ),
          );
        }
        // 重新建立 SSE 连接
        sseCleanupRef.current = streamSubagentEvents(userId, sessionId, agentId, {
          onEvent: () => {},
          onError: () => {},
        });
      }
    },
    [userId, sessionId, agentId, isRunning],
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
