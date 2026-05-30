import { useMemo } from "react";
import { Bot } from "lucide-react";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { ChatItem } from "../../types";
import type { RuntimeControlsState } from "./types";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { SessionStatusInfo, TaskWorkspaceSummary } from "../../types";
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
  inputValue: string;
  onInputChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown: (event: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  isRunning: boolean;
  isPrewarming: boolean;
  isUploading: boolean;
  onStop: () => void;
  uploadedFiles: UploadedFile[];
  onRemoveFile: (index: number) => void;
  onAddFileClick: () => void;
  onImportFromSession: () => void;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  runtimeControls: RuntimeControlsState;
  hasMessagesForMcp: boolean;
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
  onOpenWorkspaceSettings?: () => void;
  isCompactingConversation?: boolean;
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
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
  onViewToolDetails,
  onRewriteUserMessage,
  inputValue,
  onInputChange,
  onSubmit,
  onKeyDown,
  isRunning,
  isPrewarming,
  isUploading,
  onStop,
  uploadedFiles,
  onRemoveFile,
  onAddFileClick,
  onImportFromSession,
  fileInputRef,
  onFileChange,
  runtimeControls,
  hasMessagesForMcp,
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
  onOpenWorkspaceSettings,
  isCompactingConversation = false,
  onCompactConversation,
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
      onViewToolDetails,
      onRewriteUserMessage,
    }),
    [
      onWorkerClick,
      onOpenWorkspaceArtifact,
      onViewToolDetails,
      onRewriteUserMessage,
    ],
  );

  if (!isOpen) {
    return (
      <div className="pointer-events-none absolute bottom-4 right-4 z-30">
        <button
          type="button"
          data-testid="conversation-dock-collapsed-toggle"
          className="pointer-events-auto relative flex h-12 w-12 items-center justify-center rounded-full border border-border bg-background text-foreground shadow-[0_14px_34px_rgba(15,23,42,0.18)]  transition-transform hover:scale-[1.02] hover:bg-background"
          onClick={onOpen}
          title="展开对话侧栏"
        >
          <Bot className="h-5 w-5 text-success" />
          <span className="absolute bottom-1.5 right-1.5 h-2.5 w-2.5 rounded-full border border-background bg-success" />
          <span className="sr-only">展开对话侧栏</span>
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
        sessionStatus={sessionStatus}
        onNewConversation={onNewConversation}
        onClose={onClose}
        onSelectConversation={onSelectConversation}
        onForkConversation={onForkConversation}
        onRenameConversation={onRenameConversation}
        onDeleteConversation={onDeleteConversation}
      />

      <DockChatView
        currentSessionId={currentSessionId}
        chatItems={chatItems}
        messagesEndRef={messagesEndRef}

        onWorkerClick={onWorkerClick}
        onOpenWorkspaceArtifact={onOpenWorkspaceArtifact}
        onViewToolDetails={onViewToolDetails}
        chatAreaActions={chatAreaActions}
        inputValue={inputValue}
        onInputChange={onInputChange}
        onSubmit={onSubmit}
        onKeyDown={onKeyDown}
        isRunning={isRunning}
        isPrewarming={isPrewarming}
        isUploading={isUploading}
        onStop={onStop}
        uploadedFiles={uploadedFiles}
        onRemoveFile={onRemoveFile}
        onAddFileClick={onAddFileClick}
        onImportFromSession={onImportFromSession}
        fileInputRef={fileInputRef}
        onFileChange={onFileChange}
        runtimeControls={runtimeControls}
        hasMessagesForMcp={hasMessagesForMcp}
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
        onOpenRuntimeConfig={onOpenWorkspaceSettings}
        isCompactingConversation={isCompactingConversation}
        onCompactConversation={onCompactConversation}
        sessionInputFocusSignal={sessionInputFocusSignal}
        tokenUsageRefreshSignal={tokenUsageRefreshSignal}
      />
    </aside>
  );
}
