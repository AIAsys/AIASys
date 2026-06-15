import { Suspense, lazy, useState, useEffect } from "react";
import {
  Panel,
  Group as PanelGroup,
  Separator as PanelResizeHandle,
} from "react-resizable-panels";
import { cn } from "@/lib/utils";
import { FileCode2, Globe, File, Info } from "lucide-react";
import {
  renderAssetResourcePreview,
  resolveAssetResourceNodeFromWorkspaceFile,
} from "@/components/layout/WorkspaceSidebar/assetPreviewFactory";
import { CodeEditorPanel } from "@/components/editor/CodeEditorPanel";
import { WorkspaceTabBar, type WorkspaceTab } from "./components/WorkspaceTabBar";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type { WorkspaceFile } from "@/types/task";
import type { PaneTreeNode, PaneLeaf } from "./paneTree";
import type { WorkspaceRefreshOptions } from "../../hooks/useCodeExecutor/executorTypes";
import type { TaskWorkspaceSummary } from "../../types";

const LazyMainCanvasPreview = lazy(() =>
  import("./MainCanvasPreview").then((module) => ({
    default: module.MainCanvasPreview,
  })),
);

const LazyNotebookWorkbenchCanvas = lazy(() =>
  import("./NotebookWorkbenchCanvas").then((module) => ({
    default: module.NotebookWorkbenchCanvas,
  })),
);

const LazySubagentTabContent = lazy(() =>
  import("./SubagentTabContent").then((module) => ({
    default: module.SubagentTabContent,
  })),
);

const LazyTerminalPanel = lazy(() =>
  import("@/components/terminal/TerminalPanel").then((module) => ({
    default: module.TerminalPanel,
  })),
);

const LazyDatabaseQueryWorkbench = lazy(() =>
  import("@/components/database/DatabaseQueryWorkbench").then((module) => ({
    default: module.DatabaseQueryWorkbench,
  })),
);

const LazyCapabilityDetailPanel = lazy(() =>
  import("@/components/CapabilityPanel/CapabilityDetailPanel").then((module) => ({
    default: module.CapabilityDetailPanel,
  })),
);

const LazyExecutionResourcesPanel = lazy(() =>
  import("@/components/execution-resources/ExecutionResourcesPanel").then((module) => ({
    default: module.ExecutionResourcesPanel,
  })),
);

function MainSurfaceFallback({ label }: { label: string }) {
  return (
    <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
      {label}
    </div>
  );
}

export type CanvasDropZone = "left" | "right" | "top" | "bottom" | "center";

export function getCanvasDropZone(e: React.DragEvent): CanvasDropZone {
  const rect = e.currentTarget.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const y = e.clientY - rect.top;
  const width = rect.width;
  const height = rect.height;

  if (x < width * 0.2) return "left";
  if (x > width * 0.8) return "right";
  if (y < height * 0.25) return "top";
  if (y > height * 0.75) return "bottom";
  return "center";
}

export interface PaneRendererProps {
  paneTree: PaneTreeNode;
  dropZones: Record<string, CanvasDropZone>;
  executor: {
    sessionId: string | undefined;
    readWorkspaceFileContent: (filePath: string) => Promise<string | null>;
    refreshWorkspaceForSession: (
      sessionId: string,
      options?: WorkspaceRefreshOptions,
    ) => Promise<void>;
    workspaceFiles: WorkspaceFile[] | undefined;
  };
  currentWorkspaceId: string | undefined;
  workspaceSummary?: TaskWorkspaceSummary;
  userId?: string;
  tabDirtyMap: Record<string, boolean>;
  onActivateTab: (leafId: string, tabId: string) => void;
  onCloseTab: (leafId: string, tabId: string) => void;
  onCloseOtherTabs: (leafId: string, tabId: string) => void;
  onCloseRightTabs: (leafId: string, tabId: string) => void;
  onCloseAllTabs: (leafId: string) => void;
  onSplitPane: (leafId: string, tabId: string, direction: "horizontal" | "vertical") => void;
  onTabReorder: (leafId: string, fromIndex: number, toIndex: number) => void;
  onNewTerminalTab?: () => void;
  onOpenRuntimeTab?: () => void;
  onNewBrowserTab?: (url: string) => void;
  onOpenWorkspaceFileFromCanvas: (fileName: string) => void;
  onOpenInBrowserTab?: (url: string) => void;
  onOpenPreviewFileFromCanvas: (file: PreviewFile) => void;
  onEditFileInMainCanvas: (file: PreviewFile) => void;
  onTabDirtyChange: (tabId: string, dirty: boolean) => void;
  refreshSessionStatus: () => void;
  onDragOver: (e: React.DragEvent, leafId: string) => void;
  onDrop: (e: React.DragEvent, leafId: string) => void;
  onDragLeave: (e: React.DragEvent, leafId: string) => void;
}

