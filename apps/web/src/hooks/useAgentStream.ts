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

/** 计算 SSE 重连延迟：指数退避 + 抖动，最大 30 秒 */
function getReconnectDelay(attempt: number): number {
  const base = 1000;
  const maxDelay = 30000;
  const exponential = base * 2 ** attempt;
  const jitter = Math.random() * 1000;
  return Math.min(exponential + jitter, maxDelay);
}

export interface AgentStreamState {
  isConnected: boolean;
  isRunning: boolean;
  isComplete: boolean;
  error?: string;
  taskId?: string;
  isReconnecting?: boolean;
}

export interface StreamCallbacks {
  onEvent?: (event: AgentEvent) => void;
  onContent?: (content: string, type: "text" | "think") => void;
  onFinish?: () => void;
  onError?: (error: string) => void;
  /** SSE 重连前调用，用于清理上一轮残留的流式数据，避免内容重复 */
  onReconnect?: () => void;
}

/** 每个 session 的流条目 */
interface SessionStreamEntry {
  state: AgentStreamState;
  abortController: AbortController | null;
  taskId: string | undefined;
  requestId: number;
  userAborted: boolean;
  reconnectCount: number;
  heartbeatTimedOut: boolean;
  /** 最近一次收到心跳的时间戳，页面恢复可见时重置以避免节流导致的误判 */
  lastHeartbeatTime: number;
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
    userAborted: false,
    reconnectCount: 0,
    heartbeatTimedOut: false,
    lastHeartbeatTime: 0,
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
      entry.userAborted = true;
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

  // 页面恢复可见时重置心跳时间戳，避免后台定时器节流导致的心跳超时误判
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        sessionsRef.current.forEach((entry) => {
          if (entry.state.isConnected) {
            entry.lastHeartbeatTime = Date.now();
          }
        });
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
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
      entry.reconnectCount = 0;
      entry.state = {
        isConnected: false,
        isRunning: true,
        isComplete: false,
        error: undefined,
        taskId: undefined,
        isReconnecting: false,
      };
      entry.taskId = undefined;

      syncIfActive(sessionId, entry.state);
      setRunningSessionIds((prev) => {
        if (prev.has(sessionId)) return prev;
        const next = new Set(prev);
        next.add(sessionId);
        return next;
      });

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

      const MAX_RECONNECT = 5;

