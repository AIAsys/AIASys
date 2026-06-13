import { useCallback, useRef } from "react";
import type { ChatItem, ChatSegment } from "../../types";
import { useStreamEventHandler } from "./useStreamEventHandler";
import { refreshWorkspaceFiles } from "./workspaceFiles";
import { apiRequest } from "@/lib/api/httpClient";
import type { AskUserRequest } from "@/types/askUser";
import type { TaskEvent, WorkspaceFile } from "@/types/task";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { StreamCallbacks } from "@/hooks/useAgentStream";
import type { SessionSlot } from "./sessionRegistry";
import { eventBus, EVENTS } from "@/lib/eventBus";

function getRouteWorkspaceId(): string | null {
  if (typeof window === "undefined") {
    return null;
  }
  if (window.location.pathname.replace(/\/+$/, "") !== "/workspace") {
    return null;
  }
  return new URLSearchParams(window.location.search).get("workspace_id");
}

interface UseExecutionSubmitProps {
  inputValue: string;
  setInputValue: (value: string) => void;
  /** 选中的模型ID，'system' 表示使用系统默认配置 */
  selectedModelId?: string;
  /** 查询指定 session 是否正在运行 */
  isSessionRunning: (sessionId: string) => boolean;
  agentState: { isRunning: boolean };
  runAgentStream: (
    input: string,
    sessionId: string,
    callbacks?: StreamCallbacks,
    modelId?: string,
    attachments?: string[],
    workspaceId?: string | null,
  ) => Promise<void>;
  currentWorkspaceId?: string | null;
  currentWorkspaceIdRef?: { readonly current: string | null | undefined };
  /** 停止指定 session 的流 */
  stopSession: (sessionId: string) => void;
  uploadedFiles: UploadedFile[];
  addUserMessage: (content: string, files: string[]) => void;
  addAiMessage: (id: string) => void;
  /** 更新指定 session 的 chatItems */
  updateChatItems: (
    sessionId: string,
    updater: (prev: ChatItem[]) => ChatItem[],
  ) => void;
  sessionId: string;
  /** 获取指定 session 的 slot */
  getSessionSlot: (sessionId: string) => SessionSlot;
  addStreamEventsForSession: (
    sessionId: string,
    taskId: string,
    events: TaskEvent[],
    sourceAgent: string,
  ) => void;
  completeHost: () => void;
  completeAllTasks: () => void;
  reloadWorkspaceFiles: (
    workspaceId?: string,
    options?: { force?: boolean },
  ) => Promise<UploadedFile[]>;
  updateWorkspaceFilesForSession: (
    sessionId: string,
    files: WorkspaceFile[],
  ) => void;
  syncExecutionHistory: (taskId: string, sessionId: string) => Promise<void>;
  updateSessionTitle: (id: string, title: string) => void;
  loadConversations: () => Promise<void>;
  showError: (err: string) => void;
  showSuccess: (msg: string) => void;
  clearFiles: () => void;
  onAskUserRequest?: (request: AskUserRequest, sessionId: string) => void;
  onSubAgentEvent?: (event: unknown) => void;
  onCompactionEvent?: (payload: {
    phase: "begin" | "done";
    tokens_before?: number;
    tokens_after?: number;
    saved_tokens?: number;
    summary_tokens?: number;
  }) => void;
  apiBaseUrl: string;
  /** 权威 activeSessionId ref — 用于判断 onFinish/onError 是否来自活跃 session */
  activeSessionIdRef: { readonly current: string };
  /** 流终态或停止后刷新右栏 token / 上下文占用 */
  onTokenUsageShouldRefresh?: () => void;
  thinkingEnabled?: boolean;
  thinkingEffort?: string;
}

interface SubmitOptions {
  skipUserEcho?: boolean;
  attachmentPaths?: string[];
}

