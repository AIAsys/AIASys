import { useCallback, useEffect, useInsertionEffect, useRef } from "react";
import { API_BASE_URL, getCurrentUserId } from "@/config/api";
import { useAskUser } from "@/hooks/useAskUser";
import { useSessionMCPManager } from "@/hooks/useSessionMCPManager";
import { useSkills } from "@/hooks/useSkills";
import type { AskUserRequest, AskUserValue } from "@/types/askUser";
import { askUserBridge } from "@/lib/askUserBridge";
import { eventBus } from "@/lib/eventBus";
import { resolveCapabilityConfirmation } from "@/lib/api/capabilityConfirmation";
import { useCodeExecutor } from "./useCodeExecutor";
import type { SessionDeletionOptions } from "./useCodeExecutor/executorTypes";
import { useWorkspaceOverlayState } from "./useWorkspaceOverlayState";
import { useWorkspacePageEffects } from "./useWorkspacePageEffects";
import { useModelSelection } from "./useModelSelection";
import { useWorkspaceRuntimeControls } from "./useWorkspaceRuntimeControls";
import { useSessionLifecycleManager } from "./useSessionLifecycleManager";
import { useToolPreview } from "./useToolPreview";
import { useTaskWorkspaces } from "./useTaskWorkspaces";
import type { TaskWorkspaceSummary } from "../types";

interface UseWorkspacePageControllerOptions {
  userId: string;
  initialSessionId?: string | null;
}

function workspaceHasSession(
  workspace: TaskWorkspaceSummary | undefined,
  sessionId?: string | null,
): boolean {
  if (!workspace || !sessionId) {
    return false;
  }

  return (
    workspace.current_conversation?.session_id === sessionId ||
    Boolean(
      workspace.conversations?.some(
        (conversation) => conversation.session_id === sessionId,
      ),
    )
  );
}

