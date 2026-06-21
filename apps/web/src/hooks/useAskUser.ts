/**
 * AskUser Hook
 *
 * 管理 AskUser 对话框状态和响应
 * 支持 per-session 队列：多 session 并发时按 sessionId 隔离请求
 */

import { useState, useCallback, useRef } from 'react';
import { API_BASE_URL } from '@/config/api';
import { apiFetch } from '@/lib/api/httpClient';
import type {
  AskUserRequest,
  AskUserResolveRequest,
  AskUserResolveResponse,
  AskUserValue,
} from '@/types/askUser';

interface UseAskUserOptions {
  onResponse?: (requestId: string, approved: boolean, value?: AskUserValue, sessionId?: string) => void;
}

export type AskUserRequestErrorCode =
  | 'forbidden'
  | 'not_found'
  | 'server'
  | 'network';

export interface AskUserRequestError {
  code: AskUserRequestErrorCode;
  message: string;
}

async function readAskUserErrorMessage(res: Response): Promise<string> {
  const contentType = res.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    try {
      const data = (await res.json()) as { detail?: string; message?: string };
      return data.detail || data.message || 'AskUser 请求处理失败';
    } catch {
      return 'AskUser 请求处理失败';
    }
  }

  const text = await res.text();
  return text || 'AskUser 请求处理失败';
}

function mapAskUserRequestError(
  status: number,
  message: string,
): AskUserRequestError {
  if (status === 403) {
    return {
      code: 'forbidden',
      message: message || '当前登录用户无权处理这个 AskUser 请求。',
    };
  }

  if (status === 404) {
    return {
      code: 'not_found',
      message: message || '这个 AskUser 请求已失效、超时，或已经被处理。',
    };
  }

  return {
    code: 'server',
    message: message || 'AskUser 请求处理失败，请稍后重试。',
  };
}

