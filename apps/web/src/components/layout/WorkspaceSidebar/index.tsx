/**
 * Workspace context surface - 工作区上下文视图（原多任务侧边栏）
 *
 * 重构为 Context Interface 模式：
 * - 将 38 个 props 减少到 Context 管理
 * - UI 组件通过 Context 获取状态和动作
 * - Provider 隔离状态管理实现细节
 *
 * @example
 * ```tsx
 * <WorkspaceSidebar
 *   isOpen={isOpen}
 *   taskList={taskList}
 *   onClose={handleClose}
 *   onSelectTask={handleSelectTask}
 * >
 *   <WorkspaceSidebar.Content />
 * </WorkspaceSidebar>
 * ```
 */
import { Suspense, lazy, useCallback, useEffect, useState } from "react";

import { useAuthContext } from "@/contexts/AuthContext";
import { useExecutionTree } from "@/hooks/useExecutionTree";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { TaskState } from "@/hooks/useMultiTaskEventStream";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { WorkspaceFile } from "@/types/task";
import { createWorkspacePreviewFile } from "@/utils/workspaceFiles";
import type {
  SessionStatusInfo,
  TaskWorkspaceSummary,
} from "@/pages/WorkspacePage/types";
import type { PreviewFile } from "./preview";
import type { SidebarTab } from "./context/types";

// Context 和 Provider
export {
  useSidebarContext,
  SidebarContext,
  type SidebarState,
  type SidebarActions,
  type SidebarMeta,
  type SidebarContextValue,
  type SidebarTab,
} from "./context";
export { SidebarProvider } from "./SidebarProvider";
import { SidebarProvider } from "./SidebarProvider";
import { SidebarContainer } from "./SidebarContainer";
import { SidebarHeader } from "./SidebarHeader";
import { WorkspaceContextPanel } from "./WorkspaceContextPanel";
import { LoadingState } from "./LoadingState";
import { useSidebarContext } from "./context";
import type { GlobalResourceNode } from "./assetPreviewFactory";
import { WorkspaceSearchPanel } from "./WorkspaceSearchPanel";
import { FileChangesPanel } from "./FileChangesPanel";
import { isActivityPanelView } from "./context/activityBarUtils";

const LazyWorkspaceMonitorPanel = lazy(() =>
  import("./WorkspaceMonitorPanel").then((module) => ({
    default: module.WorkspaceMonitorPanel,
  })),
);

const LazyWorkspaceAssetPanel = lazy(() =>
  import("./WorkspaceAssetPanel").then((module) => ({
    default: module.WorkspaceAssetPanel,
  })),
);

const LazyWorkspaceSubagentPanel = lazy(() => import("./WorkspaceSubagentPanel"));

const LazyTerminalPanel = lazy(() =>
  import("@/components/terminal/TerminalPanel").then((module) => ({
    default: module.TerminalPanel,
  })),
);

function SidebarPanelFallback() {
  return (
    <div className="flex h-full min-h-[160px] items-center justify-center text-xs text-muted-foreground">
      面板加载中...
    </div>
  );
}

