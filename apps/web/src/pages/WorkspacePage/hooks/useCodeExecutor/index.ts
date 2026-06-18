import { useCallback, useEffect, useRef, useState } from "react";
import type { AskUserRequest } from "@/types/askUser";

import { useFileUploadToast } from "../../../../components/file/FileUploadToast";
import { useAgentFileUpload } from "../../../../hooks/useAgentFileUpload";
import { useExecutionHistory } from "../../../../hooks/useExecutionHistory";
import { useAgentStream } from "../../../../hooks/useAgentStream";
import { useMultiTaskEventStream } from "../../../../hooks/useMultiTaskEventStream";
import { useChatState } from "../useChatState";
import { useWorkspacePolling } from "./useWorkspacePolling";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import { rewriteSessionFromMessage } from "@/lib/api/sessions";
import { restoreChatItemsFromHistory } from "../sessionManagementHistory";
import type { SessionHistoryMessage } from "../../types";

import { useUIState } from "./useUIState";
import { useSessionOrchestrator } from "./useSessionOrchestrator";
import { useExecutionSubmit } from "./useExecutionSubmit";
import { useCodeExecutorActiveSessionSync } from "./useCodeExecutorActiveSessionSync";
import { useCodeExecutorViewState } from "./useCodeExecutorViewState";
import { getOrCreateSlot, cleanupSlot } from "./sessionRegistry";
import type { SessionSlot } from "./sessionRegistry";
import { unregisterHiddenSession } from "../hiddenSessionRegistry";
import { mapToWorkspaceFiles } from "./workspaceFiles";
import type {
  UseCodeExecutorProps,
  UseCodeExecutorReturn,
  WorkspaceRefreshOptions,
} from "./executorTypes";

export * from "./executorTypes";