export function useAskUser(options: UseAskUserOptions = {}) {
  const [currentRequest, setCurrentRequest] = useState<AskUserRequest | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [requestError, setRequestError] = useState<AskUserRequestError | null>(null);
  const responseCallbackRef = useRef(options.onResponse);
  const currentRequestRef = useRef<AskUserRequest | null>(null);

  // Per-session request queue
  const requestQueueMapRef = useRef<Map<string, AskUserRequest[]>>(new Map());
  const requestIdToSessionIdRef = useRef<Map<string, string>>(new Map());
  const activeSessionIdRef = useRef<string>("");
  const currentRequestSessionIdRef = useRef<string>("");

  useEffect(() => {
    responseCallbackRef.current = options.onResponse;
    currentRequestRef.current = currentRequest;
  }, [options.onResponse, currentRequest]);

  const getQueue = useCallback((sessionId: string): AskUserRequest[] => {
    return requestQueueMapRef.current.get(sessionId) || [];
  }, []);

  const setQueue = useCallback((sessionId: string, queue: AskUserRequest[]) => {
    if (queue.length === 0) {
      requestQueueMapRef.current.delete(sessionId);
    } else {
      requestQueueMapRef.current.set(sessionId, queue);
    }
  }, []);

  const clearVisibleRequest = useCallback(() => {
    currentRequestSessionIdRef.current = "";
    setCurrentRequest(null);
    setIsLoading(false);
    setRequestError(null);
  }, []);

  const showQueueHead = useCallback((sessionId: string) => {
    const queue = getQueue(sessionId);
    const nextRequest = queue[0] || null;

    if (nextRequest) {
      currentRequestSessionIdRef.current = sessionId;
      setCurrentRequest(nextRequest);
      setIsLoading(false);
      setRequestError(null);
      return;
    }

    clearVisibleRequest();
  }, [clearVisibleRequest, getQueue]);

  const removeRequestFromQueue = useCallback((sessionId: string, requestId: string) => {
    const nextQueue = getQueue(sessionId).filter(
      (request) => request.request_id !== requestId,
    );
    setQueue(sessionId, nextQueue);
    requestIdToSessionIdRef.current.delete(requestId);
    return nextQueue;
  }, [getQueue, setQueue]);

  /** 响应成功后推进队列：有下一个请求就展示，否则清空当前请求 */
  const advanceQueue = useCallback((ownerSessionId?: string) => {
    const activeId = activeSessionIdRef.current;
    if (ownerSessionId && ownerSessionId === activeId) {
      showQueueHead(ownerSessionId);
      return;
    }
    clearVisibleRequest();
  }, [showQueueHead, clearVisibleRequest]);

  /** 设置活跃 session ID */
  const setActiveSessionId = useCallback((sessionId: string) => {
    const prevId = activeSessionIdRef.current;
    activeSessionIdRef.current = sessionId;

    // 切换 session 时，检查新 session 是否有暂存的 AskUser 请求
    if (sessionId !== prevId) {
      showQueueHead(sessionId);
    }
  }, [showQueueHead]);

  /**
   * 显示 AskUser 对话框（session-aware）
   */
  const showAskUser = useCallback((request: AskUserRequest, sessionId?: string) => {
    const targetSessionId = sessionId || activeSessionIdRef.current;
    const queue = getQueue(targetSessionId);
    const existingIndex = queue.findIndex(
      (item) => item.request_id === request.request_id,
    );
    const nextQueue =
      existingIndex >= 0
        ? queue.map((item) =>
            item.request_id === request.request_id ? request : item,
          )
        : [...queue, request];

    // 存入 per-session Queue，并记录 requestId -> sessionId 映射
    setQueue(targetSessionId, nextQueue);
    requestIdToSessionIdRef.current.set(request.request_id, targetSessionId);

    // 只有活跃 session 且当前没有正在展示该 session 请求时才弹出队头请求
    if (
      targetSessionId === activeSessionIdRef.current &&
      (!currentRequestRef.current ||
        currentRequestSessionIdRef.current !== targetSessionId)
    ) {
      currentRequestSessionIdRef.current = targetSessionId;
      setCurrentRequest(nextQueue[0]);
      setIsLoading(false);
      setRequestError(null);
    } else if (
      targetSessionId === activeSessionIdRef.current &&
      currentRequestRef.current?.request_id === request.request_id
    ) {
      setCurrentRequest(request);
      setIsLoading(false);
      setRequestError(null);
    }
    // 后台 session 或当前已有前台请求时，后续请求保留在队列中
  }, [getQueue, setQueue]);

  /**
   * 发送用户响应到后端
   */
  const sendResponse = useCallback(async (
    approved: boolean,
    value?: AskUserValue
  ): Promise<boolean> => {
    if (!currentRequest) return false;

    setIsLoading(true);
    setRequestError(null);

    try {
      const payload: AskUserResolveRequest = {
        request_id: currentRequest.request_id,
        approved,
        value,
      };

      const res = await apiFetch(`${API_BASE_URL}/api/ask-user/resolve`, {
        method: 'POST',
        body: payload,
      });

      if (!res.ok) {
        // 404 表示请求已不存在（已超时或已被其他客户端处理），视为成功清理
        if (res.status === 404) {
          const ownerSessionId =
            currentRequestSessionIdRef.current || activeSessionIdRef.current;
          if (ownerSessionId) {
            removeRequestFromQueue(ownerSessionId, currentRequest.request_id);
          }
          responseCallbackRef.current?.(currentRequest.request_id, approved, value, ownerSessionId);
          advanceQueue(ownerSessionId);
          return true;
        }
        const message = await readAskUserErrorMessage(res);
        setRequestError(mapAskUserRequestError(res.status, message));
        return false;
      }

      const data: AskUserResolveResponse = await res.json();

      if (data.success) {
        const ownerSessionId =
          currentRequestSessionIdRef.current || activeSessionIdRef.current;
        if (ownerSessionId) {
          removeRequestFromQueue(ownerSessionId, currentRequest.request_id);
        }

        responseCallbackRef.current?.(currentRequest.request_id, approved, value, ownerSessionId);
        advanceQueue(ownerSessionId);
        return true;
      } else {
        setRequestError({
          code: 'server',
          message: data.message || 'AskUser 请求处理失败，请稍后重试。',
        });
        return false;
      }
    } catch (error) {
      console.error('Failed to send ask user response:', error);
      setRequestError({
        code: 'network',
        message:
          error instanceof Error
            ? error.message
            : '网络异常，AskUser 请求尚未提交成功。',
      });
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [currentRequest, removeRequestFromQueue, advanceQueue]);

  /**
   * 按 requestId 发送响应（用于内联卡片，非弹窗模式）
   */
  const resolveRequestById = useCallback(async (
    requestId: string,
    approved: boolean,
    value?: AskUserValue
  ): Promise<boolean> => {
    // 如果 requestId 匹配当前请求，直接走 sendResponse
    if (currentRequestRef.current?.request_id === requestId) {
      return sendResponse(approved, value);
    }

    // 不匹配当前请求时直接发 API（请求可能还在队列中）
    try {
      const payload: AskUserResolveRequest = {
        request_id: requestId,
        approved,
        value,
      };
      const res = await apiFetch(`${API_BASE_URL}/api/ask-user/resolve`, {
        method: 'POST',
        body: payload,
      });
      // 404 表示请求已不存在（已超时或已被其他客户端处理），视为成功清理
      if (!res.ok && res.status === 404) {
        const ownerSessionId = requestIdToSessionIdRef.current.get(requestId);
        if (ownerSessionId) {
          removeRequestFromQueue(ownerSessionId, requestId);
        }
        responseCallbackRef.current?.(requestId, approved, value, ownerSessionId);
        if (currentRequestRef.current?.request_id === requestId) {
          advanceQueue(ownerSessionId ?? undefined);
        }
        return true;
      }
      if (!res.ok) return false;
      const data: AskUserResolveResponse = await res.json();
      if (data.success) {
        const ownerSessionId = requestIdToSessionIdRef.current.get(requestId);
        if (ownerSessionId) {
          removeRequestFromQueue(ownerSessionId, requestId);
        }
        responseCallbackRef.current?.(requestId, approved, value, ownerSessionId);
        if (currentRequestRef.current?.request_id === requestId) {
          advanceQueue(ownerSessionId ?? undefined);
        }
      }
      return data.success;
    } catch {
      return false;
    }
  }, [sendResponse, removeRequestFromQueue, advanceQueue]);

  /**
   * 处理 SSE 中的 AskUser 事件
   */
  const handleAskUserEvent = useCallback((event: { payload: AskUserRequest }, sessionId?: string) => {
    showAskUser(event.payload, sessionId);
  }, [showAskUser]);

  /**
   * 关闭并移除当前已失效的请求，让队列继续推进。
   */
  const dismissCurrentRequest = useCallback(() => {
    const requestId = currentRequestRef.current?.request_id;
    const ownerSessionId =
      currentRequestSessionIdRef.current || activeSessionIdRef.current;

    if (!requestId || !ownerSessionId) {
      clearVisibleRequest();
      return;
    }

    removeRequestFromQueue(ownerSessionId, requestId);

    if (ownerSessionId === activeSessionIdRef.current) {
      showQueueHead(ownerSessionId);
      return;
    }

    clearVisibleRequest();
  }, [clearVisibleRequest, removeRequestFromQueue, showQueueHead]);

  /**
   * 获取 requestId 所属的 sessionId
   */
  const getRequestSessionId = useCallback((requestId: string): string | undefined => {
    return requestIdToSessionIdRef.current.get(requestId);
  }, []);

  /**
   * 移除指定 session 的所有 AskUser 数据
   */
  const removeSession = useCallback((sessionId: string) => {
    const queue = requestQueueMapRef.current.get(sessionId) || [];
    for (const req of queue) {
      requestIdToSessionIdRef.current.delete(req.request_id);
    }
    requestQueueMapRef.current.delete(sessionId);
    if (sessionId === currentRequestSessionIdRef.current) {
      clearVisibleRequest();
    }
  }, [clearVisibleRequest]);

  return {
    currentRequest,
    isLoading,
    requestError,
    showAskUser,
    sendResponse,
    resolveRequestById,
    getRequestSessionId,
    handleAskUserEvent,
    dismissCurrentRequest,
    setActiveSessionId,
    removeSession,
  };
}