interface WorkspaceSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onOpen: () => void;
  taskList: TaskState[];
  selectedTask?: TaskState;
  selectedTaskId?: string;
  onSelectTask: (taskId: string) => void;
  hasAnyRunning?: boolean;
  width?: number;
  onWidthChange?: (width: number) => void;
  sessionId?: string;
  sessionTitle?: string | null;
  messageCount?: number;
  executionRecordCount?: number;
  lastRuntimeState?: string | null;
  isSessionRunning?: boolean;
  isCompactingConversation?: boolean;
  isRestartingRuntime?: boolean;
  isLoadingHistory?: boolean;
  userModels?: LLMModelConfig[];
  workspaceFiles?: WorkspaceFile[];
  pendingUploadedFiles?: Pick<UploadedFile, "filename" | "file_path">[];
  initialArtifactFile?: PreviewFile | null;
  onDeleteFile?: (filename: string) => Promise<boolean>;
  onDeleteFolder?: (folderPath: string) => Promise<boolean>;
  onReadFileContent?: (filename: string) => Promise<string | null>;
  onRefreshWorkspaceFiles?: () => Promise<void>;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  onUploadFiles?: (files: File[] | FileList) => Promise<void>;
  onViewExecutionRecords?: () => Promise<void> | void;
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
  onRestartRuntime?: () => Promise<void> | void;
  activeTabRequest?: {
    tab: SidebarTab;
    key: number;
    targetWorkspaceId?: string | null;
  } | null;
  workspaceSummary?: TaskWorkspaceSummary;
  sessionStatus?: SessionStatusInfo | null;
  executionSummary?: unknown;
  /** 打开工作区配置 */
  onOpenWorkspaceSettings?: () => void;
  /** 打开数据库连接管理 */
  onManageDatabaseConnections?: () => void;
  /** 新建数据库连接 */
  onCreateDatabaseConnection?: () => void;
  /** 打开工作区能力 */
  /** 打开知识库管理 */
  onOpenKnowledgeBaseDialog?: () => void;
  /** 打开知识图谱管理 */
  onOpenKnowledgeGraphDialog?: () => void;
  /** 在中间主画布打开文件 */
  onOpenCanvasPreview?: (file: PreviewFile) => void;
  /** 在浏览器标签页打开文件 */
  onOpenInBrowserTab?: (file: WorkspaceFile) => void;
  /** 在中间主画布打开全局资源 */
  onOpenGlobalResourceInMainCanvas?: (node: GlobalResourceNode) => void;
  /** 在主画布编辑区打开文件 */
  onEditInMainCanvas?: (file: PreviewFile) => void;
  /** 打开工作区资源设置 */
  onOpenWorkspaceResourcesSettings?: () => void;
  /** 在中间主画布打开当前工作区图谱 */
  onOpenKnowledgeGraphCanvas?: (payload: {
    workspaceId: string;
    workspaceTitle?: string | null;
    primaryKnowledgeGraphId?: string | null;
  }) => void;
  /** 托管面板需要把用户桥接回当前会话输入时调用 */
  onRequestHostClarification?: (request: {
    draft: string;
    targetSessionId?: string | null;
  }) => void;
  onRequestSubagentDock?: () => void;
  onRequestHostingDock?: () => void;
  /** 打开全局自动化任务管理 */
  onOpenGlobalAutoTask?: () => void;
  onOpenTerminalTab?: () => void;
  onOpenCapabilityDetailTab?: (capabilityId: string, displayName: string) => void;
  onNewConversation?: () => void;
  /** 是否为深度研究模式 */
  /** 研究状态 */
  /** 是否正在加载研究状态 */
  autoTaskContent?: React.ReactNode;
  children?: React.ReactNode;}

interface WorkspaceSidebarContentProps {
  onOpenCanvasPreview?: (file: PreviewFile) => void;
  onOpenInBrowserTab?: (file: WorkspaceFile) => void;
  onOpenGlobalResourceInMainCanvas?: (node: GlobalResourceNode) => void;
  onEditInMainCanvas?: (file: PreviewFile) => void;
  onOpenKnowledgeBaseDialog?: () => void;
  onOpenKnowledgeGraphDialog?: () => void;
  onOpenWorkspaceSettings?: () => void;
  onOpenWorkspaceResourcesSettings?: () => void;
  layoutMode?: "sidebar" | "center";
  userModels?: LLMModelConfig[];
  pendingUploadedFiles?: Pick<UploadedFile, "filename" | "file_path">[];
  initialArtifactFile?: PreviewFile | null;
  onUploadFiles?: (files: File[] | FileList) => Promise<void>;
  onRequestHostClarification?: (request: {
    draft: string;
    targetSessionId?: string | null;
  }) => void;
  onRequestSubagentDock?: () => void;
  onOpenSubagentInMainCanvas?: (subagentId: string) => void;
  editorContent?: React.ReactNode;
  autoTaskContent?: React.ReactNode;
  onOpenGlobalAutoTask?: () => void;
  onNewConversation?: () => void;
  onOpenDatabaseQueryTab?: (handle: string) => void;
  onOpenTerminalTab?: () => void;
  onOpenCapabilityDetailTab?: (capabilityId: string, displayName: string) => void;
}

