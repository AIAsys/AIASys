import { Suspense, cloneElement, isValidElement, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocalStorageState } from "@/hooks/useLocalStorageState";
import {
  Database,
  GitBranch,
  Puzzle,
  Radio,
  ScrollText,
  Settings,
  Terminal,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import type {
  SessionStatusInfo,
  TaskWorkspaceSummary,
} from "@/pages/WorkspacePage/types";
import { ActivityBar, type ActivityBarItem } from "./ActivityBar";
import { ActivitySidebar } from "./ActivitySidebar";
import {
  getBucketCount,
  getRuntimeSummaryLabel,
  SummaryChip,
} from "./WorkspaceSummaryCards";
import {
  getDefaultActivityItems,
  applyOrder,
  getViewButtons,
  isActivityPanelView,
  type ActivityPanelView,
  type ViewButton,
} from "./context/activityBarUtils";
import { useWorkspaceOverview } from "./hooks/useWorkspaceOverview";
import { EnvVarsPanel } from "@/components/workspace/EnvVarsPanel";
import { CapabilityListPanel } from "@/components/CapabilityPanel/CapabilityListPanel";
import { WorkspaceAgentConfigPanel } from "@/components/workspace/WorkspaceAgentConfigPanel";

const LazyDatabaseQueryWorkbench = lazy(() =>
  import("@/components/database/DatabaseQueryWorkbench").then((module) => ({
    default: module.DatabaseQueryWorkbench,
  })),
);

const LazyWorkspaceDatabaseConnectionsPanel = lazy(() =>
  import("./WorkspaceDatabaseConnectionsPanel").then((module) => ({
    default: module.WorkspaceDatabaseConnectionsPanel,
  })),
);


const LazyWorkspaceCanvasOverview = lazy(() =>
  import("./WorkspaceCanvasOverview").then((module) => ({
    default: module.WorkspaceCanvasOverview,
  })),
);

const LazyResourceOverviewPanel = lazy(() =>
  import("./ResourceOverviewPanel").then((module) => ({
    default: module.ResourceOverviewPanel,
  })),
);

const LazyCapabilityPanel = lazy(() =>
  import("@/components/CapabilityPanel").then((module) => ({
    default: module.CapabilityPanel,
  })),
);

type WorkspacePanelView = ActivityPanelView | "channel";
type WorkspaceContextPanelLayoutMode = "sidebar" | "center";

function ContextPanelFallback() {
  return (
    <div className="flex h-full min-h-0 items-center justify-center px-6 text-sm text-muted-foreground">
      面板加载中...
    </div>
  );
}

function normalizeActivityPanelView(view: WorkspacePanelView): ActivityPanelView {
  return isActivityPanelView(view) ? view : "artifacts";
}

interface WorkspaceContextPanelProps {
  activeTab: WorkspacePanelView;
  layoutMode?: WorkspaceContextPanelLayoutMode;
  workspaceSummary?: TaskWorkspaceSummary;
  sessionStatus?: SessionStatusInfo | null;
  workspaceFiles: Array<{ name: string }>;
  sessionId?: string;
  messageCount?: number;
  executionRecordCount?: number;
  lastRuntimeState?: string | null;
  isSessionRunning?: boolean;
  isCompactingConversation?: boolean;
  isRestartingRuntime?: boolean;
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
  onRestartRuntime?: () => Promise<void> | void;
  onOpenWorkspaceSettings?: () => void;
  artifactsContent: React.ReactNode;
  searchContent?: React.ReactNode;
  monitorContent: React.ReactNode;
  subagentContent: React.ReactNode;
  terminalContent?: React.ReactNode;
  resourceContent?: React.ReactNode;
  resourcesContent?: React.ReactNode;
  editorContent?: React.ReactNode;
  autoTaskContent?: React.ReactNode;
  fileChangesContent?: React.ReactNode;
  onOpenGlobalAutoTask?: () => void;

  subagentCount?: number | null;
  runningSubagentCount?: number | null;
  onExecutionTreeActivated?: () => void;
  onRequestSubagentDock?: () => void;
  onManageDatabaseConnections?: () => void;
  onCreateDatabaseConnection?: () => void;
  onOpenKnowledgeBaseDialog?: () => void;
  onOpenKnowledgeGraphDialog?: () => void;
  onOpenWorkspaceResourcesSettings?: () => void;
  onNewConversation?: () => void;
  onViewExecutionRecords?: () => Promise<void> | void;
  userId?: string;
  onOpenDatabaseQueryTab?: (handle: string) => void;
  onOpenTerminalTab?: () => void;
  onOpenCapabilityDetailTab?: (capabilityId: string, displayName: string) => void;
}

export function WorkspaceContextPanel({
  activeTab,
  layoutMode = "sidebar",
  workspaceSummary,
  sessionStatus,
  workspaceFiles,
  sessionId,
  messageCount,
  executionRecordCount,
  lastRuntimeState,
  isSessionRunning: _isSessionRunning = false,
  isRestartingRuntime: _isRestartingRuntime = false,
  onRestartRuntime: _onRestartRuntime,
  onOpenWorkspaceSettings,
  onManageDatabaseConnections,
  onCreateDatabaseConnection,
  onViewExecutionRecords,
  artifactsContent,
  searchContent,
  monitorContent,
  subagentContent,
  terminalContent,
  resourceContent: providedResourceContent,
  resourcesContent,
  editorContent,
  autoTaskContent,
  fileChangesContent,
  onOpenGlobalAutoTask: _onOpenGlobalAutoTask,
  subagentCount: _subagentCount = null,
  runningSubagentCount: _runningSubagentCount = null,
  onExecutionTreeActivated,
  onRequestSubagentDock: _onRequestSubagentDock,
  onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog,
  onOpenWorkspaceResourcesSettings,
  onNewConversation,
  userId,
  onOpenDatabaseQueryTab,
  onOpenTerminalTab,
  onOpenCapabilityDetailTab,
}: WorkspaceContextPanelProps) {

  const [activeView, setActiveView] = useState<WorkspacePanelView>(
    activeTab,
  );
  const [activitySidebarWidth, setActivitySidebarWidth] = useState(() =>
    typeof window !== "undefined" && window.innerWidth < 1440 ? 280 : 320,
  );
  const [isActivitySidebarCollapsed, setIsActivitySidebarCollapsed] = useLocalStorageState(
    "aiasys:ui:isActivitySidebarCollapsed",
    false,
  );
  const [isActivitySidebarResizing, setIsActivitySidebarResizing] = useState(false);
  const activityResizeStartX = useRef(0);
  const activityResizeStartWidth = useRef(360);
  const [selectedDatabaseHandle, setSelectedDatabaseHandle] = useState<string | null>(null);
  const [visitedActivityViews, setVisitedActivityViews] = useState<Set<ActivityPanelView>>(
    () => new Set([normalizeActivityPanelView(activeTab)]),
  );
  const hasProvidedResourceContent = Boolean(providedResourceContent);
  // 预加载 workspaceOverview：后端在本地，延迟低，提前加载提升 database tab 和 header 数据体验
  const shouldLoadOverview = !hasProvidedResourceContent;
  const { workspaceOverview, isLoadingOverview } = useWorkspaceOverview(
    workspaceSummary?.workspace_id,
    sessionId || workspaceSummary?.current_conversation?.session_id || "no-session",
    shouldLoadOverview,
  );

  useEffect(() => {
    let nextView = activeTab;
    if (layoutMode === "center" && nextView === "terminal") {
      nextView = "artifacts";
    }
    setActiveView(nextView);
  }, [activeTab, layoutMode]);

  // 数据库选中后在 PaneRenderer 中以 Tab 形式打开查询工作台
  useEffect(() => {
    if (
      layoutMode === "center" &&
      selectedDatabaseHandle &&
      sessionId &&
      onOpenDatabaseQueryTab
    ) {
      onOpenDatabaseQueryTab(selectedDatabaseHandle);
    }
  }, [selectedDatabaseHandle, sessionId, layoutMode, onOpenDatabaseQueryTab]);

  useEffect(() => {
    if (layoutMode !== "center") {
      return;
    }

    const syncLayoutWidth = () => {
      const narrow = window.innerWidth < 1100;
      setIsActivitySidebarCollapsed(narrow);
    };

    syncLayoutWidth();
    window.addEventListener("resize", syncLayoutWidth);
    return () => window.removeEventListener("resize", syncLayoutWidth);
  }, [layoutMode, setIsActivitySidebarCollapsed]);

  useEffect(() => {
    if (!isActivitySidebarResizing) {
      return;
    }

    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";

    const handleMouseMove = (event: MouseEvent) => {
      const deltaX = event.clientX - activityResizeStartX.current;
      const maxWidth = Math.max(320, Math.min(560, window.innerWidth * 0.42));
      const nextWidth = Math.min(
        Math.max(280, activityResizeStartWidth.current + deltaX),
        maxWidth,
      );
      setActivitySidebarWidth(nextWidth);
    };

    const handleMouseUp = () => {
      setIsActivitySidebarResizing(false);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [isActivitySidebarResizing]);

  useEffect(() => {
    if (activeView === "subagents") {
      onExecutionTreeActivated?.();
    }
  }, [activeView, onExecutionTreeActivated]);

  useEffect(() => {
    const currentActivityView = normalizeActivityPanelView(activeView);
    setVisitedActivityViews((current) => {
      if (current.has(currentActivityView)) {
        return current;
      }
      const next = new Set(current);
      next.add(currentActivityView);
      return next;
    });
  }, [activeView]);

  const handleActiveViewChange = useCallback(
    (nextView: WorkspacePanelView) => {
      if (nextView === "subagents") {
        onExecutionTreeActivated?.();
      }
      if (nextView === "terminal" && layoutMode === "center") {
        onOpenTerminalTab?.();
        return;
      }
      setActiveView(nextView);
      // 窄屏下保持折叠，避免挤压主画布
      const narrow = typeof window !== "undefined" && window.innerWidth < 1440;
      if (!narrow) {
        setIsActivitySidebarCollapsed(false);
      }
    },
    [onExecutionTreeActivated, layoutMode, onOpenTerminalTab, setIsActivitySidebarCollapsed],
  );

  const handleActivitySidebarResizeStart = useCallback(
    (event: React.MouseEvent<HTMLDivElement>) => {
      activityResizeStartX.current = event.clientX;
      activityResizeStartWidth.current = activitySidebarWidth;
      setIsActivitySidebarResizing(true);
    },
    [activitySidebarWidth],
  );

  const toggleActivitySidebar = useCallback(() => {
    setIsActivitySidebarCollapsed((current) => !current);
  }, [setIsActivitySidebarCollapsed]);

  // Header 派生数据统一用 useMemo 缓存，避免 sidebar resize / activeView 变化时重复计算
  const headerData = useMemo(() => {
    const capabilitySummary = sessionStatus?.workspace_capability_summary;
    const runtimeSummary =
      workspaceOverview?.runtime.runtime_summary ||
      sessionStatus?.runtime_summary;
    const overviewResources = workspaceOverview?.resources ?? null;
    const databaseItem = overviewResources?.database ?? null;
    const knowledgeBaseItem = overviewResources?.knowledge_base ?? null;
    const knowledgeGraphItem = overviewResources?.knowledge_graph ?? null;
    const mountedKnowledgeBaseCount =
      (capabilitySummary as { mounted_knowledge_base_count?: number } | undefined)
        ?.mounted_knowledge_base_count ??
      0;
    const knowledgeGraphCount = knowledgeGraphItem?.user_asset_count ?? 0;
    const mountedKnowledgeBaseNames =
      knowledgeBaseItem?.ids?.filter(Boolean) ?? [];
    const attachedDatabaseCount = getBucketCount(databaseItem);
    const currentSessionOverview = workspaceOverview?.current_session ?? null;
    const currentSessionTitle =
      sessionStatus?.title ||
      currentSessionOverview?.title ||
      workspaceSummary?.current_conversation?.title ||
      "未命名会话";
    const workspaceId = workspaceSummary?.workspace_id ?? null;
    const resolvedMessageCount = Math.max(
      messageCount ?? 0,
      sessionStatus?.message_count ?? 0,
      currentSessionOverview?.message_count ?? 0,
      workspaceSummary?.current_conversation?.message_count ?? 0,
    );
    const resolvedExecutionRecordCount = Math.max(
      executionRecordCount ?? 0,
      sessionStatus?.execution_record_count ?? 0,
      workspaceOverview?.artifacts.execution_record_count ?? 0,
      currentSessionOverview?.execution_record_count ?? 0,
      workspaceSummary?.current_conversation?.execution_record_count ?? 0,
    );
    const effectiveLastRuntimeState =
      workspaceOverview?.runtime.last_runtime_state || lastRuntimeState;
    const runtimeLabel = getRuntimeSummaryLabel(
      runtimeSummary,
      effectiveLastRuntimeState,
    );
    const sessionTasks = sessionStatus?.tasks ?? [];
    const activeTasks = sessionTasks.filter((task) =>
      task.status === "pending" || task.status === "in_progress",
    );
    const inProgressTask = sessionTasks.find((task) => task.status === "in_progress");
    const planState = sessionStatus?.plan_state ?? null;
    const isPlanModeActive = planState?.mode === "active";
    const isPlanPendingApproval = planState?.approval_status === "pending_approval";
    const completedTaskCount =
      sessionStatus?.task_counts?.completed ??
      sessionTasks.filter((task) => task.status === "completed").length;
    const totalTaskCount = sessionTasks.length;

    return {
      databaseItem,
      knowledgeGraphItem,
      mountedKnowledgeBaseCount,
      knowledgeGraphCount,
      mountedKnowledgeBaseNames,
      attachedDatabaseCount,
      currentSessionTitle,
      workspaceId,
      resolvedMessageCount,
      resolvedExecutionRecordCount,
      runtimeLabel,
      sessionTasks,
      activeTasks,
      inProgressTask,
      planState,
      isPlanModeActive,
      isPlanPendingApproval,
      completedTaskCount,
      totalTaskCount,
    };
  }, [
    sessionStatus,
    workspaceOverview,
    workspaceSummary,
    messageCount,
    executionRecordCount,
    lastRuntimeState,
  ]);

  const {
    databaseItem,
    knowledgeGraphItem,
    mountedKnowledgeBaseCount,
    knowledgeGraphCount,
    mountedKnowledgeBaseNames,
    attachedDatabaseCount,
    currentSessionTitle,
    workspaceId,
    resolvedMessageCount,
    resolvedExecutionRecordCount,
    runtimeLabel,
    sessionTasks,
    planState,
  } = headerData;
  const viewButtons: ViewButton[] = getViewButtons(layoutMode);
  const [activityItems, setActivityItems] = useState<Array<ActivityBarItem<ActivityPanelView>>>(
    getDefaultActivityItems,
  );

  useEffect(() => {
    if (!userId) return;
    const resolvedUserId = userId;
    let cancelled = false;
    async function loadOrder() {
      try {
        const { getUserUISettings } = await import("@/lib/api/uiSettings");
        const settings = await getUserUISettings(resolvedUserId);
        if (cancelled) return;
        const ordered = applyOrder(
          getDefaultActivityItems(),
          settings.activityBarOrder,
        );
        setActivityItems(ordered);
      } catch {
        // 读取失败时保持默认顺序
      }
    }
    void loadOrder();
    return () => {
      cancelled = true;
    };
  }, [userId]);

  const handleActivityReorder = useCallback(
    (newOrder: ActivityPanelView[]) => {
      const defaults = getDefaultActivityItems();
      const itemMap = new Map(defaults.map((i) => [i.id, i]));
      const reordered = newOrder
        .map((id) => itemMap.get(id))
        .filter((i): i is ActivityBarItem<ActivityPanelView> => Boolean(i));
      if (reordered.length === defaults.length) {
        setActivityItems(reordered);
        if (userId) {
          import("@/lib/api/uiSettings")
            .then(({ saveUserUISettings }) =>
              saveUserUISettings(userId, { activityBarOrder: newOrder }),
            )
            .catch(() => {
              // 保存失败静默处理
            });
        }
      }
    },
    [userId],
  );
  const activityView = normalizeActivityPanelView(activeView);
  const isCenterEditorOnlyActivityView = false;

  const currentViewLabel =
    activityItems.find((button) => button.id === activityView)?.label ||
    viewButtons.find((button) => button.id === activeView)?.label ||
    "资产";


  const fallbackResourceContent = (
    <Suspense fallback={<ContextPanelFallback />}>
      <LazyResourceOverviewPanel
        workspaceId={workspaceId}
        isLoading={isLoadingOverview}
        knowledgeBaseCount={mountedKnowledgeBaseCount}
        knowledgeGraphCount={knowledgeGraphCount}
        databaseCount={attachedDatabaseCount}
        sessionId={sessionId}
        knowledgeBaseNames={mountedKnowledgeBaseNames}
        knowledgeGraphItem={knowledgeGraphItem}
        databaseItem={databaseItem}
        onOpenKnowledgeBase={onOpenKnowledgeBaseDialog}
        onOpenKnowledgeGraph={onOpenKnowledgeGraphDialog}
        onManageResources={onOpenWorkspaceResourcesSettings}
        onManageDatabases={onManageDatabaseConnections}
      />
    </Suspense>
  );

  const workspaceCanvasContent = (
    <Suspense fallback={<ContextPanelFallback />}>
      <LazyWorkspaceCanvasOverview
        workspaceTitle={workspaceSummary?.title || "当前工作区"}
        sessionTitle={currentSessionTitle}
        runtimeLabel={runtimeLabel}
        messageCount={resolvedMessageCount}
        executionRecordCount={resolvedExecutionRecordCount}
        fileCount={workspaceFiles.length}
        recentFiles={workspaceFiles.slice(0, 5)}
        planState={planState}
        tasks={sessionTasks}
        onNewBranch={onNewConversation}
        onOpenSettings={onOpenWorkspaceSettings}
        onViewRecords={onViewExecutionRecords}
        onOpenFiles={() => {
          handleActiveViewChange("artifacts");
          setIsActivitySidebarCollapsed(false);
        }}
      />
    </Suspense>
  );

  const resourceContent = providedResourceContent ?? fallbackResourceContent;

  // 统一面板配置表：消除 tabPanels / activityTabPanels 的重复定义
  // 两份数组顺序不同、少数面板内容不同，其余共享同一份节点引用
  const { tabPanels, activityTabPanels } = useMemo(() => {
    // 公共面板节点（在 sidebar 和 activity 上下文中内容相同）
    const searchNode = searchContent ?? (
      <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
        当前工作区搜索暂时不可用。
      </div>
    );
    const envNode = workspaceSummary ? (
      <EnvVarsPanel workspaceSummary={workspaceSummary} />
    ) : (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <ScrollText className="h-6 w-6 text-muted-foreground/40" />
        <div className="mt-3 text-sm font-medium text-foreground">环境变量</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          当前工作区的环境变量会显示在这里。
        </div>
      </div>
    );
    const terminalNode = terminalContent ?? (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <Terminal className="h-6 w-6 text-muted-foreground/40" />
        <div className="mt-3 text-sm font-medium text-foreground">终端</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          选择一个会话以打开终端。
        </div>
      </div>
    );
    const autoTasksNode = autoTaskContent ?? (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <Zap className="h-6 w-6 text-muted-foreground/40" />
        <div className="mt-3 text-sm font-medium text-foreground">自动化任务</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          当前工作区的自动化任务会显示在这里。
        </div>
      </div>
    );
    const fileChangesNode = fileChangesContent ?? (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <GitBranch className="h-6 w-6 text-muted-foreground/40" />
        <div className="mt-3 text-sm font-medium text-foreground">文件变更</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          工作区文件的变更记录会显示在这里。
        </div>
      </div>
    );
    // sidebar 模式面板（右侧 Tab 切换）
    const tabPanels: { id: string; node: React.ReactNode }[] = [
      { id: "artifacts", node: artifactsContent },
      { id: "monitor", node: monitorContent },
      { id: "subagents", node: subagentContent },
      { id: "search", node: searchNode },
      { id: "file-changes", node: fileChangesNode },
      {
        id: "database",
        node:
          selectedDatabaseHandle && sessionId ? (
            <Suspense fallback={<ContextPanelFallback />}>
              <LazyDatabaseQueryWorkbench
                sessionId={sessionId}
                initialHandle={selectedDatabaseHandle}
                showHandleSelector={false}
              />
            </Suspense>
          ) : (
            <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted-foreground">
              <Database className="mb-2 h-8 w-8 opacity-50" />
              <p className="text-sm font-medium text-foreground/80">未选择数据库</p>
              <p className="mt-1 text-xs leading-5">从左侧列表选择一个连接开始查询。</p>
            </div>
          ),
      },
      { id: "env", node: envNode },
      { id: "terminal", node: terminalNode },
      {
        id: "capabilities",
        node: workspaceId ? (
          <Suspense fallback={<ContextPanelFallback />}>
            <LazyCapabilityPanel workspaceId={workspaceId} />
          </Suspense>
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <Puzzle className="h-6 w-6 text-muted-foreground/40" />
            <div className="mt-3 text-sm font-medium text-foreground">能力管理</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              请先打开一个工作区。
            </div>
          </div>
        ),
      },
      { id: "auto-tasks", node: autoTasksNode },
      {
        id: "agent-config",
        node: workspaceId ? (
          <WorkspaceAgentConfigPanel workspaceId={workspaceId} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <Settings className="h-6 w-6 text-muted-foreground/40" />
            <div className="mt-3 text-sm font-medium text-foreground">工作区设置</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              请先打开一个工作区。
            </div>
          </div>
        ),
      },
    ];

    // activity 模式面板（左侧 ActivitySidebar 内容）
    const monitorActivityNode = monitorContent ?? (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <Radio className="h-6 w-6 text-muted-foreground/40" />
        <div className="mt-3 text-sm font-medium text-foreground">监控任务</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          监控任务的输出和状态会显示在这里。
        </div>
      </div>
    );
    const capabilitiesActivityNode = workspaceId ? (
      <CapabilityListPanel
        workspaceId={workspaceId}
        onSelectCap={(capId, displayName) => onOpenCapabilityDetailTab?.(capId, displayName)}
      />
    ) : (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center">
        <Puzzle className="h-6 w-6 text-muted-foreground/40" />
        <div className="mt-3 text-sm font-medium text-foreground">能力管理</div>
        <div className="mt-1 text-xs leading-5 text-muted-foreground">
          请先打开一个工作区。
        </div>
      </div>
    );
    const resourcesNode = resourcesContent ?? (
      <div className="flex h-full items-center justify-center px-6 text-sm text-muted-foreground">
        全局工作区暂时不可用。
      </div>
    );

    const activityTabPanels: { id: string; node: React.ReactNode }[] = [
      { id: "artifacts", node: artifactsContent },
      { id: "search", node: searchNode },
      {
        id: "database",
        node: (
          <Suspense fallback={<ContextPanelFallback />}>
            <LazyWorkspaceDatabaseConnectionsPanel
              sessionId={sessionId}
              selectedHandle={selectedDatabaseHandle}
              onSelectHandle={setSelectedDatabaseHandle}
              onManageConnections={onManageDatabaseConnections}
              onCreateConnection={onCreateDatabaseConnection}
            />
          </Suspense>
        ),
      },
      { id: "file-changes", node: fileChangesNode },
      { id: "resources", node: resourcesNode },
      { id: "monitor", node: monitorActivityNode },
      { id: "auto-tasks", node: autoTasksNode },
      { id: "subagents", node: subagentContent },
      { id: "env", node: envNode },
      { id: "terminal", node: terminalNode },
      { id: "capabilities", node: capabilitiesActivityNode },
      {
        id: "agent-config",
        node: workspaceId ? (
          <WorkspaceAgentConfigPanel workspaceId={workspaceId} />
        ) : (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <Settings className="h-6 w-6 text-muted-foreground/40" />
            <div className="mt-3 text-sm font-medium text-foreground">工作区设置</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              请先打开一个工作区。
            </div>
          </div>
        ),
      },
    ];

    return { tabPanels, activityTabPanels };
  }, [
    artifactsContent,
    monitorContent,
    subagentContent,
    searchContent,
    selectedDatabaseHandle,
    sessionId,
    workspaceSummary,
    workspaceId,
    terminalContent,
    autoTaskContent,
    fileChangesContent,
    resourcesContent,
    onManageDatabaseConnections,
    onCreateDatabaseConnection,
    onOpenCapabilityDetailTab,
  ]);

  // keep-alive 只保留高频切换的 tab，减少重建开销同时控制内存增长
  const keepAliveActivityViews = new Set<ActivityPanelView>(["artifacts", "resources", "subagents", "terminal"]);
  const visibleActivityPanels = activityTabPanels.filter((panel) => {
    const panelId = panel.id as ActivityPanelView;
    return panelId === activityView || (keepAliveActivityViews.has(panelId) && visitedActivityViews.has(panelId));
  });

  const activitySidebarContent = (
    <div className="relative flex h-full w-full flex-col">
      {visibleActivityPanels.map((panel) => (
        <div
          key={panel.id}
          className={cn(
            "h-full w-full min-h-0 flex-col",
            panel.id === activityView ? "flex" : "hidden",
          )}
        >
          {panel.node}
        </div>
      ))}
    </div>
  );
  const editorSurface = editorContent ?? workspaceCanvasContent;

  const showBranchContextInHeader = layoutMode !== "center";

  const headerContent = (
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0">
        <div className="text-[11px] text-muted-foreground">当前工作区</div>
        <div className="mt-1 truncate text-sm font-semibold text-foreground">
          {workspaceSummary?.title || "未绑定工作区"}
        </div>
        {showBranchContextInHeader ? (
          <div className="mt-1 truncate text-[12px] text-muted-foreground">
            {currentSessionTitle}
          </div>
        ) : null}
        <div className="mt-2 flex flex-wrap gap-2">
          <SummaryChip>{currentViewLabel}</SummaryChip>
          <SummaryChip>
            {workspaceSummary?.conversation_count ?? 0} 个会话
          </SummaryChip>
          <SummaryChip>{resolvedMessageCount} 条消息</SummaryChip>
          <SummaryChip>{resolvedExecutionRecordCount} 条记录</SummaryChip>
          <SummaryChip>{runtimeLabel}</SummaryChip>
        </div>
      </div>
      <div className="flex items-center gap-2" />
    </div>
  );
  return (
    <div
      className={
        layoutMode === "center"
          ? "relative flex h-full min-h-0 min-w-0 flex-1 flex-col bg-background"
          : "flex h-full min-h-0 flex-col bg-background"
      }
    >
      {layoutMode === "center" ? (
        <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
          <ActivityBar
            items={activityItems}
            activeView={activityView}
            isSidebarCollapsed={
              isActivitySidebarCollapsed || isCenterEditorOnlyActivityView
            }
            canToggleSidebar={!isCenterEditorOnlyActivityView}
            onSelectView={handleActiveViewChange as (view: ActivityPanelView) => void}
            onToggleSidebar={toggleActivitySidebar}
            onReorder={handleActivityReorder}
          />
          <ActivitySidebar
            title={currentViewLabel}
            width={activitySidebarWidth}
            isCollapsed={
              isActivitySidebarCollapsed || isCenterEditorOnlyActivityView
            }
            isResizing={isActivitySidebarResizing}
            onCollapse={() => setIsActivitySidebarCollapsed(true)}
            onResizeStart={handleActivitySidebarResizeStart}
          >
            {activitySidebarContent}
          </ActivitySidebar>
          <div className="flex min-w-0 flex-1 flex-col overflow-hidden bg-background">
            {editorSurface}
          </div>
        </div>
      ) : (
        <>
          <div className="border-b border-border px-4 py-3">
            {headerContent}

            <div className="mt-3 flex flex-wrap gap-2">
              {viewButtons.map((button) => (
                <Button
                  key={button.id}
                  type="button"
                  size="sm"
                  variant={activeView === button.id ? "default" : "outline"}
                  className="h-8 text-[11px]"
                  onClick={() => handleActiveViewChange(button.id)}
                >
                  {button.label}
                </Button>
              ))}
            </div>
          </div>

          <div className="relative flex min-h-0 flex-1 flex-col overflow-hidden">
            {tabPanels.map((panel) => {
              const isActive = panel.id === (activeView || "resource-overview");
              // 为 terminal 面板注入 visible prop
              let node = panel.node;
              if (panel.id === "terminal" && isValidElement(node)) {
                node = cloneElement(node as React.ReactElement<{ visible?: boolean }>, { visible: isActive });
              }
              return (
                <div
                  key={panel.id}
                  className="flex h-full w-full min-h-0 flex-col"
                  style={{ display: isActive ? undefined : "none" }}
                >
                  {panel.id === "resource-overview" && !activeView ? resourceContent : node}
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

export default WorkspaceContextPanel;
