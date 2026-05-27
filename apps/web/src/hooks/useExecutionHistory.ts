/**
 * 执行历史 Hook
 *
 * 获取 Agent 执行历史和 Task 执行流程
 */

import { useCallback, useState } from "react";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { ApiRequestError, apiRequest } from "@/lib/api/httpClient";
import type {
  ExecutionFlowResponse,
  ExecutionEvent,
} from "@/types/api";

export interface UseExecutionHistoryReturn {
  /** 执行流程事件 */
  events: ExecutionEvent[];
  /** Task 数量 */
  taskCount: number;
  /** 是否加载中 */
  isLoading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 加载执行流程 */
  loadExecutionFlow: (sessionId: string) => Promise<void>;
  /** 重置状态 */
  reset: () => void;
}

/**
 * 执行历史 Hook
 */
export function useExecutionHistory(): UseExecutionHistoryReturn {
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [taskCount, setTaskCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  /**
   * 加载执行流程
   */
  const loadExecutionFlow = useCallback(async (sessionId: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const userId = getCurrentUserId();
      const endpoint = API_ENDPOINTS.EXECUTION_FLOW(userId, sessionId);
      const data = await apiRequest<ExecutionFlowResponse>(endpoint);
      setEvents(data.events);
      setTaskCount(data.task_count);
    } catch (err) {
      if (err instanceof ApiRequestError && err.status === 404) {
        setEvents([]);
        setTaskCount(0);
        return;
      }
      const errorMsg = err instanceof Error ? err.message : "未知错误";
      setError(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  /**
   * 重置状态
   */
  const reset = useCallback(() => {
    setEvents([]);
    setTaskCount(0);
    setError(null);
    setIsLoading(false);
  }, []);

  return {
    events,
    taskCount,
    isLoading,
    error,
    loadExecutionFlow,
    reset,
  };
}