function WorkspaceSidebarContent({
  onOpenCanvasPreview,
  onOpenGlobalResourceInMainCanvas,
  onEditInMainCanvas,
  onOpenInBrowserTab,
  onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog,
  onOpenWorkspaceSettings: providedOpenWorkspaceSettings,
  onOpenWorkspaceResourcesSettings,
  layoutMode = "sidebar",
  userModels: _userModels = [],
  pendingUploadedFiles = [],
  initialArtifactFile,
  onUploadFiles,
  onRequestHostClarification: _onRequestHostClarification,
  onRequestSubagentDock,
  onOpenSubagentInMainCanvas,
  editorContent,
  autoTaskContent,
  onOpenGlobalAutoTask,
  onNewConversation,
  onOpenDatabaseQueryTab,
  onOpenTerminalTab,
  onOpenCapabilityDetailTab,
}: WorkspaceSidebarContentProps) {
  void _userModels;
  const { user, session } = useAuthContext();
  const token = session?.token;
  const {
    state: {
      isLoadingHistory,
      activeTab,
      workspaceSummary,
      sessionStatus,
      workspaceFiles,
      sessionId,
      sessionTitle,
      messageCount,
      executionRecordCount,
      lastRuntimeState,
      isSessionRunning,
      isCompactingConversation,
      isRestartingRuntime,
      isExporting: exportingState,
    },
    actions: {
      exportWorkspace,
      exportWorkspaceFile,
      onClose,
      onDeleteFile,
      onDeleteFolder,
      onReadFileContent,
      onRefreshWorkspaceFiles,
      onMoveFile,
      onViewExecutionRecords,
      onCompactConversation,
      onRestartRuntime,
      onOpenWorkspaceSettings: contextOpenWorkspaceSettings,
      onManageDatabaseConnections,
      onCreateDatabaseConnection,
    },
  } = useSidebarContext();
  void onViewExecutionRecords;
  const onOpenWorkspaceSettings =
    providedOpenWorkspaceSettings ?? contextOpenWorkspaceSettings;
  const [shouldLoadExecutionTree, setShouldLoadExecutionTree] = useState(false);
  const [pinnedSubAgentIds, setPinnedSubAgentIds] = useState<Set<string>>(new Set());
  const buildWorkspacePreviewFile = useCallback(
    (fileName: string): PreviewFile =>
      createWorkspacePreviewFile(fileName, sessionId, token),
    [sessionId, token],
  );
  const handleOpenSearchResult = useCallback(
    (file: WorkspaceFile) => {
      onOpenCanvasPreview?.(buildWorkspacePreviewFile(file.name));
    },
    [buildWorkspacePreviewFile, onOpenCanvasPreview],
  );

  useEffect(() => {
    // 当切换到协作节点或托管模式时，按需加载执行树。
    setShouldLoadExecutionTree(activeTab === "subagents" || activeTab === "monitor");
  }, [sessionId, activeTab]);

  const handleExecutionTreeActivated = useCallback(() => {
    setShouldLoadExecutionTree(true);
  }, []);

  const handleTogglePin = useCallback((agentId: string) => {
    setPinnedSubAgentIds((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) {
        next.delete(agentId);
      } else {
        next.add(agentId);
      }
      return next;
    });
  }, []);

  const {
    executionTree,
    selectedSubAgent,
    isLoadingTree,
    isLoadingSubAgent,
    selectSubAgent,
    stopSubAgent,
    retrySubAgent,
  } = useExecutionTree(user?.id, sessionId, {
    enabled: shouldLoadExecutionTree,
    loadCodeExecutionRecords: false,
  });
  const subagentCount = executionTree
    ? executionTree.subagent_calls.length
    : sessionStatus?.collaboration_node_summary?.total_count ?? null;
  const runningSubagentCount =
    executionTree?.subagent_calls.filter(
      (call) => call.subagent.status === "running" || call.subagent.status === "queued",
    ).length ??
    sessionStatus?.collaboration_node_summary?.running_count ??
    null;

  const normalizedActiveTab = isActivityPanelView(activeTab) ? activeTab : "artifacts";

  const body = isLoadingHistory ? (
    <LoadingState />
  ) : (
    <WorkspaceContextPanel
      activeTab={normalizedActiveTab}
      layoutMode={layoutMode}
      workspaceSummary={workspaceSummary}
      sessionStatus={sessionStatus}
      workspaceFiles={workspaceFiles}
      sessionId={sessionId}
      messageCount={messageCount}
      executionRecordCount={executionRecordCount}
      lastRuntimeState={lastRuntimeState}
      isSessionRunning={isSessionRunning}
      isCompactingConversation={isCompactingConversation}
      isRestartingRuntime={isRestartingRuntime}
      onCompactConversation={onCompactConversation}
      onRestartRuntime={onRestartRuntime}
      onOpenWorkspaceSettings={onOpenWorkspaceSettings}
      onManageDatabaseConnections={onManageDatabaseConnections}
      onCreateDatabaseConnection={onCreateDatabaseConnection}
      onExecutionTreeActivated={handleExecutionTreeActivated}
      onRequestSubagentDock={onRequestSubagentDock}
      onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
      onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
      onOpenWorkspaceResourcesSettings={onOpenWorkspaceResourcesSettings}
      onOpenGlobalAutoTask={onOpenGlobalAutoTask}
      onNewConversation={onNewConversation}
      userId={user?.id}
      editorContent={editorContent}
      autoTaskContent={autoTaskContent}
      searchContent={
        <WorkspaceSearchPanel
          files={workspaceFiles}
          onOpenFile={handleOpenSearchResult}
        />
      }
      fileChangesContent={
        <FileChangesPanel
          workspaceId={workspaceSummary?.workspace_id ?? null}
        />
      }
      monitorContent={
        <Suspense fallback={<SidebarPanelFallback />}>
          <LazyWorkspaceMonitorPanel
            userId={user?.id}
            sessionId={sessionId}
          />
        </Suspense>
      }
      subagentContent={
        <Suspense fallback={<SidebarPanelFallback />}>
          <LazyWorkspaceSubagentPanel
            executionTree={executionTree}
            selectedSubAgent={selectedSubAgent}
            isLoadingTree={isLoadingTree}
            isLoadingSubAgent={isLoadingSubAgent}
            onSelectSubAgent={selectSubAgent}
            onStopSubAgent={stopSubAgent}
            onRetrySubAgent={retrySubAgent}
            onTogglePin={handleTogglePin}
            pinnedSubAgentIds={pinnedSubAgentIds}
            userId={user?.id}
            sessionId={sessionId}
            onOpenInMainCanvas={onOpenSubagentInMainCanvas}
            compact
          />
        </Suspense>
      }
      artifactsContent={
        <Suspense fallback={<SidebarPanelFallback />}>
          <LazyWorkspaceAssetPanel
            files={workspaceFiles}
            sessionId={sessionId}
            workspaceId={workspaceSummary?.workspace_id}
            workspaceSummary={workspaceSummary}
            pendingUploadedFiles={pendingUploadedFiles}
            initialFile={initialArtifactFile}
            onDeleteFile={onDeleteFile}
            onDeleteFolder={onDeleteFolder}
            onReadFileContent={onReadFileContent}
            onRefreshWorkspaceFiles={onRefreshWorkspaceFiles}
            onMoveFile={onMoveFile}
            onUploadFiles={onUploadFiles}
            onExportMarkdownFile={exportWorkspaceFile}
            onOpenInMainCanvas={onOpenCanvasPreview}
            onOpenInBrowserTab={onOpenInBrowserTab}
            onEditInMainCanvas={onEditInMainCanvas}
            onOpenWorkspaceSettings={onOpenWorkspaceSettings}
            surfaceMode={layoutMode === "center" ? "navigation" : "workbench"}
          />
        </Suspense>
      }
      resourcesContent={
        <Suspense fallback={<SidebarPanelFallback />}>
          <LazyWorkspaceAssetPanel
            scope="global"
            workspaceId={workspaceSummary?.workspace_id}
            sessionId={sessionId}
            onOpenGlobalResourceInMainCanvas={onOpenGlobalResourceInMainCanvas}
            onOpenInMainCanvas={onOpenCanvasPreview}
            onOpenInBrowserTab={onOpenInBrowserTab}
            onEditInMainCanvas={onEditInMainCanvas}
            surfaceMode={layoutMode === "center" ? "navigation" : "workbench"}
          />
        </Suspense>
      }
      terminalContent={
        user?.id && sessionId ? (
          <Suspense fallback={<SidebarPanelFallback />}>
            <LazyTerminalPanel
              userId={user.id}
              sessionId={sessionId}
            />
          </Suspense>
        ) : undefined
      }
      subagentCount={subagentCount}
      runningSubagentCount={runningSubagentCount}
      onOpenDatabaseQueryTab={onOpenDatabaseQueryTab}
      onOpenTerminalTab={onOpenTerminalTab}
      onOpenCapabilityDetailTab={onOpenCapabilityDetailTab}
    />
  );

  if (layoutMode === "center") {
    return body;
  }

  return (
    <SidebarContainer>
      <SidebarHeader
        sessionId={sessionId}
        sessionTitle={sessionTitle}
        isExporting={exportingState}
        onExport={exportWorkspace}
        onClose={onClose}
      />
      {body}
    </SidebarContainer>
  );
}

