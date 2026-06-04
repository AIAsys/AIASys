/**
 * Agent流式交互Hook
 *
 * 封装与后端 Agent API 的流式通信
 * 支持多 session 并行流：每个 session 持有独立的 AbortController 和状态
 * 只有活跃 session 的状态同步到 React useState
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { getErrorMessage, isError } from "@/lib/utils";
import { API_ENDPOINTS } from "@/config/api";
import { apiFetch } from "@/lib/api/httpClient";
import type { AgentExecuteRequest, AgentEvent } from "@/types/api";

export interface AgentStreamState {
  isConnected: boolean;
  isRunning: boolean;
  isComplete: boolean;
  error?: string;
  taskId?: string;
}

export interface StreamCallbacks {
  onEvent?: (event: AgentEvent) => void;
  onContent?: (content: string, type: "text" | "think") => void;
  onFinish?: () => void;
  onError?: (error: string) => void;
}

/** 每个 session 的流条目 */
interface SessionStreamEntry {
  state: AgentStreamState;
  abortController: AbortController | null;
  taskId: string | undefined;
  requestId: number;
}

function createEmptyStreamEntry(): SessionStreamEntry {
  return {
    state: {
      isConnected: false,
      isRunning: false,
      isComplete: false,
    },
    abortController: null,
    taskId: undefined,
    requestId: 0,
  };
}

export interface UseAgentStreamResult {
  /** 活跃 session 的流式状态 */
  state: AgentStreamState;
  /** 发起流式请求 */
  run: (
    input: string,
    sessionId: string,
    callbacks?: StreamCallbacks,
    providerId?: string,
    attachments?: string[],
    workspaceId?: string | null,
    thinkingEnabled?: boolean,
    thinkingEffort?: string,
  ) => Promise<void>;
  /** 停止指定 session 的流 */
  stopSession: (sessionId: string) => void;
  /** 停止当前活跃 session */
  stop: () => void;
  /** 重置活跃 session 状态 */
  reset: () => void;
  /** 设置活跃 session */
  setActiveSession: (sessionId: string) => void;
  /** 查询指定 session 是否正在运行 */
  isSessionRunning: (sessionId: string) => boolean;
  /** 当前所有正在运行的 session ID 集合 */
  runningSessionIds: Set<string>;
  /** 移除指定 session 的 entry */
  removeSession: (sessionId: string) => void;
}

/**
 * Agent流式交互Hook — 支持多 session 并行
 */