export function useExecutionSubmit(props: UseExecutionSubmitProps) {
  const {
    inputValue,
    setInputValue,
    selectedModelId,
    isSessionRunning,
    runAgentStream,
    currentWorkspaceId,
    currentWorkspaceIdRef,
    stopSession,
    uploadedFiles,
    addUserMessage,
    addAiMessage,
    updateChatItems,
    sessionId,
    getSessionSlot,
    addStreamEventsForSession,
    completeHost,
    completeAllTasks,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncExecutionHistory,
    updateSessionTitle,
    loadConversations,
    showError,
    showSuccess,
    clearFiles,
    onAskUserRequest,
    onSubAgentEvent,
    onCompactionEvent,
    apiBaseUrl,
    activeSessionIdRef,
    onTokenUsageShouldRefresh,
  } = props;

  const isSubmittingRef = useRef(false);

  const { handleStreamEvent } = useStreamEventHandler({
    getSessionSlot,
    updateChatItems,
    addStreamEventsForSession,
    isSessionRunning,
    onAskUserRequest,
    onSubAgentEvent,
    onCompactionEvent,
    onTokenUsageShouldRefresh,
  });

  const handleSubmit = useCallback(async (
    overridePrompt?: string,
    options: SubmitOptions = {},
  ) => {
    // 只检查当前 session 是否运行，不再全局阻止
    const effectiveInput = (overridePrompt ?? inputValue).trim();
    // 使用最新的 sessionId，避免闭包中 sessionId 过时
    const latestSessionId = activeSessionIdRef.current || sessionId;
    if (!effectiveInput || isSessionRunning(latestSessionId) || isSubmittingRef.current) return;
    isSubmittingRef.current = true;

    const userContent = effectiveInput;
    const attachmentPaths =
      options.attachmentPaths ??
      uploadedFiles.map((file) => file.file_path || file.filename);
    if (!overridePrompt) {
      setInputValue("");
      clearFiles();
    }

    if (!options.skipUserEcho) {
      addUserMessage(userContent, attachmentPaths);
    }

    // 立即更新 session title，避免长时间显示"新任务"
    const titleFromContent =
      userContent.slice(0, 30) + (userContent.length > 30 ? "..." : "");
    updateSessionTitle(latestSessionId, titleFromContent);

    // 清理当前 session 中已被终止的 AI 消息的 isStopped 标志，
    // 避免新任务启动后旧消息仍显示"任务已终止"
    updateChatItems(latestSessionId, (prev: ChatItem[]) => {
      return prev.map((item) => {
        if (item.type === "message" && item.sender === "ai" && item.isStopped) {
          return { ...item, isStopped: false };
        }
        return item;
      });
    });

    // 清理当前 session 的 slot 数据
    // 必须使用 latestSessionId，不能用闭包中的 sessionId（可能已过时）
    const slot = getSessionSlot(latestSessionId);
    slot.taskEventsMap = {};
    slot.outputAccumulators.clear();
    slot.streamingSegments = [];
    if (slot.flushTimer) {
      clearTimeout(slot.flushTimer);
      slot.flushTimer = null;
    }

    const aiMsgId = `ai-${Date.now()}`;
    // 记录 streamingMessageId 用于精确匹配
    slot.streamingMessageId = aiMsgId;
    addAiMessage(aiMsgId);

    // 只在选择了非 system 的模型时才传递 model_id
    const effectiveModelId =
      selectedModelId && selectedModelId !== "system"
        ? selectedModelId
        : undefined;
    const executionWorkspaceId =
      currentWorkspaceIdRef?.current ?? currentWorkspaceId ?? getRouteWorkspaceId();

    // 捕获 sessionId 避免闭包中 sessionId 变化
    const currentSessionId = latestSessionId;

    // 通知执行树：流即将开始，触发首次刷新以感知 host running 并启动 polling
    eventBus.emit(EVENTS.EXECUTION_ACTIVITY, {
      session_id: currentSessionId,
      type: "stream_start",
    });

    await runAgentStream(
      userContent,
      currentSessionId,
      {
        onEvent: (event) => handleStreamEvent(currentSessionId, event),
        onFinish: async () => {
          const finishSlot = getSessionSlot(currentSessionId);
          let msgId: string | null = null;

          try {
            if (finishSlot.flushTimer) {
              clearTimeout(finishSlot.flushTimer);
              finishSlot.flushTimer = null;
            }

            finishSlot.streamingSegments = finishSlot.streamingSegments.map(
              (seg) =>
                seg.type === "think" ? { ...seg, isComplete: true } : seg,
            );

            const finalSegments = [...finishSlot.streamingSegments];
            msgId = finishSlot.streamingMessageId;

            updateChatItems(currentSessionId, (prev: ChatItem[]) => {
              const aiMsgIdx = msgId
                ? prev.findIndex((item) => item.id === msgId)
                : prev.findIndex(
                    (item) => item.type === "message" && item.sender === "ai" && item.isStreaming,
                  );
              if (aiMsgIdx === -1) return prev;
              const newItems = [...prev];
              const target = newItems[aiMsgIdx];
              if (target.type === "message") {
                newItems[aiMsgIdx] = { ...target, segments: finalSegments, isStreaming: false };
              }
              return newItems;
            });

            // 通知执行树做最终刷新
            eventBus.emit(EVENTS.EXECUTION_ACTIVITY, {
              session_id: currentSessionId,
              type: "stream_end",
            });

            // 只对当前活跃 session 执行 React setState 操作
            // 后台 session 的任务状态由 addStreamEventsForSession 中的 hasEndEvent 管理
            const isActive = currentSessionId === activeSessionIdRef.current;
            if (isActive) {
              completeAllTasks();
            }

            // 只对活跃 session 刷新工作区文件到 React state
            // 后台 session 的文件在切回时通过 switchSession 加载
            if (isActive) {
              await refreshWorkspaceFiles(
                reloadWorkspaceFiles,
                updateWorkspaceFilesForSession,
                currentSessionId,
                executionWorkspaceId,
                undefined,
                { force: true },
              );
            }
            await syncExecutionHistory("host", currentSessionId);
            onTokenUsageShouldRefresh?.();

            const titleFromContent =
              userContent.slice(0, 30) + (userContent.length > 30 ? "..." : "");
            updateSessionTitle(currentSessionId, titleFromContent);
            await loadConversations();

            // 后台 session 完成时显示 toast
            // 用 activeSessionIdRef（始终最新）判断，而非闭包中的 sessionId
            if (!isActive) {
              showSuccess(`监控任务 "${titleFromContent}" 已完成`);
            }
          } catch (finishErr) {
            console.error("[useExecutionSubmit onFinish] 流结束处理失败:", finishErr);
          } finally {
            // 无论成功失败，slot 必须清理，避免泄漏
            finishSlot.streamingSegments = [];
            finishSlot.streamingMessageId = null;
            completeHost();
          }
        },
        onError: (err: string) => {
          showError(err);

          const errorSlot = getSessionSlot(currentSessionId);
          if (errorSlot.flushTimer) {
            clearTimeout(errorSlot.flushTimer);
            errorSlot.flushTimer = null;
          }

          // 先关闭未完成的 think，再读取 msgId
          errorSlot.streamingSegments = errorSlot.streamingSegments.map(
            (seg) => seg.type === "think" ? { ...seg, isComplete: true } : seg,
          );

          // 先读取 msgId，再清空（修复读取顺序 bug）
          const msgId = errorSlot.streamingMessageId;

          errorSlot.streamingSegments = [];
          errorSlot.streamingMessageId = null;
          completeHost();

          // 通知执行树：流已结束（错误）
          eventBus.emit(EVENTS.EXECUTION_ACTIVITY, {
            session_id: currentSessionId,
            type: "stream_end",
          });

          // 只对活跃 session 调 completeAllTasks（避免错误标记其他 session 的任务）
          if (currentSessionId === activeSessionIdRef.current) {
            completeAllTasks();
          }
          onTokenUsageShouldRefresh?.();

          updateChatItems(currentSessionId, (prev: ChatItem[]) => {
            const aiMsgIdx = msgId
              ? prev.findIndex((item) => item.id === msgId)
              : prev.findIndex(
                  (item) => item.type === "message" && item.sender === "ai" && item.isStreaming,
                );
            if (aiMsgIdx === -1) return prev;
            const newItems = [...prev];
            const target = newItems[aiMsgIdx];
            const existingContent = target.type === "message" && typeof target.content === "string"
              ? target.content
              : "";
            const existingSegments = target.type === "message" && Array.isArray(target.segments)
              ? target.segments
              : [];
            const errorSegment: ChatSegment = {
              type: "text",
              content: `\n\n**Error**: ${err}`,
              isError: true,
            };
            if (target.type === "message") {
              newItems[aiMsgIdx] = {
                ...target,
                segments: [...existingSegments, errorSegment],
                content: `${existingContent}\n\n**Error**: ${err}`,
                isStreaming: false,
              };
            }
            return newItems;
          });
        },
      },
      effectiveModelId,
      attachmentPaths,
      executionWorkspaceId,
    );
    isSubmittingRef.current = false;
  }, [
    inputValue,
    selectedModelId,
    isSessionRunning,
    sessionId,
    updateChatItems,
    addUserMessage,
    addAiMessage,
    runAgentStream,
    currentWorkspaceId,
    currentWorkspaceIdRef,
    setInputValue,
    completeHost,
    completeAllTasks,
    showError,
    showSuccess,
    reloadWorkspaceFiles,
    updateWorkspaceFilesForSession,
    uploadedFiles,
    updateSessionTitle,
    loadConversations,
    handleStreamEvent,
    getSessionSlot,
    clearFiles,
    syncExecutionHistory,
    activeSessionIdRef,
    onTokenUsageShouldRefresh,
  ]);

  const handleStop = useCallback(async () => {
    // 使用最新的 sessionId，避免闭包中 sessionId 过时
    const latestSessionId = activeSessionIdRef.current || sessionId;

    // 1. 先调用后端 API 真正停止会话
    let stopApiOk = false;
    try {
      await apiRequest<{ success?: boolean; message?: string }>(
        `${apiBaseUrl}/api/agent/stop`,
        {
          method: "POST",
          body: {
            session_id: latestSessionId,
          },
        },
      );
      stopApiOk = true;
    } catch (error) {
      console.error("调用停止会话 API 失败:", error);
    }

    // 2. 更新前端状态
    const slot = getSessionSlot(latestSessionId);
    const msgId = slot.streamingMessageId;

    updateChatItems(latestSessionId, (prev: ChatItem[]) => {
      const aiMsgIdx = msgId
        ? prev.findIndex((item) => item.id === msgId)
        : prev.findIndex((item) => item.type === "message" && item.sender === "ai" && item.isStreaming);
      if (aiMsgIdx === -1) return prev;
      const newItems = [...prev];
      const target = newItems[aiMsgIdx];
      if (target.type === "message") {
        newItems[aiMsgIdx] = { ...target, isStreaming: false, isStopped: true };
      }
      return newItems;
    });

    // 只停止当前 session 的流，不影响其他 session
    stopSession(latestSessionId);

    slot.streamingSegments = [];
    slot.streamingMessageId = null;
    if (slot.flushTimer) {
      clearTimeout(slot.flushTimer);
      slot.flushTimer = null;
    }

    if (stopApiOk) {
      showSuccess("任务已停止");
    } else {
      showError("停止请求发送失败，请刷新页面重试");
    }
    onTokenUsageShouldRefresh?.();
  }, [
    stopSession,
    updateChatItems,
    getSessionSlot,
    showSuccess,
    apiBaseUrl,
    sessionId,
    onTokenUsageShouldRefresh,
  ]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  return { handleSubmit, handleStop, handleKeyDown };
}