export type WorkspaceContextSurfaceProps = Omit<
  WorkspaceSidebarProps,
  "isOpen" | "onClose" | "onOpen" | "width" | "onWidthChange"
> & {
  defaultActiveTab?: SidebarTab;
  editorContent?: React.ReactNode;
  onOpenSubagentInMainCanvas?: (subagentId: string) => void;
  onOpenDatabaseQueryTab?: (handle: string) => void;
  onOpenTerminalTab?: () => void;
  onOpenCapabilityDetailTab?: (capabilityId: string, displayName: string) => void;
};

export function WorkspaceContextSurface({
  taskList,
  selectedTask,
  selectedTaskId,
  onSelectTask,
  sessionId,
  sessionTitle,
  messageCount,
  executionRecordCount,
  lastRuntimeState,
  isSessionRunning,
  isCompactingConversation,
  isRestartingRuntime,
  isLoadingHistory,
  userModels,
  workspaceFiles,
  pendingUploadedFiles,
  initialArtifactFile,
  onDeleteFile,
  onDeleteFolder,
  onReadFileContent,
  onRefreshWorkspaceFiles,
  onMoveFile,
  onUploadFiles,
  onViewExecutionRecords,
  onCompactConversation,
  onRestartRuntime,
  activeTabRequest,
  workspaceSummary,
  sessionStatus,
  onOpenWorkspaceSettings,
  onManageDatabaseConnections,
  onCreateDatabaseConnection,
  onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog,
  onOpenCanvasPreview,
  onOpenInBrowserTab,
  onOpenGlobalResourceInMainCanvas,
  onEditInMainCanvas,
  onOpenWorkspaceResourcesSettings,
  onRequestHostClarification,
  onRequestSubagentDock,
  onOpenSubagentInMainCanvas,
  onNewConversation,
  defaultActiveTab = "artifacts",
  editorContent,
  autoTaskContent,
  children,
  onOpenDatabaseQueryTab,
  onOpenTerminalTab,
  onOpenCapabilityDetailTab,
}: WorkspaceContextSurfaceProps) {
  return (
    <SidebarProvider
      isOpen={true}
      taskList={taskList}
      selectedTask={selectedTask}
      selectedTaskId={selectedTaskId}
      onSelectTask={onSelectTask}
      onClose={() => {}}
      onOpen={() => {}}
      width={400}
      sessionId={sessionId}
      sessionTitle={sessionTitle}
      messageCount={messageCount}
      executionRecordCount={executionRecordCount}
      lastRuntimeState={lastRuntimeState}
      isSessionRunning={isSessionRunning}
      isCompactingConversation={isCompactingConversation}
      isRestartingRuntime={isRestartingRuntime}
      isLoadingHistory={isLoadingHistory}
      workspaceFiles={workspaceFiles}
      pendingUploadedFiles={pendingUploadedFiles}
      onDeleteFile={onDeleteFile}
      onDeleteFolder={onDeleteFolder}
      onReadFileContent={onReadFileContent}
      onRefreshWorkspaceFiles={onRefreshWorkspaceFiles}
      onMoveFile={onMoveFile}
      onUploadFiles={onUploadFiles}
      onViewExecutionRecords={onViewExecutionRecords}
      onCompactConversation={onCompactConversation}
      onRestartRuntime={onRestartRuntime}
      activeTabRequest={activeTabRequest}
      workspaceSummary={workspaceSummary}
      sessionStatus={sessionStatus}
      onOpenWorkspaceSettings={onOpenWorkspaceSettings}
      onManageDatabaseConnections={onManageDatabaseConnections}
      onCreateDatabaseConnection={onCreateDatabaseConnection}
      onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
      onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
      defaultActiveTab={defaultActiveTab}
    >
      {children || (
        <WorkspaceSidebarContent
          onOpenCanvasPreview={onOpenCanvasPreview}
          onOpenInBrowserTab={onOpenInBrowserTab}
          onOpenGlobalResourceInMainCanvas={onOpenGlobalResourceInMainCanvas}
          onEditInMainCanvas={onEditInMainCanvas}
          onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
          onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
          onOpenWorkspaceSettings={onOpenWorkspaceSettings}
          onOpenWorkspaceResourcesSettings={onOpenWorkspaceResourcesSettings}
          layoutMode="center"
          userModels={userModels}
          pendingUploadedFiles={pendingUploadedFiles}
          initialArtifactFile={initialArtifactFile}
          onUploadFiles={onUploadFiles}
          onRequestHostClarification={onRequestHostClarification}
          onRequestSubagentDock={onRequestSubagentDock}
          onOpenSubagentInMainCanvas={onOpenSubagentInMainCanvas}
          onNewConversation={onNewConversation}
          onOpenDatabaseQueryTab={onOpenDatabaseQueryTab}
          onOpenTerminalTab={onOpenTerminalTab}
          onOpenCapabilityDetailTab={onOpenCapabilityDetailTab}
          editorContent={editorContent}
          autoTaskContent={autoTaskContent}
        />
      )}
    </SidebarProvider>
  );
}

