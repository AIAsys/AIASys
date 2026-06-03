import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatItem } from "../../types";
import { generateUUID } from "../../../../hooks/useAgentFileUpload";
import { useSessionManagement } from "../useSessionManagement";
import { registerHiddenSession, unregisterHiddenSession } from "../hiddenSessionRegistry";
import { restoreSessionState } from "./sessionRestore";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { WorkspaceFile, TaskEvent } from "@/types/task";
import {
  navigateToAnalysisSession,
  requestAvailableDraftId,
  requestDraftCleanup,
} from "./useSessionOrchestratorHelpers";
import {
  useSessionBootstrapEffects,
  useSessionPrewarmEffect,
} from "./useSessionOrchestratorEffects";
import type {
  SessionDeletionOptions,
  SessionSelectionOptions,
} from "./executorTypes";

interface UseSessionOrchestratorProps {
  apiBaseUrl: string;
  initialSessionId?: string | null;
  chatItems: ChatItem[];
  clearChat: () => void;
  clearFiles: () => void;
  /** 切换聊天 session */
  switchChatSession: (fromId: string, toId: string) => void;
  /** 切换多任务 session */
  switchMultiTaskSession: (fromId: string, toId: string) => void;
  /** 设置活跃流 session */
  setActiveStreamSession: (toId: string) => void;
  /** 初始化聊天 session */
  initChatSession: (id: string) => void;
  /** 初始化多任务 session */
  initMultiTaskSession: (id: string) => void;
  /** 停止指定 session 的流 */
  stopSession: (sessionId: string) => void;
  setChatItems: (
    items: ChatItem[] | ((prev: ChatItem[]) => ChatItem[]),
  ) => void;
  completeHost: () => void;
  reloadWorkspaceFiles: (
    workspaceId?: string,
    options?: { force?: boolean },
  ) => Promise<UploadedFile[]>;
  updateWorkspaceFilesForSession: (
    sessionId: string,
    files: WorkspaceFile[],
  ) => void;
  syncExecutionHistory: (taskId: string, sessionId: string) => Promise<void>;
  setIsRightSidebarOpen: (open: boolean) => void;
  setUserClosedSidebar: (closed: boolean) => void;
  /** 移除聊天 session */
  removeChatSession: (id: string) => void;
  /** 移除多任务 session */
  removeMultiTaskSession: (id: string) => void;
  /** 读取本地缓存的聊天内容 */
  getSessionChatItems: (id: string) => ChatItem[];
  /** 添加流到指定 session */
  addStreamEventsForSession: (
    sessionId: string,
    taskId: string,
    events: TaskEvent[],
    label?: string,
  ) => void;
  getWorkspaceId?: () => string | null | undefined;
}

