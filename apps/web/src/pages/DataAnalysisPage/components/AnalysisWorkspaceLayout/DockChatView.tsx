import { ChatArea } from "@/components/chat/ChatArea";
import { TokenUsageBar } from "@/components/chat/TokenUsageBar";
import type { ChatItem } from "../../types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { RuntimeControlsState } from "./types";
import { InputArea } from "../InputArea";

interface UploadedFile {
  filename: string;
  size: number;
  progress?: number;
}

interface DockChatViewProps {
  currentSessionId?: string;
  chatItems: ChatItem[];
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  onViewExecutionSpace?: (taskId: string) => void;
  onWorkerClick?: (workerName: string) => void;
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
  onViewToolDetails?: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  chatAreaActions: {
    onViewExecutionSpace?: (taskId: string) => void;
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
  };
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
  onOpenRuntimeConfig?: () => void;
  isCompactingConversation?: boolean;
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
  sessionInputFocusSignal?: number;
  tokenUsageRefreshSignal?: number | string;
}

export function DockChatView({
  currentSessionId,
  chatItems,
  messagesEndRef,
  onViewExecutionSpace,
  onWorkerClick,
  onOpenWorkspaceArtifact,
  onViewToolDetails,
  chatAreaActions,
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
  onOpenRuntimeConfig,
  isCompactingConversation = false,
  onCompactConversation,
  sessionInputFocusSignal,
  tokenUsageRefreshSignal,
}: DockChatViewProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <TokenUsageBar
        sessionId={currentSessionId || undefined}
        refreshSignal={tokenUsageRefreshSignal}
      />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/15">
        <ChatArea
          items={chatItems}
          messagesEndRef={messagesEndRef}
          onViewExecutionSpace={onViewExecutionSpace}
          onWorkerClick={onWorkerClick}
          onViewToolDetails={onViewToolDetails}
          sessionId={currentSessionId || undefined}
          layout="rail"
          onOpenWorkspaceArtifact={onOpenWorkspaceArtifact}
          onRewriteUserMessage={chatAreaActions.onRewriteUserMessage}
          isRunning={isRunning}
        >
          {chatItems.length > 0 ? (
            <ChatArea.List
              items={chatItems}
              actions={chatAreaActions}
              sessionId={currentSessionId || undefined}
              layout="rail"
              isRunning={isRunning}
            />
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-background px-4 py-4 text-sm text-muted-foreground">
              当前对话还没有聊天记录。
            </div>
          )}
        </ChatArea>
      </div>

      <InputArea
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
        currentEnv={runtimeControls.activeEnv}
        isInitializingEnvironment={
          runtimeControls.isInitializingEnvironment
        }
        sessionId={currentSessionId || undefined}
        hasMessages={hasMessagesForMcp}
        isCompactingConversation={isCompactingConversation}
        onCompactConversation={onCompactConversation}
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
        onOpenConfig={onOpenLLMConfigDialog}
        onOpenToolConfig={onOpenToolConfig}
        onOpenRuntimeConfig={onOpenRuntimeConfig}
        focusSignal={sessionInputFocusSignal}
      />
    </div>
  );
}