export function PaneRenderer({
  paneTree,
  dropZones,
  executor,
  currentWorkspaceId,
  workspaceSummary,
  userId,
  tabDirtyMap,
  onActivateTab,
  onCloseTab,
  onCloseOtherTabs,
  onCloseRightTabs,
  onCloseAllTabs,
  onSplitPane,
  onTabReorder,
  onNewTerminalTab,
  onOpenRuntimeTab,
  onNewBrowserTab,
  onOpenInBrowserTab,
  onOpenWorkspaceFileFromCanvas,
  onOpenPreviewFileFromCanvas,
  onEditFileInMainCanvas,
  onTabDirtyChange,
  refreshSessionStatus,
  onDragOver,
  onDrop,
  onDragLeave,
}: PaneRendererProps) {
  function renderFilePreview(
    tab: WorkspaceTab,
    onClose: () => void,
    closeLabel: string,
    onSplitRight?: () => void,
    onSplitDown?: () => void,
  ) {
    const file = tab.file;
    if (tab.subagentId) {
      return (
        <Suspense fallback={<MainSurfaceFallback label="正在加载协作节点详情..." />}>
          <LazySubagentTabContent
            subagentId={tab.subagentId}
            userId={userId}
            sessionId={executor.sessionId}
            onOpenWorkspaceFile={(file) => onOpenWorkspaceFileFromCanvas(file.name)}
            onOpenInBrowserTab={onOpenInBrowserTab}
          />
        </Suspense>
      );
    }
    if (tab.terminalId) {
      return (
        <Suspense fallback={<MainSurfaceFallback label="正在加载终端..." />}>
          <LazyTerminalPanel
            userId={userId ?? ""}
            sessionId={executor.sessionId ?? ""}
            terminalId={tab.terminalId}
          />
        </Suspense>
      );
    }
    if (tab.databaseHandle && executor.sessionId) {
      return (
        <Suspense fallback={<MainSurfaceFallback label="正在加载数据查询..." />}>
          <LazyDatabaseQueryWorkbench
            sessionId={executor.sessionId}
            initialHandle={tab.databaseHandle}
            showHandleSelector={false}
          />
        </Suspense>
      );
    }
    if (tab.capabilityDetail) {
      return (
        <Suspense fallback={<MainSurfaceFallback label="正在加载能力详情..." />}>
          <LazyCapabilityDetailPanel
            workspaceId={tab.capabilityDetail.workspaceId}
            capabilityId={tab.capabilityDetail.capabilityId}
          />
        </Suspense>
      );
    }
    if (tab.url) {
      return <BrowserTabView url={tab.url} readFileContent={executor.readWorkspaceFileContent} />;
    }
    if (tab.runtime) {
      return (
        <Suspense fallback={<MainSurfaceFallback label="正在加载执行环境..." />}>
          <LazyExecutionResourcesPanel
            workspaceId={currentWorkspaceId ?? null}
            workspaceTitle={workspaceSummary?.title ?? null}
            workspaceSummary={workspaceSummary ?? null}
          />
        </Suspense>
      );
    }
    if (!file) return null;
    const resourceNode = resolveAssetResourceNodeFromWorkspaceFile(file);

    if (tab.mode === 'edit' && file.type === 'code') {
      return (
        <CodeEditorPanel
          file={file}
          sessionId={executor.sessionId ?? null}
          workspaceId={currentWorkspaceId ?? null}
          onReadFileContent={executor.readWorkspaceFileContent}
          onRefreshWorkspace={
            executor.sessionId
              ? () =>
                  executor.refreshWorkspaceForSession(executor.sessionId!, {
                    force: true,
                  })
              : undefined
          }
          onDirtyChange={(dirty) => onTabDirtyChange(tab.id, dirty)}
        />
      );
    }

    if (resourceNode) {
      const preview = renderAssetResourcePreview({
        node: resourceNode,
        sessionId: executor.sessionId ?? null,
        workspaceId: currentWorkspaceId ?? null,
        onClose,
        closeLabel,
        onSplitRight,
        onSplitDown,
        onRefresh: executor.sessionId
          ? () =>
              executor.refreshWorkspaceForSession(executor.sessionId!, {
                force: true,
              })
          : undefined,
      });
      if (preview) return preview;
    }

    if (file.type === "notebook" && tab.mode !== "preview") {
      return (
        <Suspense fallback={<MainSurfaceFallback label="正在加载 notebook workbench..." />}>
          <LazyNotebookWorkbenchCanvas
            file={file}
            sessionId={executor.sessionId}
            workspaceFiles={executor.workspaceFiles ?? []}
            onClose={onClose}
            closeLabel={closeLabel}
            onSplitRight={onSplitRight}
            onSplitDown={onSplitDown}
            onRefreshWorkspace={
              executor.sessionId
                ? () =>
                    executor.refreshWorkspaceForSession(executor.sessionId!, {
                      force: true,
                    })
                : undefined
            }
            onRefreshSessionStatus={refreshSessionStatus}
          />
        </Suspense>
      );
    }

    return (
      <Suspense fallback={<MainSurfaceFallback label="正在加载主画布预览..." />}>
        <LazyMainCanvasPreview
          file={file}
          sessionId={executor.sessionId ?? null}
          onClose={onClose}
          closeLabel={closeLabel}
          onSplitRight={onSplitRight}
          onSplitDown={onSplitDown}
          onReadFileContent={executor.readWorkspaceFileContent}
          workspaceId={currentWorkspaceId}
          workspaceFiles={executor.workspaceFiles ?? []}
          onOpenWorkspaceFile={onOpenWorkspaceFileFromCanvas}
          onOpenPreviewFile={onOpenPreviewFileFromCanvas}
          onEditFile={onEditFileInMainCanvas}
        />
      </Suspense>
    );
  }

  function renderLeaf(leaf: PaneLeaf) {
    const dropZone = dropZones[leaf.id] ?? null;

    return (
      <div
        className="relative flex h-full min-h-0 flex-col overflow-hidden"
        data-testid="canvas-drop-zone"
        data-leaf-id={leaf.id}
        onDragOver={(e) => onDragOver(e, leaf.id)}
        onDrop={(e) => onDrop(e, leaf.id)}
        onDragLeave={(e) => onDragLeave(e, leaf.id)}
      >
        {dropZone ? (
          <div className="pointer-events-none absolute inset-0 z-50">
            {dropZone === "center" ? (
              <div className="flex h-full items-center justify-center bg-primary/5">
                <div className="rounded-lg bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow">
                  放入此处
                </div>
              </div>
            ) : (
              <>
                <div
                  className={cn(
                    "absolute bg-primary/10",
                    dropZone === "left" && "inset-y-0 left-0 w-1/2",
                    dropZone === "right" && "inset-y-0 right-0 w-1/2",
                    dropZone === "top" && "inset-x-0 top-0 h-1/2",
                    dropZone === "bottom" && "inset-x-0 bottom-0 h-1/2",
                  )}
                />
                <div
                  className={cn(
                    "absolute z-10 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground shadow",
                    dropZone === "left" && "left-4 top-1/2 -translate-y-1/2",
                    dropZone === "right" && "right-4 top-1/2 -translate-y-1/2",
                    dropZone === "top" && "left-1/2 top-4 -translate-x-1/2",
                    dropZone === "bottom" && "bottom-4 left-1/2 -translate-x-1/2",
                  )}
                >
                  {dropZone === "left"
                    ? "左侧分栏"
                    : dropZone === "right"
                      ? "右侧分栏"
                      : dropZone === "top"
                        ? "上方分栏"
                        : "下方分栏"}
                </div>
                <div
                  className={cn(
                    "absolute bg-primary",
                    dropZone === "left" && "inset-y-0 left-0 w-0.5",
                    dropZone === "right" && "inset-y-0 right-0 w-0.5",
                    dropZone === "top" && "inset-x-0 top-0 h-0.5",
                    dropZone === "bottom" && "inset-x-0 bottom-0 h-0.5",
                  )}
                />
              </>
            )}
          </div>
        ) : null}

        <WorkspaceTabBar
          leafId={leaf.id}
          tabs={leaf.tabs}
          activeTabId={leaf.activeTabId}
          onTabClick={(tabId) => onActivateTab(leaf.id, tabId)}
          onTabClose={(tabId) => onCloseTab(leaf.id, tabId)}
          onTabCloseOthers={(tabId) => onCloseOtherTabs(leaf.id, tabId)}
          onTabCloseRight={(tabId) => onCloseRightTabs(leaf.id, tabId)}
          onTabCloseAll={() => onCloseAllTabs(leaf.id)}
          onTabSplitRight={(tabId) => onSplitPane(leaf.id, tabId, "horizontal")}
          onTabSplitDown={(tabId) => onSplitPane(leaf.id, tabId, "vertical")}
          onTabReorder={(fromIndex, toIndex) =>
            onTabReorder(leaf.id, fromIndex, toIndex)
          }
          onTabDirtyCheck={(tabId) => tabDirtyMap[tabId] ?? false}
          onNewTerminalTab={onNewTerminalTab}
          onOpenRuntimeTab={onOpenRuntimeTab}
          onNewBrowserTab={onNewBrowserTab}
        />
        <div className="min-h-0 flex-1 flex flex-col overflow-hidden">
          {leaf.tabs.map((tab) => {
            const isActive = tab.id === leaf.activeTabId;
            // 终端和数据库 tab 保持挂载（keep-alive），其他 tab 仅在活跃时渲染
            const isKeepAlive = !!(tab.terminalId || tab.databaseHandle);
            if (!isActive && !isKeepAlive) return null;
            return (
              <div
                key={tab.id}
                className="min-h-0 flex-1 flex flex-col overflow-hidden"
                style={{ display: isActive ? undefined : "none" }}
              >
                {renderFilePreview(
                  tab,
                  () => onCloseTab(leaf.id, tab.id),
                  leaf.tabs.length > 1 ? "关闭标签" : "返回文件资产",
                  () => onSplitPane(leaf.id, tab.id, "horizontal"),
                  () => onSplitPane(leaf.id, tab.id, "vertical"),
                )}
              </div>
            );
          })}
          {leaf.tabs.length === 0 && (
            <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-muted-foreground">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-muted/30">
                <FileCode2 className="h-4 w-4 text-muted-foreground/40" />
              </div>
              <div className="text-center">
                <div className="text-xs font-medium text-foreground">
                  当前没有打开的对象
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground/70">
                  从左侧资源树选择文件，或开始一段对话
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  function renderTree(node: PaneTreeNode): React.ReactNode {
    if (node.kind === "leaf") {
      return renderLeaf(node);
    }

    const [first, second] = node.children;
    const isHorizontal = node.direction === "horizontal";
    const handleClass = isHorizontal
      ? "relative w-1 flex items-center justify-center bg-transparent cursor-col-resize group"
      : "relative h-1 flex items-center justify-center bg-transparent cursor-row-resize group";
    const lineClass = isHorizontal
      ? "h-full w-px bg-border/60 group-hover:bg-primary/40 group-active:bg-primary group-active:w-0.5 transition-colors"
      : "w-full h-px bg-border/60 group-hover:bg-primary/40 group-active:bg-primary group-active:h-0.5 transition-colors";
    // hit area: 4px 宽透明区域，方便鼠标命中
    const hitAreaClass = isHorizontal
      ? "absolute inset-y-0 left-1/2 -translate-x-1/2 w-1"
      : "absolute inset-x-0 top-1/2 -translate-y-1/2 h-1";

    return (
      <PanelGroup
        orientation={isHorizontal ? "horizontal" : "vertical"}
        className="h-full min-h-0"
      >
        <Panel defaultSize={node.sizes[0]} minSize={10}>
          <div className="h-full min-h-0 overflow-hidden">
            {renderTree(first)}
          </div>
        </Panel>
        <PanelResizeHandle className={cn(handleClass)}>
          <div className={hitAreaClass} />
          <div className={lineClass} />
        </PanelResizeHandle>
        <Panel defaultSize={node.sizes[1]} minSize={10}>
          <div className="h-full min-h-0 overflow-hidden">
            {renderTree(second)}
          </div>
        </Panel>
      </PanelGroup>
    );
  }

  return (
    <div className="relative flex-1 min-h-0">
      {renderTree(paneTree)}
    </div>
  );
}

function BrowserTabView({ url, readFileContent }: { url: string; readFileContent?: (path: string) => Promise<string | null> }) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const isLocal = url && !url.startsWith("http");
  const isElectron = typeof window !== "undefined" && window.__AIASYS_DESKTOP__?.platform === "electron";

  useEffect(() => {
    if (!isLocal || !readFileContent) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    readFileContent(url)
      .then((text) => {
        if (!cancelled) {
          setContent(text);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [url, isLocal, readFileContent]);

  const displayPath = isLocal ? "/workspace/" + url : url;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* 地址栏 - Obsidian 风格 */}
      <div className="flex items-center gap-2 border-b border-border bg-muted/30 px-3 py-1.5">
        {isLocal ? (
          <File className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        ) : (
          <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        )}
        <span className="truncate font-mono text-xs text-foreground">
          {displayPath}
        </span>
      </div>
      {/* Web 版外部链接受限提示 */}
      {!isLocal && !isElectron ? (
        <div className="flex items-start gap-2 border-b border-border bg-amber-50 px-3 py-2 text-xs text-amber-800">
          <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>
            Web 版受浏览器安全策略限制，部分外部网站（如百度、GitHub 等）可能无法显示。
            如需完整浏览任意网站，请使用桌面版。
          </span>
        </div>
      ) : null}
      {/* 内容区 */}
      <div className="flex-1 min-h-0 bg-white">
        {loading ? (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            正在加载...
          </div>
        ) : isLocal && content ? (
          <iframe
            srcDoc={content}
            sandbox="allow-scripts"
            className="h-full w-full border-0"
            title={url}
          />
        ) : !isLocal ? (
          <iframe
            src={url}
            sandbox="allow-scripts"
            className="h-full w-full border-0"
            title={url}
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-muted-foreground">
            无法加载文件内容
          </div>
        )}
      </div>
    </div>
  );
}