      for (let attempt = 0; attempt <= MAX_RECONNECT; attempt++) {
        const controller = new AbortController();
        entry.abortController = controller;
        entry.userAborted = false;
        entry.heartbeatTimedOut = false;
        const signal = controller.signal;

        let heartbeatChecker: ReturnType<typeof setInterval> | null = null;

        try {
          const response = await apiFetch(API_ENDPOINTS.AGENT_STREAM, {
            method: "POST",
            headers: { "X-Session-Id": sessionId },
            body,
            signal,
            timeoutMs: 300_000, // 5 分钟超时
          });

          if (!response.ok) {
            let detailMessage = "";
            try {
              const errorData = await response.json();
              const detail = errorData?.detail;
              if (typeof detail === "string") {
                detailMessage = detail;
              } else if (detail && typeof detail === "object") {
                detailMessage =
                  detail.message ||
                  detail.error ||
                  JSON.stringify(detail);
              } else {
                detailMessage = errorData?.message || "";
              }
            } catch {
              // 非 JSON 错误体，忽略
            }
            throw new Error(
              detailMessage
                ? `API Error: ${response.status} - ${detailMessage}`
                : `API Error: ${response.status}`,
            );
          }

          if (entry.requestId !== requestId) {
            return;
          }

          entry.state = { ...entry.state, isConnected: true, isReconnecting: false };
          syncIfActive(sessionId, entry.state);

          const reader = response.body?.getReader();
          const decoder = new TextDecoder();
          let pendingLine = "";

          if (!reader) {
            throw new Error("No response body");
          }

          // 心跳检测：超过 45 秒（3 个心跳周期）未收到 heartbeat 则主动中断并触发重连
          entry.lastHeartbeatTime = Date.now();
          heartbeatChecker = setInterval(() => {
            if (
              Date.now() - entry.lastHeartbeatTime > 45000 &&
              entry.requestId === requestId &&
              !entry.userAborted
            ) {
              entry.heartbeatTimedOut = true;
              controller.abort();
            }
          }, 5000);

          const finishStream = () => {
            if (heartbeatChecker) {
              clearInterval(heartbeatChecker);
              heartbeatChecker = null;
            }
            entry.reconnectCount = 0;
            entry.state = {
              ...entry.state,
              isConnected: false,
              isRunning: false,
              isComplete: true,
              isReconnecting: false,
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
              if (heartbeatChecker) {
                clearInterval(heartbeatChecker);
                heartbeatChecker = null;
              }
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
                  case "heartbeat":
                    entry.lastHeartbeatTime = Date.now();
                    break;

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
          // 流正常完成，退出重试循环
          break;
        } catch (error: unknown) {
          if (heartbeatChecker) {
            clearInterval(heartbeatChecker);
            heartbeatChecker = null;
          }

          if (isError(error) && error.name === "AbortError") {
            // User-initiated abort: silent
            if (entry.userAborted) {
              entry.userAborted = false;
              return;
            }
            // 心跳超时触发的 abort — 尝试重连
            if (entry.heartbeatTimedOut && attempt < MAX_RECONNECT) {
              entry.reconnectCount = attempt + 1;
              entry.state = {
                ...entry.state,
                isReconnecting: true,
                isConnected: false,
                error: undefined,
              };
              syncIfActive(sessionId, entry.state);
              await new Promise((resolve) =>
                setTimeout(resolve, getReconnectDelay(attempt)),
              );
              if (entry.requestId !== requestId || entry.userAborted) return;
              // 重连前清理上一轮残留的流式数据，避免后端重放导致内容重复
              callbacks?.onReconnect?.();
              entry.state = {
                ...entry.state,
                isReconnecting: false,
                isRunning: true,
                isConnected: false,
              };
              syncIfActive(sessionId, entry.state);
              continue;
            }
            // Timeout-triggered abort: notify user
            if (entry.requestId === requestId) {
              const timeoutMsg = "请求超时（5分钟），请检查网络或重试";
              entry.state = {
                ...entry.state,
                isConnected: false,
                isRunning: false,
                isComplete: true,
                error: timeoutMsg,
                isReconnecting: false,
              };
              syncIfActive(sessionId, entry.state);
              setRunningSessionIds((prev) => {
                if (!prev.has(sessionId)) return prev;
                const next = new Set(prev);
                next.delete(sessionId);
                return next;
              });
              callbacks?.onError?.(timeoutMsg);
            }
            return;
          }

          if (entry.requestId !== requestId) {
            return;
          }

          const errMsg = getErrorMessage(error);
          const isNetworkError =
            /fetch|network|failed to fetch/i.test(errMsg);

          // 网络错误 — 尝试重连
          if (isNetworkError && !entry.userAborted && attempt < MAX_RECONNECT) {
            entry.reconnectCount = attempt + 1;
            entry.state = {
              ...entry.state,
              isReconnecting: true,
              isConnected: false,
              error: undefined,
            };
            syncIfActive(sessionId, entry.state);
            await new Promise((resolve) =>
              setTimeout(resolve, getReconnectDelay(attempt)),
            );
            if (entry.requestId !== requestId || entry.userAborted) return;
            // 重连前清理上一轮残留的流式数据，避免后端重放导致内容重复
            callbacks?.onReconnect?.();
            entry.state = {
              ...entry.state,
              isReconnecting: false,
              isRunning: true,
              isConnected: false,
            };
            syncIfActive(sessionId, entry.state);
            continue;
          }

          // 最终错误
          entry.state = {
            ...entry.state,
            isConnected: false,
            isRunning: false,
            isComplete: true,
            error: errMsg,
            isReconnecting: false,
          };
          syncIfActive(sessionId, entry.state);
          setRunningSessionIds((prev) => {
            if (!prev.has(sessionId)) return prev;
            const next = new Set(prev);
            next.delete(sessionId);
            return next;
          });
          callbacks?.onError?.(errMsg);
          break;
        } finally {
          if (heartbeatChecker) {
            clearInterval(heartbeatChecker);
            heartbeatChecker = null;
          }
          if (
            entry.requestId === requestId &&
            entry.abortController === controller
          ) {
            entry.abortController = null;
          }
          // 保留 entry 不删除，只有明确的 removeSession 才清理
        }
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