function WorkspaceSidebarRoot({
  isOpen,
  onClose,
  onOpen,
  taskList,
  selectedTask,
  selectedTaskId,
  onSelectTask,
  hasAnyRunning: _hasAnyRunning,
  width = 440,
  onWidthChange,
  sessionId,
  sessionTitle,
  messageCount,
  executionRecordCount,
  lastRuntimeState,
  isSessionRunning,
  isCompactingConversation,
  isRestartingRuntime,
  isLoadingHistory,
  userModels,
  workspaceFiles,
  pendingUploadedFiles,
  initialArtifactFile,
  onDeleteFile,
  onDeleteFolder,
  onReadFileContent,
  onRefreshWorkspaceFiles,
  onUploadFiles,
  onViewExecutionRecords,
  onCompactConversation,
  onRestartRuntime,
  activeTabRequest,
  workspaceSummary,
  sessionStatus,
  executionSummary: _executionSummary,
  onOpenWorkspaceSettings,
  onManageDatabaseConnections,
  onCreateDatabaseConnection,
  onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog,
  onOpenCanvasPreview,
  onOpenInBrowserTab,
  onOpenGlobalResourceInMainCanvas,
  onEditInMainCanvas,
  onOpenWorkspaceResourcesSettings,
  onOpenKnowledgeGraphCanvas: _onOpenKnowledgeGraphCanvas,
  autoTaskContent,
  onRequestHostClarification,
  onRequestSubagentDock,
  onOpenTerminalTab,
  onOpenCapabilityDetailTab,
  children,
}: WorkspaceSidebarProps) {
  void _hasAnyRunning;
  void _executionSummary;
  void _onOpenKnowledgeGraphCanvas;

  return (
    <SidebarProvider
      isOpen={isOpen}
      taskList={taskList}
      selectedTask={selectedTask}
      selectedTaskId={selectedTaskId}
      onSelectTask={onSelectTask}
      onClose={onClose}
      onOpen={onOpen}
      width={width}
      onWidthChange={onWidthChange}
      sessionId={sessionId}
      sessionTitle={sessionTitle}
      messageCount={messageCount}
      executionRecordCount={executionRecordCount}
      lastRuntimeState={lastRuntimeState}
      isSessionRunning={isSessionRunning}
      isCompactingConversation={isCompactingConversation}
      isRestartingRuntime={isRestartingRuntime}
      isLoadingHistory={isLoadingHistory}
      workspaceFiles={workspaceFiles}
      pendingUploadedFiles={pendingUploadedFiles}
      onDeleteFile={onDeleteFile}
      onDeleteFolder={onDeleteFolder}
      onReadFileContent={onReadFileContent}
      onRefreshWorkspaceFiles={onRefreshWorkspaceFiles}
      onUploadFiles={onUploadFiles}
      onViewExecutionRecords={onViewExecutionRecords}
      onCompactConversation={onCompactConversation}
      onRestartRuntime={onRestartRuntime}
      activeTabRequest={activeTabRequest}
      workspaceSummary={workspaceSummary}
      sessionStatus={sessionStatus}
      onOpenWorkspaceSettings={onOpenWorkspaceSettings}
      onManageDatabaseConnections={onManageDatabaseConnections}
      onCreateDatabaseConnection={onCreateDatabaseConnection}
      onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
      onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
    >
      {children || (
        <WorkspaceSidebarContent
          onOpenCanvasPreview={onOpenCanvasPreview}
          onOpenInBrowserTab={onOpenInBrowserTab}
          onOpenGlobalResourceInMainCanvas={onOpenGlobalResourceInMainCanvas}
          onEditInMainCanvas={onEditInMainCanvas}
          onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
          onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
          onOpenWorkspaceSettings={onOpenWorkspaceSettings}
          onOpenWorkspaceResourcesSettings={onOpenWorkspaceResourcesSettings}
          userModels={userModels}
          pendingUploadedFiles={pendingUploadedFiles}
          initialArtifactFile={initialArtifactFile}
          onUploadFiles={onUploadFiles}
          onRequestHostClarification={onRequestHostClarification}
          onRequestSubagentDock={onRequestSubagentDock}
          onOpenTerminalTab={onOpenTerminalTab}
          onOpenCapabilityDetailTab={onOpenCapabilityDetailTab}
          autoTaskContent={autoTaskContent}
        />
      )}
    </SidebarProvider>
  );
}

export const WorkspaceSidebar = WorkspaceSidebarRoot;

export default WorkspaceSidebarRoot;
