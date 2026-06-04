import type { LLMModelConfig } from "@/lib/api/llm";
import type {
  SessionDeletionOptions,
  UseCodeExecutorReturn,
} from "../../hooks/useCodeExecutor/executorTypes";
import type { UseSessionLifecycleManagerReturn } from "../../hooks/useSessionLifecycleManager";
import type { useWorkspaceRuntimeControls } from "../../hooks/useWorkspaceRuntimeControls";
import type { TaskWorkspaceSummary } from "../../types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { WorkspaceSidebarTab } from "./hooks/useSidebarTabRequest";

export type RuntimeControlsState = ReturnType<typeof useWorkspaceRuntimeControls>;

export interface WorkspaceLayoutProps {
  apiBaseUrl: string;
  executor: UseCodeExecutorReturn;
  workspaces: TaskWorkspaceSummary[];
  isLoadingWorkspaces: boolean;
  isLoadingMore?: boolean;
  hasMore?: boolean;
  currentWorkspaceId?: string;
  currentWorkspace?: TaskWorkspaceSummary;
  loadWorkspaces: () => Promise<unknown>;
  loadMoreWorkspaces?: () => Promise<void>;
  runtimeControls: RuntimeControlsState;
  sessionLifecycle: UseSessionLifecycleManagerReturn;
  userModels: LLMModelConfig[];
  selectedModelId: string;
  effectiveModelDisplayName?: string | null;
  onSelectModel: (modelId: string) => Promise<void> | void;
  thinkingEnabled: boolean;
  thinkingEffort: "low" | "medium" | "high";
  setThinkingEnabled: (enabled: boolean) => void;
  setThinkingEffort: (effort: "low" | "medium" | "high") => void;
  selectedModelSupportsThinking: boolean;
  hasMessagesForMcp: boolean;
  hasMCPConfig: boolean;
  onDeleteSession: (
    sessionId: string,
    options?: SessionDeletionOptions,
  ) => Promise<void>;
  onOpenDatabaseConnectionsDialog: () => void;
  onCreateDatabaseConnectionDialog: () => void;
  onOpenKnowledgeBaseDialog: () => void;
  onOpenKnowledgeGraphDialog: () => void;
  onOpenLLMConfigDialog: () => void;
  onOpenToolConfig: () => void;
  onViewToolDetails: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
}

export interface MainContentProps {
  executor: UseCodeExecutorReturn;
  runtimeControls: RuntimeControlsState;
  sessionLifecycle: UseSessionLifecycleManagerReturn;
  workspaces: TaskWorkspaceSummary[];
  isLoadingWorkspaces: boolean;
  userModels: LLMModelConfig[];
  selectedModelId: string;
  effectiveModelDisplayName?: string | null;
  onSelectModel: (modelId: string) => Promise<void> | void;
  thinkingEnabled: boolean;
  thinkingEffort: "low" | "medium" | "high";
  setThinkingEnabled: (enabled: boolean) => void;
  setThinkingEffort: (effort: "low" | "medium" | "high") => void;
  selectedModelSupportsThinking: boolean;
  hasMessagesForMcp: boolean;
  hasMCPConfig: boolean;
  onOpenDatabaseConnectionsDialog: () => void;
  onCreateDatabaseConnectionDialog: () => void;
  onOpenKnowledgeBaseDialog: () => void;
  onOpenKnowledgeGraphDialog: () => void;
  onOpenLLMConfigDialog: () => void;
  onOpenToolConfig: () => void;
  onViewToolDetails: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  sessionTitle: string | null;
  currentWorkspace?: TaskWorkspaceSummary;
  onSelectWorkspace: (workspaceId: string) => void;
  onSelectConversation: (sessionId: string) => void;
  onNewConversation: () => void;
  onNewWorkspace: () => void;
  onForkConversation: (conversationId: string) => void;
  onRenameConversation: (sessionId: string, title: string) => Promise<void>;
  onDeleteConversation?: (sessionId: string) => Promise<void>;
  onOpenGlobalAutoTask?: () => void;
  onOpenWorkspaceSettings?: () => void;
  activeTabRequest: {
    tab: WorkspaceSidebarTab;
    key: number;
    targetWorkspaceId?: string | null;
  } | null;
  requestSidebarTab?: (tab: WorkspaceSidebarTab) => void;
  initialArtifactFile?: PreviewFile | null;
}