export function useAgentStream(): UseAgentStreamResult {
  const [state, setState] = useState<AgentStreamState>({
    isConnected: false,
    isRunning: false,
    isComplete: false,
  });

  // 所有 session 的流条目
  const sessionsRef = useRef<Map<string, SessionStreamEntry>>(new Map());
  // 当前活跃 session ID
  const activeSessionIdRef = useRef<string>("");
  // 正在运行的 session IDs — 轻量 React 状态，驱动侧边栏指示器
  const [runningSessionIds, setRunningSessionIds] = useState<Set<string>>(
    new Set(),
  );

  /** 获取或创建 session 条目 */
  const getEntry = (sessionId: string): SessionStreamEntry => {
    let entry = sessionsRef.current.get(sessionId);
    if (!entry) {
      entry = createEmptyStreamEntry();
      sessionsRef.current.set(sessionId, entry);
    }
    return entry;
  };

  /** 如果是活跃 session，同步状态到 React */
  const syncIfActive = (sessionId: string, newState: AgentStreamState) => {
    if (sessionId === activeSessionIdRef.current) {
      setState(newState);
    }
  };

  /** 停止指定 session 的流 */
  const stopSession = useCallback(
    (sessionId: string) => {
      const entry = sessionsRef.current.get(sessionId);
      if (!entry) return;

      entry.requestId += 1;
      if (entry.abortController) {
        entry.abortController.abort();
        entry.abortController = null;
      }
      entry.state = {
        ...entry.state,
        isConnected: false,
        isRunning: false,
      };

      syncIfActive(sessionId, entry.state);
      setRunningSessionIds((prev) => {
        if (!prev.has(sessionId)) return prev;
        const next = new Set(prev);
        next.delete(sessionId);
        return next;
      });
      // 不在这里删除 entry，保留 completed/error 状态供切回时读取
      // 明确的 session 删除由调用方通过 removeSession 处理
    },
    [],
  );

  /** 停止活跃 session */
  const stop = useCallback(() => {
    if (activeSessionIdRef.current) {
      stopSession(activeSessionIdRef.current);
    }
  }, [stopSession]);

  /** 重置活跃 session 状态 */
  const reset = useCallback(() => {
    const sessionId = activeSessionIdRef.current;
    if (sessionId) {
      stopSession(sessionId);
      const entry = getEntry(sessionId);
      entry.taskId = undefined;
      entry.state = {
        isConnected: false,
        isRunning: false,
        isComplete: false,
        error: undefined,
        taskId: undefined,
      };
      syncIfActive(sessionId, entry.state);
    }
  }, [stopSession]);

  /** 设置活跃 session */
  const setActiveSession = useCallback(
    (sessionId: string) => {
      if (activeSessionIdRef.current === sessionId) return; // 避免不必要的 setState
      activeSessionIdRef.current = sessionId;
      const entry = getEntry(sessionId);
      setState(entry.state);
    },
    [],
  );

  /** 查询指定 session 是否正在运行 */
  const isSessionRunning = (sessionId: string): boolean => {
    const entry = sessionsRef.current.get(sessionId);
    return entry?.state.isRunning ?? false;
  };

  /** 移除指定 session 的 entry（在 session 被删除时调用） */
  const removeSession = useCallback((sessionId: string) => {
    const entry = sessionsRef.current.get(sessionId);
    if (entry?.abortController) {
      entry.abortController.abort();
      entry.abortController = null;
    }
    sessionsRef.current.delete(sessionId);
    setRunningSessionIds((prev) => {
      if (!prev.has(sessionId)) return prev;
      const next = new Set(prev);
      next.delete(sessionId);
      return next;
    });
  }, []);

  // 组件卸载时停止所有流并清理内存
  useEffect(() => {
    const sessions = sessionsRef.current;
    return () => {
      sessions.forEach((entry) => {
        if (entry.abortController) {
          entry.abortController.abort();
        }
      });
      sessions.clear();
    };
  }, []);

  const run = useCallback(
    async (
      input: string,
      sessionId: string,
      callbacks?: StreamCallbacks,
      modelId?: string,
      attachments?: string[],
      workspaceId?: string | null,
      thinkingEnabled?: boolean,
      thinkingEffort?: string,
    ) => {
      // 只停止同一 session 的旧流，不影响其他 session
      stopSession(sessionId);

      const entry = getEntry(sessionId);
      const requestId = entry.requestId + 1;
      entry.requestId = requestId;
      entry.state = {
        isConnected: false,
        isRunning: true,
        isComplete: false,
        error: undefined,
        taskId: undefined,
      };
      entry.taskId = undefined;

      syncIfActive(sessionId, entry.state);
      setRunningSessionIds((prev) => {
        if (prev.has(sessionId)) return prev;
        const next = new Set(prev);
        next.add(sessionId);
        return next;
      });

      const controller = new AbortController();
      entry.abortController = controller;
      const signal = controller.signal;

      const body: AgentExecuteRequest = {
        prompt: input,
        session_id: sessionId,
        workspace_id: workspaceId || undefined,
        model_id: modelId,
        attachments,
        thinking_enabled: thinkingEnabled,
        thinking_effort: thinkingEffort,
        // user_id 不传，后端会从当前本地用户上下文解析真实身份
      };

      try {
        const response = await apiFetch(API_ENDPOINTS.AGENT_STREAM, {
          method: "POST",
          headers: { "X-Session-Id": sessionId },
          body,
          signal,
          timeoutMs: 300_000, // 5 分钟超时
        });

        if (!response.ok) {
          throw new Error(`API Error: ${response.status}`);
        }

        if (entry.requestId !== requestId) {
          return;
        }

        entry.state = { ...entry.state, isConnected: true };
        syncIfActive(sessionId, entry.state);

        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let pendingLine = "";

        if (!reader) {
          throw new Error("No response body");
        }

        const finishStream = () => {
          entry.state = {
            ...entry.state,
            isConnected: false,
            isRunning: false,
            isComplete: true,
          };
          syncIfActive(sessionId, entry.state);
          setRunningSessionIds((prev) => {
            if (!prev.has(sessionId)) return prev;
            const next = new Set(prev);
            next.delete(sessionId);
            return next;
          });
          // 保留 entry 不删除，切回 session 时仍能读取最终状态
        };

        while (true) {
          const { done, value } = await reader.read();

          if (entry.requestId !== requestId) {
            return;
          }

          if (done) {
            finishStream();
            callbacks?.onFinish?.();
            break;
          }

          pendingLine += decoder.decode(value, { stream: true });
          const lines = pendingLine.split(/\r?\n/);
          pendingLine = lines.pop() ?? "";

          for (const line of lines) {
            if (!line.startsWith("data:")) continue;

            const data = line.slice(5).trimStart();
            if (data === "[DONE]") {
              finishStream();
              callbacks?.onFinish?.();
              return;
            }

            try {
              const event: AgentEvent = JSON.parse(data);

              callbacks?.onEvent?.(event);

              switch (event.type) {
                case "content":
                  if (event.content_type === "text" && event.text) {
                    callbacks?.onContent?.(event.text, "text");
                  } else if (event.content_type === "think" && event.think) {
                    callbacks?.onContent?.(event.think, "think");
                  }
                  break;

                case "tool_call":
                  break;

                case "tool_result":
                  break;

                case "subagent_content":
                case "subagent_tool_call":
                case "subagent_tool_result":
                case "subagent_step_begin":
                  if (
                    "task_tool_call_id" in event &&
                    event.task_tool_call_id &&
                    !entry.taskId
                  ) {
                    entry.taskId = event.task_tool_call_id;
                    entry.state = {
                      ...entry.state,
                      taskId: event.task_tool_call_id,
                    };
                    syncIfActive(sessionId, entry.state);
                  }
                  break;

                case "file_changes":
                  break;

                case "error":
                  if ("message" in event && event.message) {
                    if (entry.requestId === requestId) {
                      callbacks?.onError?.(event.message);
                    }
                  }
                  break;
              }
            } catch (parseError) {
              console.warn("SSE 事件解析失败", line, parseError);
            }
          }
        }
      } catch (error: unknown) {
        if (isError(error) && error.name === "AbortError") {
          return;
        }

        if (entry.requestId !== requestId) {
          return;
        }

        const errMsg = getErrorMessage(error);
        entry.state = {
          ...entry.state,
          isConnected: false,
          isRunning: false,
          isComplete: true,
          error: errMsg,
        };
        syncIfActive(sessionId, entry.state);
        setRunningSessionIds((prev) => {
          if (!prev.has(sessionId)) return prev;
          const next = new Set(prev);
          next.delete(sessionId);
          return next;
        });
        callbacks?.onError?.(errMsg);
      } finally {
        if (
          entry.requestId === requestId &&
          entry.abortController === controller
        ) {
          entry.abortController = null;
        }
        // 保留 entry 不删除，只有明确的 removeSession 才清理
      }
    },
    [stopSession],
  );

  return {
    state,
    run,
    stop,
    stopSession,
    reset,
    setActiveSession,
    isSessionRunning,
    runningSessionIds,
    removeSession,
  };
}
