import { ChatArea } from "@/components/chat/ChatArea";
import { EmptyConversationState } from "@/components/chat/EmptyConversationState";
import { SessionTaskPanel } from "@/components/session/SessionTaskPanel";
import { ErrorBoundary } from "@/components/error/ErrorBoundary";
import { SectionErrorFallback } from "@/components/error/SectionErrorFallback";
import { AlertCircle, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { memo } from "react";
import type { ChatItem } from "../../types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { RuntimeControlsState } from "./types";
import type { SessionTaskItem, SessionPlanState } from "@/components/session/SessionTaskPanel";
import type { FailedUpload } from "@/hooks/useAgentFileUpload";
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
  onWorkerClick?: (workerName: string) => void;
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
  onOpenInBrowserTab?: (path: string) => void;
  onOpenRuntimeTab?: () => void;
  onViewToolDetails?: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  chatAreaActions: {
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
    onRetryLastSubmit?: () => Promise<void> | void;
  };
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
  isCompactingConversation?: boolean;
  isRestoringSession?: boolean;
  historyLoadError?: string | null;
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
  sessionInputFocusSignal?: number;
  tasks?: SessionTaskItem[];
  planState?: SessionPlanState | null;
  workspaceId?: string;
}

export const DockChatView = memo(function DockChatView({
  currentSessionId,
  chatItems,
  messagesEndRef,
  onWorkerClick,
  onOpenWorkspaceArtifact,
  onOpenInBrowserTab,
  onOpenRuntimeTab,
  onViewToolDetails,
  chatAreaActions,
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
  isCompactingConversation = false,
  isRestoringSession = false,
  historyLoadError = null,
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
  sessionInputFocusSignal,
  tasks,
  planState,
  workspaceId,
}: DockChatViewProps) {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <SessionTaskPanel tasks={tasks} planState={planState} />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-muted/15">
        <ErrorBoundary
          key={currentSessionId ?? "no-session"}
          fallback={(error, reset) => (
            <SectionErrorFallback error={error} reset={reset} />
          )}
        >
        <ChatArea
          items={chatItems}
          messagesEndRef={messagesEndRef}
          onWorkerClick={onWorkerClick}
          onViewToolDetails={onViewToolDetails}
          sessionId={currentSessionId || undefined}
          layout="rail"
          onOpenWorkspaceArtifact={onOpenWorkspaceArtifact}
          onOpenInBrowserTab={onOpenInBrowserTab}
          onOpenRuntimeTab={onOpenRuntimeTab}
          onRewriteUserMessage={chatAreaActions.onRewriteUserMessage}
          onRetryLastSubmit={chatAreaActions.onRetryLastSubmit}
          onLoadMoreHistory={onLoadMoreHistory}
          hasMoreHistory={hasMoreHistory}
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
          ) : isRestoringSession ? (
            <div className="flex h-full items-center justify-center">
              <div role="status" className="flex flex-col items-center gap-3 text-muted-foreground">
                <Loader2 className="h-6 w-6 animate-spin" />
                <span className="text-sm">正在加载会话历史...</span>
              </div>
            </div>
          ) : historyLoadError ? (
            <div className="flex h-full items-center justify-center">
              <div role="alert" className="flex flex-col items-center gap-3 text-center max-w-sm">
                <AlertCircle className="h-8 w-8 text-error" />
                <div className="text-sm font-medium text-foreground">加载会话历史失败</div>
                <div className="text-xs text-muted-foreground">{historyLoadError}</div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => currentSessionId && (window.location.href = window.location.pathname)}
                >
                  重试
                </Button>
              </div>
            </div>
          ) : (
            <EmptyConversationState
              onExampleClick={(text) => onInputChange(text)}
              onAddFileClick={onAddFileClick}
            />
          )}
        </ChatArea>
        </ErrorBoundary>
      </div>

      <InputArea
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
        isInitializingEnvironment={
          runtimeControls.isInitializingEnvironment
        }
        sessionId={currentSessionId || undefined}
        isCompactingConversation={isCompactingConversation}
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
        onOpenRuntimeTab={onOpenRuntimeTab}
        activeEnv={runtimeControls.activeEnv}
        focusSignal={sessionInputFocusSignal}
        workspaceId={workspaceId}
      />
    </div>
  );
});
