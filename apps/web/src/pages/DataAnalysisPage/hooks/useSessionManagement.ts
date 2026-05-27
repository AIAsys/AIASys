import { useCallback, useRef, useState } from "react";
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
  const latestSelectRequestRef = useRef(0);
  const hasLoadedHistoryRef = useRef(false);
  const isLoadingRef = useRef(false);
  const conversationsRef = useRef<Conversation[]>([]);
  conversationsRef.current = conversations;

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
      hasLoadedHistoryRef.current = true;
      if (shouldShowLoading) {
        setIsLoadingConversations(false);
      }
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
      setIsRestoringSession(true);

      const restoredItems: ChatItem[] = [];

      try {
        const userId = getCurrentUserId();
        const endpoint = API_ENDPOINTS.SESSION_HISTORY(userId, sid);
        const data = await apiRequest<{ messages?: HistoryMessage[] }>(
          `${apiBaseUrl}${endpoint}`,
        );
        const messages = (data.messages || []) as HistoryMessage[];
        restoredItems.push(...restoreChatItemsFromHistory(sid, messages));

        if (requestId !== latestSelectRequestRef.current) {
          return restoredItems;
        }

        await onSessionSelect?.(sid, restoredItems);
      } catch (error) {
        if (error instanceof ApiRequestError && error.status === 401) {
          console.warn("Session management: 401 Unauthorized");
          return restoredItems;
        }
        console.error("Failed to load session:", error);
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
        title: title || "新对话",
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

    // 异步更新后端标题
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
    }
  }, [apiBaseUrl]);

  return {
    conversations,
    isLoadingHistory: isLoadingConversations,
    isRestoringSession,
    loadConversations,
    handleSessionSelect,
    handleDeleteSession,
    addOptimisticSession,
    updateSessionTitle,
  };
}
