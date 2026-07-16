import { useCallback, useEffect, useRef, useState } from "react";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";

import { ApiRequestError, apiRequest } from "@/lib/api/httpClient";
import type { ChatItem, Conversation } from "../types";
import {
  restoreChatItemsFromHistory,
  type HistoryMessage,
} from "./sessionManagementHistory";
import {
  filterVisibleConversations,
  isHiddenSession,
} from "./hiddenSessionRegistry";
import { emitWorkspaceListRefreshEvent } from "./workspaceListRefreshEvent";
import { DEFAULT_CONVERSATION_TITLE } from "@/lib/conversationTitles";
import type {
  UseSessionManagementProps,
  UseSessionManagementReturn,
} from "./sessionManagementTypes";
import { sessionsEqual } from "./sessionManagementUtils";

export function useSessionManagement({
  apiBaseUrl,
  initialSessionId,
  onSessionSelect,
}: UseSessionManagementProps): UseSessionManagementReturn {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [isLoadingConversations, setIsLoadingConversations] = useState(true);
  const [isRestoringSession, setIsRestoringSession] = useState(
    Boolean(initialSessionId),
  );
  const [historyLoadError, setHistoryLoadError] = useState<string | null>(null);
  const latestSelectRequestRef = useRef(0);
  const latestSelectTargetRef = useRef<string | null>(null);
  const loadedHistorySessionsRef = useRef<Set<string>>(new Set());
  const sessionHasMoreRef = useRef<Map<string, boolean>>(new Map());
  const sessionOldestIndexRef = useRef<Map<string, number>>(new Map());
  const loadingMoreRef = useRef<Set<string>>(new Set());
  const hasLoadedHistoryRef = useRef(false);
  const isLoadingRef = useRef(false);
  const conversationsRef = useRef<Conversation[]>([]);
  useEffect(() => {
    conversationsRef.current = conversations;
  }, [conversations]);
  const lastUpdatedTitleRef = useRef<Map<string, string>>(new Map());

  const loadConversations = useCallback(async () => {
    if (isLoadingRef.current) {
      return;
    }

    isLoadingRef.current = true;
    const shouldShowLoading =
      !hasLoadedHistoryRef.current && conversationsRef.current.length === 0;

    if (shouldShowLoading) {
      setIsLoadingConversations(true);
    }

    try {
      const userId = getCurrentUserId();
      const endpoint = API_ENDPOINTS.SESSIONS_LIST(userId);
      try {
        const data = await apiRequest<{
          sessions?: Array<{
            session_id: string;
            title: string;
            updated_at: string;
            message_count: number;
            workspace_file_count: number;
            conversation_type?: string;
            project_id?: string | null;
            bound_lead_session_id?: string | null;
            team_id?: string | null;
            assignment_id?: string | null;
            assignment_title?: string | null;
            source?: string | null;
            auto_task_id?: string | null;
          }>;
        }>(`${apiBaseUrl}${endpoint}`);

        // 字段映射：将 API 返回的 snake_case 映射为前端类型
        const mappedSessions: Conversation[] = (data.sessions || []).map(
          (session) => ({
            session_id: session.session_id,
            title: session.title || "",
            updated_at: session.updated_at,
            message_count: session.message_count,
            workspace_file_count: session.workspace_file_count,
            conversation_type: session.conversation_type as Conversation['conversation_type'],
            project_id: session.project_id,
            bound_lead_session_id: session.bound_lead_session_id,
            team_id: session.team_id,
            assignment_id: session.assignment_id,
            assignment_title: session.assignment_title ?? undefined,
            source: session.source as Conversation['source'],
            auto_task_id: session.auto_task_id,
          }),
        );

        const nextSessions = filterVisibleConversations(mappedSessions);
        setConversations((previousSessions) =>
          sessionsEqual(previousSessions, nextSessions)
            ? previousSessions
            : nextSessions,
        );
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 401) {
          setConversations([]);
          return;
        }
        throw error;
      }
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        setConversations([]);
        return;
      }
      console.error("Failed to load history sessions:", error);
    } finally {
      if (shouldShowLoading) {
        setIsLoadingConversations(false);
      }
      hasLoadedHistoryRef.current = true;
      isLoadingRef.current = false;
    }
  }, [apiBaseUrl]);

  const handleDeleteSession = useCallback(
    async (sid: string) => {
      try {
        const userId = getCurrentUserId();
        const endpoint = API_ENDPOINTS.SESSION_DELETE(userId, sid);
        await apiRequest<{ success?: boolean; detail?: string }>(
          `${apiBaseUrl}${endpoint}`,
          {
            method: "DELETE",
          },
        );

        setConversations((previousSessions) =>
          previousSessions.filter((session) => session.session_id !== sid),
        );
        emitWorkspaceListRefreshEvent();
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 401) {
          return;
        }
        console.error("Failed to delete session:", error);
      }
    },
    [apiBaseUrl],
  );

  const handleSessionSelect = useCallback(
    async (sid: string): Promise<ChatItem[]> => {
      latestSelectRequestRef.current += 1;
      const requestId = latestSelectRequestRef.current;
      latestSelectTargetRef.current = sid;
      setIsRestoringSession(true);
      setHistoryLoadError(null);

      const restoredItems: ChatItem[] = [];

      try {
        const userId = getCurrentUserId();
        // 首次加载某个会话时只取最近 50 条消息，避免大对话全量加载
        const isFirstLoad = !loadedHistorySessionsRef.current.has(sid);
        const historyLimit = isFirstLoad ? 50 : 0;
        const endpoint = API_ENDPOINTS.SESSION_HISTORY(userId, sid);
        const data = await apiRequest<{
          messages?: HistoryMessage[];
          total_messages?: number;
          has_more?: boolean;
          has_more_before?: boolean;
          oldest_loaded_index?: number;
        }>(`${apiBaseUrl}${endpoint}${historyLimit > 0 ? `?limit=${historyLimit}` : ""}`);
        const messages = (data.messages || []) as HistoryMessage[];
        restoredItems.push(...restoreChatItemsFromHistory(sid, messages));

        // 记录分页状态
        if (isFirstLoad) {
          sessionHasMoreRef.current.set(sid, Boolean(data.has_more_before ?? data.has_more));
          sessionOldestIndexRef.current.set(sid, data.oldest_loaded_index ?? 0);
        }

        // 标记该会话历史已加载过，下次切换回来不再限制条数
        loadedHistorySessionsRef.current.add(sid);

        // 同时检查 requestId 和目标 sessionId，防止 A->B->A 快速切换时迟到回包覆盖
        if (
          requestId !== latestSelectRequestRef.current ||
          sid !== latestSelectTargetRef.current
        ) {
          return restoredItems;
        }

        await onSessionSelect?.(sid, restoredItems);
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 401) {
          console.warn("Session management: 401 Unauthorized");
          return restoredItems;
        }
        console.error("Failed to load session:", error);
        if (
          requestId === latestSelectRequestRef.current &&
          sid === latestSelectTargetRef.current
        ) {
          setHistoryLoadError(
            error instanceof Error ? error.message : "加载会话历史失败",
          );
        }
      } finally {
        if (requestId === latestSelectRequestRef.current) {
          setIsRestoringSession(false);
        }
      }

      return restoredItems;
    },
    [apiBaseUrl, onSessionSelect],
  );

  const addOptimisticSession = useCallback((sessionId: string, title?: string) => {
    if (isHiddenSession(sessionId)) {
      return;
    }

    setConversations((previousSessions) => {
      if (previousSessions.some((session) => session.session_id === sessionId)) {
        return previousSessions;
      }

      const nextSession: Conversation = {
        session_id: sessionId,
        title: title || DEFAULT_CONVERSATION_TITLE,
        updated_at: new Date().toISOString(),
        message_count: 0,
        workspace_file_count: 0,
      };

      return [nextSession, ...previousSessions];
    });
  }, []);

  const updateSessionTitle = useCallback(async (sessionId: string, title: string) => {
    if (isHiddenSession(sessionId)) {
      return;
    }

    // 先更新前端状态
    setConversations((prev) => {
      const exists = prev.some((s) => s.session_id === sessionId);
      if (exists) {
        return prev.map((s) =>
          s.session_id === sessionId
            ? { ...s, title, updated_at: new Date().toISOString() }
            : s,
        );
      }
      // 会话不在列表中（如初始会话），插入到顶部
      const newSession: Conversation = {
        session_id: sessionId,
        title,
        updated_at: new Date().toISOString(),
        message_count: 1,
        workspace_file_count: 0,
      };
      return [newSession, ...prev];
    });

    // 异步更新后端标题，相同标题在短周期内不重复发请求
    const lastTitle = lastUpdatedTitleRef.current.get(sessionId);
    if (lastTitle === title) {
      return;
    }
    lastUpdatedTitleRef.current.set(sessionId, title);

    try {
      const userId = getCurrentUserId();
      await apiRequest(
        `${apiBaseUrl}${API_ENDPOINTS.SESSION_UPDATE_TITLE(userId, sessionId)}`,
        {
          method: "POST",
          body: { title },
        }
      );
      emitWorkspaceListRefreshEvent();
    } catch (error) {
      console.error("Failed to update session title on backend:", error);
      // 请求失败时清除缓存，允许下次重试
      lastUpdatedTitleRef.current.delete(sessionId);
    }
  }, [apiBaseUrl]);

  const loadMoreHistory = useCallback(
    async (sid: string): Promise<ChatItem[] | null> => {
      if (loadingMoreRef.current.has(sid)) return null;
      const hasMore = sessionHasMoreRef.current.get(sid);
      if (!hasMore) return null;

      loadingMoreRef.current.add(sid);
      try {
        const userId = getCurrentUserId();
        const before = sessionOldestIndexRef.current.get(sid) ?? 0;
        const endpoint = API_ENDPOINTS.SESSION_HISTORY(userId, sid);
        const data = await apiRequest<{
          messages?: HistoryMessage[];
          has_more_before?: boolean;
          oldest_loaded_index?: number;
        }>(`${apiBaseUrl}${endpoint}?limit=50&before=${before}`);
        const messages = (data.messages || []) as HistoryMessage[];
        const olderItems = restoreChatItemsFromHistory(sid, messages);

        sessionHasMoreRef.current.set(sid, Boolean(data.has_more_before));
        sessionOldestIndexRef.current.set(sid, data.oldest_loaded_index ?? 0);

        return olderItems;
      } catch (error) {
        console.error("Failed to load more history:", error);
        return null;
      } finally {
        loadingMoreRef.current.delete(sid);
      }
    },
    [apiBaseUrl],
  );

  const hasMoreHistory = useCallback((sid: string): boolean => {
    return Boolean(sessionHasMoreRef.current.get(sid));
  }, []);

  return {
    conversations,
    isLoadingHistory: isLoadingConversations,
    isRestoringSession,
    historyLoadError,
    loadConversations,
    handleSessionSelect,
    handleDeleteSession,
    addOptimisticSession,
    updateSessionTitle,
    loadMoreHistory,
    hasMoreHistory,
  };
}
