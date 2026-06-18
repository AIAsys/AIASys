import { useMemo } from "react";
import { Bot } from "lucide-react";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { ChatItem } from "../../types";
import type { RuntimeControlsState } from "./types";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { SessionStatusInfo, TaskWorkspaceSummary } from "../../types";
import type { FailedUpload } from "@/hooks/useAgentFileUpload";
import { useDockResize } from "./useDockResize";
import { DockHeader } from "./DockHeader";
import { DockChatView } from "./DockChatView";

interface UploadedFile {
  filename: string;
  size: number;
  progress?: number;
}

interface ConversationDockProps {
  isOpen: boolean;
  width: number;
  onWidthChange?: (width: number) => void;
  onOpen: () => void;
  onClose: () => void;
  workspace?: TaskWorkspaceSummary;
  sessionStatus?: SessionStatusInfo | null;
  currentSessionId?: string;
  sessionTitle?: string | null;
  chatItems: ChatItem[];
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  onSelectConversation: (sessionId: string) => void;
  onNewConversation: () => void;
  onForkConversation: (conversationId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<void>;
  onDeleteConversation?: (sessionId: string) => Promise<void>;
  onWorkerClick?: (workerName: string) => void;
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
  onOpenInBrowserTab?: (path: string) => void;
  onViewToolDetails?: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  onRewriteUserMessage?: (
    messageId: string,
    content: string,
    originalContent?: string,
  ) => Promise<void> | void;
  /** 重试上一次失败的提交 */
  onRetryLastSubmit?: () => Promise<void> | void;
  /** 加载更多历史消息 */
  onLoadMoreHistory?: () => Promise<void>;
  /** 是否还有更多历史消息 */
  hasMoreHistory?: boolean;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  isRunning: boolean;
  isPrewarming: boolean;
  isUploading: boolean;
  /** 当前上传进度 0-100，null 表示不在上传中 */
  uploadProgress?: number | null;
  onStop: () => void;
  uploadedFiles: UploadedFile[];
  /** 上传失败的文件列表 */
  failedUploads?: FailedUpload[];
  /** 重试某个失败的上传 */
  onRetryUpload?: (id: string) => void;
  /** 移除某个失败的上传记录 */
  onRemoveFailedUpload?: (id: string) => void;
  onRemoveFile: (index: number) => void;
  onAddFileClick: () => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  runtimeControls: RuntimeControlsState;
  hasMCPConfig: boolean;
  userModels: LLMModelConfig[];
  selectedModelId: string;
  effectiveModelDisplayName?: string | null;
  onSelectModel: (modelId: string) => Promise<void> | void;
  thinkingEnabled: boolean;
  thinkingEffort: "low" | "medium" | "high";
  setThinkingEnabled: (enabled: boolean) => void;
  setThinkingEffort: (effort: "low" | "medium" | "high") => void;
  selectedModelSupportsThinking: boolean;
  onOpenLLMConfigDialog: () => void;
  onOpenToolConfig: () => void;
  onOpenRuntimeTab?: () => void;
  isCompactingConversation?: boolean;
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
  compactionState?: {
    phase: "begin" | "done";
    tokens_before?: number;
    tokens_after?: number;
    saved_tokens?: number;
    summary_tokens?: number;
  } | null;
  sessionInputFocusSignal?: number;
  tokenUsageRefreshSignal?: number | string;
}

export function ConversationDock({
  isOpen,
  width,
  onWidthChange,
  onOpen,
  onClose,
  workspace,
  sessionStatus,
  currentSessionId,
  sessionTitle,
  chatItems,
  messagesEndRef,
  onSelectConversation,
  onNewConversation,
  onForkConversation,
  onRenameConversation,
  onDeleteConversation,
  onWorkerClick,
  onOpenWorkspaceArtifact,
  onOpenInBrowserTab,
  onViewToolDetails,
  onRewriteUserMessage,
  onRetryLastSubmit,
  onLoadMoreHistory,
  hasMoreHistory,
  inputValue,
  onInputChange,
  onSubmit,
  onKeyDown,
  isRunning,
  isPrewarming,
  isUploading,
  uploadProgress,
  onStop,
  uploadedFiles,
  failedUploads,
  onRetryUpload,
  onRemoveFailedUpload,
  onRemoveFile,
  onAddFileClick,
  fileInputRef,
  onFileChange,
  runtimeControls,
  hasMCPConfig,
  userModels,
  selectedModelId,
  effectiveModelDisplayName,
  onSelectModel,
  thinkingEnabled,
  thinkingEffort,
  setThinkingEnabled,
  setThinkingEffort,
  selectedModelSupportsThinking,
  onOpenLLMConfigDialog,
  onOpenToolConfig,
  onOpenRuntimeTab,
  isCompactingConversation = false,
  onCompactConversation,
  compactionState,
  sessionInputFocusSignal,
  tokenUsageRefreshSignal,
}: ConversationDockProps) {
  const { handleDragStart } = useDockResize(width, onWidthChange);

  const currentWorkspaceConversation =
    workspace?.conversations?.find(
      (conversation) => conversation.session_id === currentSessionId,
    ) || workspace?.current_conversation;
  const currentSessionTitle =
    sessionTitle || currentWorkspaceConversation?.title || "未命名对话";

  const chatAreaActions = useMemo(
    () => ({
      onWorkerClick,
      onOpenWorkspaceArtifact,
      onOpenInBrowserTab,
      onViewToolDetails,
      onRewriteUserMessage,
      onRetryLastSubmit,
    }),
    [
      onWorkerClick,
      onOpenWorkspaceArtifact,
      onOpenInBrowserTab,
      onViewToolDetails,
      onRewriteUserMessage,
      onRetryLastSubmit,
    ],
  );

  if (!isOpen) {
    // 折叠态指示器：运行中绿色脉冲 / 预热中琥珀色脉冲 / 空闲灰色静态
    const indicatorColor = isRunning
      ? "bg-success animate-pulse"
      : isPrewarming
        ? "bg-warning animate-pulse"
        : "bg-muted-foreground/40";
    const indicatorTitle = isRunning
      ? "会话运行中 — 展开对话侧栏"
      : isPrewarming
        ? "正在预热 — 展开对话侧栏"
        : "展开对话侧栏";
    return (
      <div className="pointer-events-none absolute bottom-4 right-4 z-30">
        <button
          type="button"
          data-testid="conversation-dock-collapsed-toggle"
          className="pointer-events-auto relative flex h-12 w-12 items-center justify-center rounded-full border border-border bg-background text-foreground shadow-[0_14px_34px_rgba(15,23,42,0.18)]  transition-transform hover:scale-[1.02] hover:bg-background"
          onClick={onOpen}
          title={indicatorTitle}
        >
          <Bot className="h-5 w-5 text-muted-foreground" />
          <span
            className={`absolute bottom-1.5 right-1.5 h-2.5 w-2.5 rounded-full border border-background ${indicatorColor}`}
          />
          <span className="sr-only">{indicatorTitle}</span>
        </button>
      </div>
    );
  }

  return (
    <aside
      className="relative flex h-full shrink-0 flex-col overflow-hidden border-l border-border bg-background"
      style={{ width: `${width}px`, maxWidth: `${width}px` }}
    >
      <div
        className="absolute bottom-0 left-0 top-0 z-10 w-1 cursor-col-resize hover:bg-border"
        onMouseDown={handleDragStart}
      />

      <DockHeader
        currentSessionTitle={currentSessionTitle}
        workspace={workspace}
        currentSessionId={currentSessionId}
        onNewConversation={onNewConversation}
        onClose={onClose}
        onSelectConversation={onSelectConversation}
        onForkConversation={onForkConversation}
        onRenameConversation={onRenameConversation}
        onDeleteConversation={onDeleteConversation}
        onCompactConversation={onCompactConversation}
        isCompactingConversation={isCompactingConversation}
        isRunning={isRunning}
        tokenUsageRefreshSignal={tokenUsageRefreshSignal}
        compactionState={compactionState}
        onOpenToolConfig={onOpenToolConfig}
        onOpenLLMConfigDialog={onOpenLLMConfigDialog}
        onOpenRuntimeTab={onOpenRuntimeTab}
      />

      <DockChatView
        currentSessionId={currentSessionId}
        chatItems={chatItems}
        messagesEndRef={messagesEndRef}

        onWorkerClick={onWorkerClick}
        onOpenWorkspaceArtifact={onOpenWorkspaceArtifact}
        onOpenInBrowserTab={onOpenInBrowserTab}
        onOpenRuntimeTab={onOpenRuntimeTab}
        onViewToolDetails={onViewToolDetails}
        chatAreaActions={chatAreaActions}
        onLoadMoreHistory={onLoadMoreHistory}
        hasMoreHistory={hasMoreHistory}
        inputValue={inputValue}
        onInputChange={onInputChange}
        onSubmit={onSubmit}
        onKeyDown={onKeyDown}
        isRunning={isRunning}
        isPrewarming={isPrewarming}
        isUploading={isUploading}
        uploadProgress={uploadProgress}
        onStop={onStop}
        uploadedFiles={uploadedFiles}
        failedUploads={failedUploads}
        onRetryUpload={onRetryUpload}
        onRemoveFailedUpload={onRemoveFailedUpload}
        onRemoveFile={onRemoveFile}
        onAddFileClick={onAddFileClick}
        fileInputRef={fileInputRef}
        onFileChange={onFileChange}
        runtimeControls={runtimeControls}
        hasMCPConfig={hasMCPConfig}
        userModels={userModels}
        selectedModelId={selectedModelId}
        effectiveModelDisplayName={effectiveModelDisplayName}
        onSelectModel={onSelectModel}
        thinkingEnabled={thinkingEnabled}
        thinkingEffort={thinkingEffort}
        setThinkingEnabled={setThinkingEnabled}
        setThinkingEffort={setThinkingEffort}
        selectedModelSupportsThinking={selectedModelSupportsThinking}
        onOpenLLMConfigDialog={onOpenLLMConfigDialog}
        onOpenToolConfig={onOpenToolConfig}
        sessionInputFocusSignal={sessionInputFocusSignal}
        tasks={sessionStatus?.tasks}
        planState={sessionStatus?.plan_state}
        workspaceId={workspace?.workspace_id}
      />
    </aside>
  );
}