export function useCodeExecutor({
  apiBaseUrl,
  initialSessionId,
  workspaceId,
  workspaceIdRef,
  onAskUserRequest,
  selectedModelId,
  thinkingEnabled,
  thinkingEffort,
}: UseCodeExecutorProps): UseCodeExecutorReturn {
  const clearContextMarkerContent =
    "当前会话已清理，后续回复不会继承以上上下文。";

  // 1. UI State
  const uiState = useUIState();

  // 2. Per-Session Slot Registry
  const sessionSlotsRef = useRef<Map<string, SessionSlot>>(new Map());

  const getSessionSlot = useCallback((sessionId: string): SessionSlot => {
    return getOrCreateSlot(sessionSlotsRef.current, sessionId);
  }, []);

  // 3. Shared Hooks
  const { toasts, showSuccess, showError } = useFileUploadToast();
  const {
    chatItems,
    setChatItems,
    inputValue,
    setInputValue,
    addUserMessage,
    addAiMessage,
    clearChat,
    switchSession: switchChatSession,
    updateSessionChatItems,
    initSession: initChatSession,
    removeSession: removeChatSession,
    setActiveSessionId: setChatActiveSessionId,
    getSessionChatItems,
    activeSessionIdRef: chatActiveSessionIdRef,
  } = useChatState();
  const {
    state: agentState,
    run: runAgentStream,
    stop: _stopAgentStream,
    stopSession: stopStreamSession,
    reset: resetAgentStream,
    setActiveSession: setActiveStreamSession,
    isSessionRunning,
    runningSessionIds,
    removeSession: removeAgentStreamSession,
  } = useAgentStream();
  const {
    taskList,
    selectedTaskId,
    hasAnyRunning,
    selectTask,
    addStreamEvents: addStreamEventsDirect,
    addStreamEventsForSession,
    completeHost,
    completeAllTasks,
    reset: _resetMultiTask,
    resetSessionTaskState,
    workspaceFiles,
    updateWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncNotebookHistory: syncExecutionHistory,
    switchSession: switchMultiTaskSession,
    initSession: initMultiTaskSession,
    removeSession: removeMultiTaskSession,
    setActiveSessionId: setMultiTaskActiveSessionId,
  } = useMultiTaskEventStream();
  const {
    events: _executionEvents,
    isLoading: _isLoadingExecutionHistory,
    reset: _resetExecutionHistory,
  } = useExecutionHistory();
  const getCurrentWorkspaceId = useCallback(
    () => workspaceIdRef?.current ?? workspaceId ?? null,
    [workspaceId, workspaceIdRef],
  );

  // 4. File Upload Logic
  const {
    state: uploadState,
    uploadFile,
    deleteFile: _deleteFile,
    listFiles: _listFiles,
    reloadWorkspaceFiles,
    removeFile,
    deleteWorkspaceFile,
    moveFile,
    readWorkspaceFileContent,
    clearFiles,
    switchSession: switchUploadSession,
    setActiveSessionId: setUploadActiveSessionId,
    removeSession: removeUploadSession,
    retryUpload,
    removeFailedUpload,
  } = useAgentFileUpload({ onUploadError: showError });
  const uploadedFiles = uploadState.files;
  const isUploading = uploadState.isUploading;
  const uploadProgress = uploadState.uploadProgress;
  const failedUploads = uploadState.failedUploads;

  // Session-aware AskUser handler
  const handleAskUserRequest = useCallback(
    (request: AskUserRequest, sessionId: string) => {
      // Forward to the original handler (per-session queue managed in useAskUser hook)
      if (onAskUserRequest) {
        onAskUserRequest(request, sessionId);
      }
    },
    [onAskUserRequest],
  );

  // 5. Session Orchestrator
  const sessionOrchestrator = useSessionOrchestrator({
    apiBaseUrl,
    initialSessionId,
    chatItems,
    clearChat,
    clearFiles,
    switchChatSession: (fromId: string, toId: string) => {
      switchChatSession(fromId, toId);
      switchUploadSession(fromId, toId);
    },
    switchMultiTaskSession,
    setActiveStreamSession: (toId: string) => {
      setActiveStreamSession(toId);
      setChatActiveSessionId(toId);
      setMultiTaskActiveSessionId(toId);
      setUploadActiveSessionId(toId);
    },
    initChatSession,
    initMultiTaskSession,
    stopSession: stopStreamSession,
    setChatItems,
    completeHost,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncExecutionHistory,
    getWorkspaceId: getCurrentWorkspaceId,
    setIsRightSidebarOpen: uiState.setIsRightSidebarOpen,
    setUserClosedSidebar: uiState.setUserClosedSidebar,
    removeChatSession: (id: string) => {
      removeChatSession(id);
      removeUploadSession(id);
    },
    removeMultiTaskSession,
    getSessionChatItems,
    addStreamEventsForSession,
  });

  const {
    activeSessionIdRef,
    updateChatItemsForSession,
    addStreamEventsForSessionWrapped,
  } = useCodeExecutorActiveSessionSync({
    sessionId: sessionOrchestrator.sessionId,
    setActiveStreamSession,
    setChatActiveSessionId,
    setMultiTaskActiveSessionId,
    setUploadActiveSessionId,
    setChatItems,
    updateSessionChatItems,
    addStreamEventsDirect,
    addStreamEventsForSession,
    chatActiveSessionIdRef,
  });

  const isCurrentSessionRunning = sessionOrchestrator.sessionId
    ? isSessionRunning(sessionOrchestrator.sessionId)
    : false;
  const [tokenUsageRevision, setTokenUsageRevision] = useState(0);
  const refreshTokenUsage = useCallback(() => {
    setTokenUsageRevision((value) => value + 1);
  }, []);

  const [compactionState, setCompactionState] = useState<{
    phase: "begin" | "done";
    tokens_before?: number;
    tokens_after?: number;
    saved_tokens?: number;
    summary_tokens?: number;
    clearTimer?: ReturnType<typeof setTimeout>;
  } | null>(null);

  const handleCompactionEvent = useCallback(
    (payload: {
      phase: "begin" | "done";
      tokens_before?: number;
      tokens_after?: number;
      saved_tokens?: number;
      summary_tokens?: number;
    }) => {
      if (payload.phase === "begin") {
        setCompactionState((prev) => {
          if (prev?.clearTimer) clearTimeout(prev.clearTimer);
          return { ...payload, phase: "begin" };
        });
        return;
      }
      // done: 刷新 token 占用数据，并短暂展示结果
      refreshTokenUsage();
      setCompactionState((prev) => {
        if (prev?.clearTimer) clearTimeout(prev.clearTimer);
        const clearTimer = setTimeout(() => {
          setCompactionState(null);
        }, 3000);
        return { ...payload, phase: "done", clearTimer };
      });
    },
    [refreshTokenUsage],
  );

  const shouldAutoSyncVisibleSessionArtifacts = Boolean(
    initialSessionId ||
      chatItems.length > 0 ||
      isCurrentSessionRunning ||
      sessionOrchestrator.isRestoringSession ||
      sessionOrchestrator.conversations.some(
        (conversation) => conversation.session_id === sessionOrchestrator.sessionId,
      ),
  );

  // 6. Execution Submit
  const executionSubmit = useExecutionSubmit({
    inputValue,
    setInputValue,
    selectedModelId,
    isSessionRunning,
    agentState,
    runAgentStream,
    thinkingEnabled,
    thinkingEffort,
    currentWorkspaceId: workspaceId,
    currentWorkspaceIdRef: workspaceIdRef,
    stopSession: stopStreamSession,
    uploadedFiles,
    addUserMessage,
    addAiMessage,
    updateChatItems: updateChatItemsForSession,
    sessionId: sessionOrchestrator.sessionId,
    getSessionSlot,
    addStreamEventsForSession: addStreamEventsForSessionWrapped,
    resetSessionTaskState,
    completeHost,
    completeAllTasks,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncExecutionHistory,
    updateSessionTitle: sessionOrchestrator.updateSessionTitle,
    loadConversations: sessionOrchestrator.loadConversations,
    showError,
    showSuccess,
    clearFiles,
    onAskUserRequest: handleAskUserRequest,
    onCompactionEvent: handleCompactionEvent,
    apiBaseUrl,
    activeSessionIdRef,
    onTokenUsageShouldRefresh: refreshTokenUsage,
  });

  const resolveHistoryUserMessageId = useCallback(
    async (
      currentSessionId: string,
      userId: string,
      requestedMessageId: string,
      lookupContent: string,
    ): Promise<string> => {
      if (!requestedMessageId.startsWith("user-")) {
        return requestedMessageId;
      }

      const historyEndpoint = API_ENDPOINTS.SESSION_HISTORY(
        userId,
        currentSessionId,
      );
      const historyPayload = await apiRequest<{
        current_messages?: SessionHistoryMessage[];
      }>(`${apiBaseUrl}${historyEndpoint}`);
      const matchingUserMessage = [
        ...(historyPayload.current_messages || []),
      ].reverse().find((message) => {
        if (message.role !== "user" || !message.id) {
          return false;
        }
        const renderedContent = message.display_content ?? message.content;
        const text =
          typeof renderedContent === "string"
            ? renderedContent
            : Array.isArray(renderedContent)
              ? renderedContent
                  .map((item) => item.text || item.think || "")
                  .join("")
              : "";
        return text.trim() === lookupContent;
      });

      return matchingUserMessage?.id || requestedMessageId;
    },
    [apiBaseUrl],
  );

  const {
    workerTaskList,
    currentSelectedTask,
    currentSelectedTaskId,
    handleViewExecutionSpace,
    handleWorkerClick,
  } = useCodeExecutorViewState({
    taskList,
    selectedTaskId,
    selectTask,
    setIsRightSidebarOpen: uiState.setIsRightSidebarOpen,
    setUserClosedSidebar: uiState.setUserClosedSidebar,
  });

  const handleUploadFiles = useCallback(
    async (inputFiles: File[] | FileList) => {
      const fileArray = Array.from(inputFiles);
      if (fileArray.length === 0) {
        return;
      }

      let hasSuccess = false;
      const currentWorkspaceId = getCurrentWorkspaceId();
      for (const file of fileArray) {
        try {
          const result = await uploadFile(
            file,
            sessionOrchestrator.sessionId,
            currentWorkspaceId,
          );
          if (result) {
            showSuccess(`文件 ${file.name} 上传成功`);
            hasSuccess = true;
          } else {
            showError(`文件 ${file.name} 上传失败`);
          }
        } catch {
          showError(`文件 ${file.name} 上传异常`);
        }
      }
      if (hasSuccess && sessionOrchestrator.sessionId && currentWorkspaceId) {
        const files = await reloadWorkspaceFiles(currentWorkspaceId, {
          force: true,
        });
        updateWorkspaceFilesForSession(
          sessionOrchestrator.sessionId,
          mapToWorkspaceFiles(files),
        );
      }
    },
    [
      uploadFile,
      showSuccess,
      showError,
      reloadWorkspaceFiles,
      updateWorkspaceFilesForSession,
      sessionOrchestrator.sessionId,
      getCurrentWorkspaceId,
    ],
  );

  const handleFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = e.target.files;
      if (!files) {
        return;
      }
      await handleUploadFiles(files);
    },
    [handleUploadFiles],
  );

  const handleAddFileClick = useCallback(() => {
    uiState.fileInputRef.current?.click();
  }, [uiState.fileInputRef]);

  // 只轮询活跃 session
  useWorkspacePolling({
    isRunning: isCurrentSessionRunning,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    workspaceFiles,
    sessionId: sessionOrchestrator.sessionId,
    workspaceId: getCurrentWorkspaceId(),
  });

  const handleReadWorkspaceFileContent = useCallback(
    (filename: string) => {
      return readWorkspaceFileContent(filename, getCurrentWorkspaceId());
    },
    [readWorkspaceFileContent, getCurrentWorkspaceId],
  );

  const workspaceFilesRef = useRef(workspaceFiles);
  useEffect(() => {
    workspaceFilesRef.current = workspaceFiles;
  }, [workspaceFiles]);

  const handleDeleteWorkspaceFile = useCallback(
    async (filename: string) => {
      const result = await deleteWorkspaceFile(
        filename,
        sessionOrchestrator.sessionId,
        getCurrentWorkspaceId(),
      );
      if (result) {
        updateWorkspaceFiles(
          workspaceFilesRef.current.filter((f) => f.name !== filename),
        );
      }
      return result;
    },
    [
      deleteWorkspaceFile,
      sessionOrchestrator.sessionId,
      getCurrentWorkspaceId,
      updateWorkspaceFiles,
    ],
  );

  const handleDeleteWorkspaceFolder = useCallback(
    async (folderPath: string) => {
      const result = await deleteWorkspaceFile(
        folderPath,
        sessionOrchestrator.sessionId,
        getCurrentWorkspaceId(),
        true,
      );
      if (result) {
        updateWorkspaceFiles(
          workspaceFilesRef.current.filter(
            (f) => !f.name.startsWith(`${folderPath}/`),
          ),
        );
      }
      return result;
    },
    [
      deleteWorkspaceFile,
      sessionOrchestrator.sessionId,
      getCurrentWorkspaceId,
      updateWorkspaceFiles,
    ],
  );

  const handleMoveFile = useCallback(
    async (source: string, target: string) => {
      if (!sessionOrchestrator.sessionId) return false;
      const result = await moveFile(
        source,
        target,
        sessionOrchestrator.sessionId,
        getCurrentWorkspaceId(),
      );
      return result;
    },
    [moveFile, sessionOrchestrator.sessionId, getCurrentWorkspaceId],
  );

  const refreshWorkspaceForSession = useCallback(
    async (
      targetSessionId: string,
      options?: WorkspaceRefreshOptions,
    ) => {
      if (!targetSessionId) {
        return;
      }

      const currentWorkspaceId = getCurrentWorkspaceId();
      if (!currentWorkspaceId) {
        return;
      }

      const files = await reloadWorkspaceFiles(currentWorkspaceId, options);
      updateWorkspaceFilesForSession(
        targetSessionId,
        mapToWorkspaceFiles(files),
      );
    },
    [reloadWorkspaceFiles, updateWorkspaceFilesForSession, getCurrentWorkspaceId],
  );

  const refreshExecutionHistoryCurrentSession = useCallback(async () => {
    const currentSessionId = sessionOrchestrator.sessionId;
    if (!currentSessionId) {
      return;
    }
    await syncExecutionHistory("host", currentSessionId);
  }, [sessionOrchestrator.sessionId, syncExecutionHistory]);

  const clearCurrentConversationView = useCallback(async () => {
    const currentSessionId = sessionOrchestrator.sessionId;
    if (!currentSessionId) {
      return;
    }

    resetAgentStream();
    updateChatItemsForSession(currentSessionId, (prev) => {
      const lastItem = prev[prev.length - 1];
      if (
        lastItem?.type === "message" &&
        lastItem.role === "system" &&
        lastItem.content === clearContextMarkerContent
      ) {
        return prev;
      }
      return [
        ...prev,
        {
          type: "message",
          id: `system-clear-${Date.now()}`,
          sender: "system",
          role: "system",
          content: clearContextMarkerContent,
          timestamp: new Date(),
          isStreaming: false,
        },
      ];
    });
    await sessionOrchestrator.loadConversations();
  }, [
    clearContextMarkerContent,
    sessionOrchestrator,
    resetAgentStream,
    updateChatItemsForSession,
  ]);

  const rewriteUserMessage = useCallback(
    async (messageId: string, content: string, originalContent?: string) => {
      const currentSessionId = sessionOrchestrator.sessionId;
      const normalizedContent = content.trim();
      const lookupContent = (originalContent || content).trim();
      if (!currentSessionId || !messageId || !normalizedContent) {
        return;
      }
      if (isSessionRunning(currentSessionId)) {
        showError("当前对话正在执行，结束后再编辑重发。");
        return;
      }

      try {
        resetAgentStream();
        const userId = getCurrentUserId();
        const historyMessageId = await resolveHistoryUserMessageId(
          currentSessionId,
          userId,
          messageId,
          lookupContent,
        );
        const rewriteResult = await rewriteSessionFromMessage(apiBaseUrl, {
          userId,
          sessionId: currentSessionId,
          messageId: historyMessageId,
          content: normalizedContent,
          confirmDropTail: true,
        });
        const rewrittenMessages =
          rewriteResult.current_messages || rewriteResult.messages || [];
        const nextItems = restoreChatItemsFromHistory(
          currentSessionId,
          rewrittenMessages,
        );
        updateChatItemsForSession(currentSessionId, () => nextItems);

        const historyEndpoint = API_ENDPOINTS.SESSION_HISTORY(
          userId,
          currentSessionId,
        );
        const historyPayload = await apiRequest<{
          current_messages?: SessionHistoryMessage[];
        }>(`${apiBaseUrl}${historyEndpoint}`);
        const lastUserMessage = [
          ...(historyPayload.current_messages || rewrittenMessages),
        ].reverse().find((message) => message.role === "user");
        const attachmentPaths = Array.isArray(lastUserMessage?.content)
          ? lastUserMessage.content
              .map((item) => item.source_path)
              .filter((value): value is string => Boolean(value))
          : [];

        await executionSubmit.handleSubmit(normalizedContent, {
          skipUserEcho: true,
          attachmentPaths,
        });
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "编辑重发失败";
        showError(message);
      }
    },
    [
      apiBaseUrl,
      executionSubmit,
      isSessionRunning,
      resetAgentStream,
      resolveHistoryUserMessageId,
      sessionOrchestrator.sessionId,
      showError,
      updateChatItemsForSession,
    ],
  );

  // 当前前台 session 一旦可见，就主动同步一次工作区文件。
  // 这样新建任务后的项目画像和工作区资源不需要等首次执行或轮询才出现。
  useEffect(() => {
    const currentSessionId = sessionOrchestrator.sessionId;
    if (!currentSessionId || !shouldAutoSyncVisibleSessionArtifacts) {
      return;
    }

    void refreshWorkspaceForSession(currentSessionId);
  }, [
    refreshWorkspaceForSession,
    sessionOrchestrator.sessionId,
    shouldAutoSyncVisibleSessionArtifacts,
  ]);

  const handleRemoveFile = useCallback(
    async (filePath?: string) => {
      if (!filePath) return;
      const currentSessionId = sessionOrchestrator.sessionId;
      const currentWorkspaceId = workspaceId ?? workspaceIdRef?.current;
      await removeFile(filePath, currentSessionId, currentWorkspaceId);
    },
    [removeFile, sessionOrchestrator.sessionId, workspaceId, workspaceIdRef],
  );

  return {
    ...uiState,
    toasts,
    chatItems,
    inputValue,
    setInputValue,
    agentState,
    runAgentStream,
    resetAgentStream,
    taskList,
    currentTaskList: workerTaskList,
    selectedTask: currentSelectedTask,
    selectedTaskId: currentSelectedTaskId,
    selectTask,
    sessionId: sessionOrchestrator.sessionId,
    handleNewSession: sessionOrchestrator.handleNewSession,
    prepareNewSession: sessionOrchestrator.prepareNewSession,
    activatePreparedSession: sessionOrchestrator.activatePreparedSession,
    refreshWorkspaceForSession,
    refreshExecutionHistoryCurrentSession,
    clearCurrentConversationView,
    handleSelectSession: sessionOrchestrator.handleSelectSession,
    handleDeleteSession: sessionOrchestrator.handleDeleteSession,
    removeSessionFrontendState: (id: string) => {
      const slot = sessionSlotsRef.current.get(id);
      if (slot) {
        cleanupSlot(slot);
        sessionSlotsRef.current.delete(id);
      }
      removeChatSession(id);
      removeMultiTaskSession(id);
      removeUploadSession(id);
      removeAgentStreamSession(id);
      unregisterHiddenSession(id);
    },
    uploadedFiles,
    failedUploads,
    removeFile: handleRemoveFile,
    handleUploadFiles,
    handleFileChange,
    handleAddFileClick,
    retryUpload,
    removeFailedUpload,
    conversations: sessionOrchestrator.conversations,
    updateSessionTitle: sessionOrchestrator.updateSessionTitle,
    handleViewExecutionSpace,
    ...executionSubmit,
    handleWorkerClick,
    // handleSubAgentClick,
    isRunning: isCurrentSessionRunning,
    tokenUsageRevision,
    compactionState,
    handleCompactionEvent,
    rewriteUserMessage,
    hasChatContent: chatItems.length > 0 || isCurrentSessionRunning,
    currentHasAnyRunning:
      hasAnyRunning || agentState.isRunning || runningSessionIds.size > 0,
    executionSummary: null,
    isLoadingHistory: sessionOrchestrator.isLoadingSessionList,
    isRestoringSession: sessionOrchestrator.isRestoringSession,
    workspaceFiles,
    updateWorkspaceFiles,
    deleteWorkspaceFile: handleDeleteWorkspaceFile,
    deleteWorkspaceFolder: handleDeleteWorkspaceFolder,
    moveFile: handleMoveFile,
    readWorkspaceFileContent: handleReadWorkspaceFileContent,
    isUploading,
    uploadProgress,
    isPrewarming: sessionOrchestrator.isPrewarming,
    runningSessionIds,
    updateSessionChatItems,
    loadMoreHistory: sessionOrchestrator.loadMoreHistory,
    hasMoreHistory: sessionOrchestrator.hasMoreHistory,
    updateChatItemsForSession,
  };
}