export function useWorkspacePageController({
  userId,
  initialSessionId,
}: UseWorkspacePageControllerOptions) {
  const apiBaseUrl = API_BASE_URL || "";
  const overlayState = useWorkspaceOverlayState();

  const handleAskUserResponseRef = useRef<((requestId: string, approved: boolean, value?: AskUserValue, sessionId?: string) => void) | undefined>(undefined);

  const {
    showAskUser,
    resolveRequestById,
    setActiveSessionId: setAskUserActiveSessionId,
    removeSession: removeAskUserSession,
  } = useAskUser({
    onResponse: (requestId, approved, value, sessionId) => {
      handleAskUserResponseRef.current?.(requestId, approved, value, sessionId);
    },
  });

  // 设置全局桥接回调，供聊天流中的 AskUserInlineCard 使用
  useEffect(() => {
    askUserBridge.resolve = resolveRequestById;
    return () => {
      askUserBridge.resolve = null;
    };
  }, [resolveRequestById]);

  const {
    models,
    selectedModelId,
    effectiveModelDisplayName,
    sessionSelection,
    isLoadingSelection,
    isUpdatingSessionSelection,
    isUpdatingWorkspaceSelection,
    setActiveSessionId: setModelSelectionSessionId,
    setSelectedModelId,
    updateWorkspaceModelId,
    reloadModels,
    thinkingEnabled,
    thinkingEffort,
    setThinkingEnabled,
    setThinkingEffort,
    selectedModelSupportsThinking,
  } = useModelSelection();

  const handleAskUserRequestRef = useRef<((request: AskUserRequest, requestSessionId: string) => void) | undefined>(undefined);
  const currentWorkspaceIdRef = useRef<string | null | undefined>(undefined);

  const executor = useCodeExecutor({
    apiBaseUrl,
    initialSessionId,
    workspaceIdRef: currentWorkspaceIdRef,
    onAskUserRequest: (request, sessionId) => {
      handleAskUserRequestRef.current?.(request, sessionId);
    },
    selectedModelId,
    thinkingEnabled,
    thinkingEffort,
  });

  const { updateSessionChatItems } = executor;

  const handleAskUserRequest = useCallback(
    (request: AskUserRequest, requestSessionId: string) => {
      showAskUser(request, requestSessionId);
      // 将 AskUser 请求插入聊天流，以内联卡片形式展示
      updateSessionChatItems(requestSessionId, (prev) => {
        // 避免重复插入相同 request_id 的项
        if (prev.some((item) => item.type === "ask_user" && item.id === request.request_id)) {
          return prev;
        }
        return [
          ...prev,
          {
            type: "ask_user" as const,
            id: request.request_id,
            request,
            status: "pending" as const,
            timestamp: new Date(),
          },
        ];
      });
    },
    [showAskUser, updateSessionChatItems],
  );

  // 同步 ref 为最新回调（useInsertionEffect 在 DOM mutation 前同步执行，无竞态窗口）
  useInsertionEffect(() => {
    handleAskUserRequestRef.current = handleAskUserRequest;
  });


  const {
    setIsRightSidebarOpen,
    toasts,
    chatItems,
    sessionId,
    prepareNewSession,
    activatePreparedSession,
    refreshWorkspaceForSession,
    refreshExecutionHistoryCurrentSession,
    clearCurrentConversationView,
    handleDeleteSession,
    isRunning,
  } = executor;

  // 同步活跃 session ID 到 AskUser，确保只处理当前查看的 session
  useEffect(() => {
    setAskUserActiveSessionId(sessionId || '');
  }, [sessionId, setAskUserActiveSessionId]);

  // 同步响应处理 ref，在 AskUser 响应成功后更新聊天流中的卡片状态
  useEffect(() => {
    handleAskUserResponseRef.current = (requestId, approved, _value, responseSessionId) => {
      const targetSessionId = responseSessionId || sessionId || undefined;
      if (!targetSessionId) return;
      updateSessionChatItems(targetSessionId, (prev) =>
        prev.map((item) =>
          item.type === "ask_user" && item.id === requestId
            ? { ...item, status: approved ? "approved" : "rejected" }
            : item
        )
      );
    };
  }, [updateSessionChatItems, sessionId]);

  // Capability Confirmation 审批响应处理
  useEffect(() => {
    const handleApprove = async (data: unknown) => {
      const payload = data as {
        sessionId: string;
        toolCallId: string;
        scope: "once" | "session";
      };
      try {
        await resolveCapabilityConfirmation(
          userId,
          payload.sessionId,
          payload.toolCallId,
          { approved: true, scope: payload.scope }
        );
        updateSessionChatItems(payload.sessionId, (prev) =>
          prev.map((item) =>
            item.type === "capability_confirmation" && item.id === payload.toolCallId
              ? { ...item, status: "approved" as const }
              : item
          )
        );
      } catch (_e) {
        // 失败时保持 pending，用户可重试
      }
    };

    const handleReject = async (data: unknown) => {
      const payload = data as {
        sessionId: string;
        toolCallId: string;
        feedback: string;
      };
      try {
        await resolveCapabilityConfirmation(
          userId,
          payload.sessionId,
          payload.toolCallId,
          { approved: false, feedback: payload.feedback }
        );
        updateSessionChatItems(payload.sessionId, (prev) =>
          prev.map((item) =>
            item.type === "capability_confirmation" && item.id === payload.toolCallId
              ? { ...item, status: "rejected" as const }
              : item
          )
        );
      } catch (_e) {
        // 失败时保持 pending，用户可重试
      }
    };

    eventBus.on("capability:approve", handleApprove);
    eventBus.on("capability:reject", handleReject);
    return () => {
      eventBus.off("capability:approve", handleApprove);
      eventBus.off("capability:reject", handleReject);
    };
  }, [userId, updateSessionChatItems]);

  const {
    workspaces,
    isLoadingWorkspaces,
    currentWorkspaceId,
    currentWorkspace,
    loadWorkspaces,
  } = useTaskWorkspaces({
    currentSessionId: sessionId || undefined,
  });

  useEffect(() => {
    currentWorkspaceIdRef.current = currentWorkspaceId;
  }, [currentWorkspaceId]);

  const sessionBelongsToCurrentWorkspace = workspaceHasSession(
    currentWorkspace,
    sessionId,
  );
  const sessionExistsInConversationList = Boolean(
    sessionId &&
      executor.conversations.some(
        (conversation) => conversation.session_id === sessionId,
      ),
  );
  const materializedSessionId =
    sessionBelongsToCurrentWorkspace ||
    sessionExistsInConversationList ||
    executor.hasChatContent
      ? sessionId || undefined
      : undefined;
  const hasMaterializedSessionContext = Boolean(
    materializedSessionId,
  );
  const {
    workspaceServers: sessionMcpServers,
    refreshWorkspace: refreshSessionMcpServers,
  } = useSessionMCPManager({
    workspaceId: currentWorkspaceId || null,
    enabled: hasMaterializedSessionContext,
  });

  const sessionLifecycle = useSessionLifecycleManager({
    apiBaseUrl,
    userId,
    sessionId: materializedSessionId,
    statusQueryEnabled: hasMaterializedSessionContext,
    isRunning,
    refreshExecutionHistory: refreshExecutionHistoryCurrentSession,
    clearCurrentConversationView,
    refreshWorkspaceList: loadWorkspaces,
    refreshSessionMcpServers,
    removeAskUserSession,
    setAskUserActiveSessionId,
    showAskUser,
    onCompactionEvent: executor.handleCompactionEvent,
  });
  const runtimeControls = useWorkspaceRuntimeControls({
    userId,
    workspace: currentWorkspace ?? null,
    sessionId: sessionId || undefined,
    prepareNewSession,
    activatePreparedSession,
    refreshWorkspaceForSession,
    refreshSessionStatus: sessionLifecycle.refreshSessionStatus,
  });

  useEffect(() => {
    setModelSelectionSessionId(materializedSessionId);
  }, [materializedSessionId, setModelSelectionSessionId]);

  const {
    toolPreviewOpen,
    toolPreviewData,
    handleViewToolDetails,
    closeToolPreview,
  } = useToolPreview(chatItems);

  const {
    marketSkills,
    isLoading: isLoadingSkills,
    loadMarketSkills,
    enableSkill,
    disableSkill,
    importSkillArchive,
    getSkillEntryContent,
  } = useSkills();

  const handleDeleteSessionWithAskUserCleanup = useCallback(
    async (sid: string, options?: SessionDeletionOptions) => {
      removeAskUserSession(sid);
      await handleDeleteSession(sid, options);
    },
    [handleDeleteSession, removeAskUserSession],
  );

  useWorkspacePageEffects({
    apiBaseUrl,
    sessionId: sessionId || undefined,
    chatItemCount: chatItems.length,
    setIsRightSidebarOpen,
  });

  return {
    apiBaseUrl,
    userId: userId || getCurrentUserId(),
    executor,
    workspaces,
    isLoadingWorkspaces,
    currentWorkspaceId,
    currentWorkspace,
    loadWorkspaces,
    sessionLifecycle,
    runtimeControls,
    overlayState,
    userModels: models,
    selectedModelId,
    effectiveModelDisplayName,
    modelSelectionState: sessionSelection,
    isLoadingModelSelection: isLoadingSelection,
    isUpdatingSessionModelSelection: isUpdatingSessionSelection,
    isUpdatingWorkspaceModelSelection: isUpdatingWorkspaceSelection,
    setSelectedModelId,
    updateWorkspaceModelId,
    reloadModels,
    thinkingEnabled,
    thinkingEffort,
    setThinkingEnabled,
    setThinkingEffort,
    selectedModelSupportsThinking,
    hasMessagesForMcp:
      (sessionLifecycle.effectiveSessionStatus?.message_count ?? 0) > 0 ||
      chatItems.length > 0,
    hasMCPConfig: sessionMcpServers.length > 0,
    handleDeleteSession: handleDeleteSessionWithAskUserCleanup,
    toolPreview: {
      isOpen: toolPreviewOpen,
      data: toolPreviewData,
      handleViewToolDetails,
      close: closeToolPreview,
    },
    skillMarket: {
      workspaceId: currentWorkspaceId,
      skills: marketSkills,
      isLoading: isLoadingSkills,
      loadMarketSkills,
      enableSkill,
      disableSkill,
      importSkillArchive,
      getSkillEntryContent,
    },
    combinedToasts: [
      ...toasts,
      ...sessionLifecycle.toasts,
      ...runtimeControls.toasts,
    ],
  };
}