export function useSessionOrchestrator({
  apiBaseUrl,
  initialSessionId,
  chatItems,
  clearChat,
  clearFiles,
  switchChatSession,
  switchMultiTaskSession,
  setActiveStreamSession,
  initChatSession,
  initMultiTaskSession,
  stopSession,
  setChatItems,
  completeHost,
  reloadWorkspaceFiles,
  updateWorkspaceFilesForSession,
  syncExecutionHistory,
  setIsRightSidebarOpen,
  setUserClosedSidebar,
  removeChatSession,
  removeMultiTaskSession,
  getSessionChatItems,
  addStreamEventsForSession,
  getWorkspaceId,
}: UseSessionOrchestratorProps) {
  const [sessionId, setSessionId] = useState<string>(
    () => initialSessionId || generateUUID(),
  );
  const [isPrewarming, setIsPrewarming] = useState(false);
  const initialSessionIdRef = useRef<string | null>(null);
  const pendingRestoreSessionIdRef = useRef<string | null>(
    initialSessionId || null,
  );
  const lastCleanupTimeRef = useRef<number>(0);

  // 清理过期草稿会话（节流：最多每5分钟执行一次）
  const cleanupDraftSessions = useCallback(async () => {
    const now = Date.now();
    if (now - lastCleanupTimeRef.current < 5 * 60 * 1000) {
      return;
    }
    lastCleanupTimeRef.current = now;

    try {
      await requestDraftCleanup(apiBaseUrl, sessionId);
    } catch (err) {
      console.warn("[Cleanup] 草稿清理失败:", err);
    }
  }, [apiBaseUrl, sessionId]);

  useEffect(() => {
    cleanupDraftSessions();
  }, [cleanupDraftSessions]);

  const handleSessionLoaded = useCallback(
    async (sid: string, items: ChatItem[]) => {
      if (pendingRestoreSessionIdRef.current !== sid) {
        // 历史恢复请求返回时，用户可能已经开始新任务或切到别的会话。
        // 这种迟到回包不能再把前台会话切回去。
        return;
      }

      const currentSessionId = sessionId;
      const cachedItems = getSessionChatItems(sid);
      const hasVisibleItemsForActiveSession =
        sid === currentSessionId && cachedItems.length > 0;

      if (hasVisibleItemsForActiveSession) {
        // 初始历史恢复可能在用户已经继续当前会话后才返回。
        // 这时若继续用旧快照覆盖 chatItems，会导致“流还在但消息消失”。
        pendingRestoreSessionIdRef.current = null;
        return;
      }

      const restoredItems =
        items.length > 0 ? items : cachedItems;

      try {
        await restoreSessionState(currentSessionId, sid, restoredItems, {
          setChatItems,
          initChatSession,
          initMultiTaskSession,
          switchChatSession,
          switchMultiTaskSession,
          setActiveStreamSession,
          setSessionId,
          completeHost,
          reloadWorkspaceFiles,
          updateWorkspaceFilesForSession,
          syncExecutionHistory,
          getWorkspaceId,
        });

        const hasSegments = restoredItems.some(
          (item) => item.type === "message" && item.segments && item.segments.length > 0,
        );
        if (hasSegments) {
          setIsRightSidebarOpen(true);
          setUserClosedSidebar(false);
        }
      } finally {
        if (pendingRestoreSessionIdRef.current === sid) {
          pendingRestoreSessionIdRef.current = null;
        }
      }
    },
    [
      sessionId,
      setChatItems,
      initChatSession,
      initMultiTaskSession,
      switchChatSession,
      switchMultiTaskSession,
      setActiveStreamSession,
      completeHost,
      reloadWorkspaceFiles,
      updateWorkspaceFilesForSession,
      syncExecutionHistory,
      getWorkspaceId,
      setIsRightSidebarOpen,
      setUserClosedSidebar,
      getSessionChatItems,
    ],
  );

  const {
    conversations,
    isLoadingHistory: isLoadingSessionList,
    isRestoringSession,
    loadConversations,
    handleSessionSelect: selectSession,
    handleDeleteSession: deleteSessionApi,
    addOptimisticSession,
    updateSessionTitle,
  } = useSessionManagement({
    apiBaseUrl,
    initialSessionId,
    onSessionSelect: handleSessionLoaded,
  });

  // 获取可用预热草稿（智能复用）
  const getAvailableDraft = useCallback(async (): Promise<string | null> => {
    try {
      return await requestAvailableDraftId(apiBaseUrl);
    } catch (err) {
      console.warn("[Session] 获取可用草稿失败:", err);
    }
    return null;
  }, [apiBaseUrl]);

  const prepareNewSession = useCallback(async () => {
    const hasConversation = chatItems.length > 0;

    // 一旦用户显式开始“新任务”流程，任何旧的历史恢复回包都不应再接管前台。
    pendingRestoreSessionIdRef.current = null;

    if (!hasConversation) {
      return sessionId;
    }

    cleanupDraftSessions();

    // 不再 resetAgentStream/resetMultiTask — 保留后台运行的流
    // 只初始化新 session 的 slot
    const availableDraftId = await getAvailableDraft();
    let newId: string;

    if (availableDraftId) {
      newId = availableDraftId;
    } else {
      newId = generateUUID();
    }

    // 初始化新 session
    initChatSession(newId);
    initMultiTaskSession(newId);

    return newId;
  }, [
    chatItems.length,
    sessionId,
    initChatSession,
    initMultiTaskSession,
    cleanupDraftSessions,
    getAvailableDraft,
  ]);

  const activatePreparedSession = useCallback(async (targetSessionId: string) => {
    pendingRestoreSessionIdRef.current = null;

    if (!targetSessionId || targetSessionId === sessionId) {
      return targetSessionId;
    }

    // 非破坏性切换到新 session
    const currentSessionId = sessionId;
    // 先同步所有子系统的 active session，避免中间状态不一致
    setActiveStreamSession(targetSessionId);
    switchChatSession(currentSessionId, targetSessionId);
    switchMultiTaskSession(currentSessionId, targetSessionId);

    clearChat();
    clearFiles();
    setSessionId(targetSessionId);
    updateWorkspaceFilesForSession(targetSessionId, []);
    addOptimisticSession(targetSessionId, "新对话");

    // 添加默认的 Host 任务到任务列表
    const hostTaskId = "host";
    const initEvent: TaskEvent = {
      event: "tool_start",
      agent_name: "Host",
      agent_role: "host",
      source_agent: "Host",
      tool_name: "Initialize",
      tool_params: {},
      timestamp: new Date().toISOString(),
    };
    addStreamEventsForSession(targetSessionId, hostTaskId, [initEvent], "当前会话");

    navigateToAnalysisSession(targetSessionId);
    return targetSessionId;
  }, [
    sessionId,
    clearChat,
    clearFiles,
    switchChatSession,
    switchMultiTaskSession,
    setActiveStreamSession,
    addOptimisticSession,
    updateWorkspaceFilesForSession,
    addStreamEventsForSession,
  ]);

  const handleNewSession = useCallback(async () => {
    const targetSessionId = await prepareNewSession();
    await activatePreparedSession(targetSessionId);
    return targetSessionId;
  }, [prepareNewSession, activatePreparedSession]);

  const activateReplacementDraft = useCallback(async () => {
    // 删除当前正在查看的会话时，总是先切到一个全新的空白草稿，
    // 避免把用户强行切回另一条历史会话，也避免在清理旧 session 前失去前台锚点。
    const replacementId = generateUUID();
    registerHiddenSession(replacementId);
    initChatSession(replacementId);
    initMultiTaskSession(replacementId);
    await activatePreparedSession(replacementId);
    return replacementId;
  }, [activatePreparedSession, initChatSession, initMultiTaskSession]);

  const handleSelectSession = useCallback(
    async (sid: string, options?: SessionSelectionOptions) => {
      if (sid === sessionId) return; // 同一 session 跳过

      cleanupDraftSessions();

      // 使用非破坏性切换
      initialSessionIdRef.current = sid;
      pendingRestoreSessionIdRef.current = sid;
      await selectSession(sid);
      if (!options?.silent) {
        navigateToAnalysisSession(sid);
      }
    },
    [sessionId, selectSession, cleanupDraftSessions],
  );

  /** 删除 session — 先停流再清理 */
  const handleDeleteSession = useCallback(
    async (sid: string, options?: SessionDeletionOptions) => {
      const isDeletingActiveSession = sid === sessionId;

      if (pendingRestoreSessionIdRef.current === sid) {
        pendingRestoreSessionIdRef.current = null;
      }

      // 先停止流
      stopSession(sid);

      if (isDeletingActiveSession && !options?.suppressActiveFallback) {
        await activateReplacementDraft();
      }

      // 清理前端 per-session 数据
      removeChatSession(sid);
      removeMultiTaskSession(sid);
      unregisterHiddenSession(sid);
      // 调后端删除 API
      await deleteSessionApi(sid);
    },
    [
      sessionId,
      stopSession,
      activateReplacementDraft,
      removeChatSession,
      removeMultiTaskSession,
      deleteSessionApi,
    ],
  );

  const hasLoadedHistoryRef = useRef(false);
  useSessionBootstrapEffects({
    initialSessionId,
    initialSessionIdRef,
    pendingRestoreSessionIdRef,
    hasLoadedHistoryRef,
    loadConversations,
    selectSession,
  });

  useSessionPrewarmEffect({
    sessionId,
    chatItemsLength: chatItems.length,
    pendingRestoreSessionIdRef,
    setIsPrewarming,
  });

  return {
    sessionId,
    isPrewarming,
    isLoadingSessionList,
    isRestoringSession,
    conversations,
    loadConversations,
    handleNewSession,
    prepareNewSession,
    activatePreparedSession,
    handleSelectSession,
    handleDeleteSession,
    updateSessionTitle,
  };
}
