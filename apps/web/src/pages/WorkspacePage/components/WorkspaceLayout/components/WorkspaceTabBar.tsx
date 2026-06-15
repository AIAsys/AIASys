import { useRef, useState, useEffect, useCallback } from "react";
import {
  X,
  FileText,
  FileCode2,
  Image,
  Table,
  BookOpen,
  BarChart3,
  Database,
  Globe,
  File,
  Columns2,
  Rows2,
  Plus,
  Bot,
  Terminal,
  Eye,
  FlaskConical,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { PreviewFile, PreviewFileType } from "@/components/layout/WorkspaceSidebar/preview";

export interface WorkspaceTab {
  id: string;
  file?: PreviewFile;
  mode?: 'preview' | 'edit';
  subagentId?: string;
  terminalId?: string;
  databaseHandle?: string;
  capabilityDetail?: { workspaceId: string; capabilityId: string; displayName: string };
  url?: string;
  runtime?: boolean;
}

interface WorkspaceTabBarProps {
  tabs: WorkspaceTab[];
  activeTabId: string | null;
  leafId: string;
  onTabClick: (tabId: string) => void;
  onTabClose: (tabId: string) => void;
  onTabCloseOthers?: (tabId: string) => void;
  onTabCloseRight?: (tabId: string) => void;
  onTabCloseAll?: () => void;
  onTabSplitRight?: (tabId: string) => void;
  onTabSplitDown?: (tabId: string) => void;
  onTabReorder?: (fromIndex: number, toIndex: number) => void;
  onTabDirtyCheck?: (tabId: string) => boolean;
  onNewTerminalTab?: () => void;
  onOpenRuntimeTab?: () => void;
  onNewTab?: () => void;
  onNewBrowserTab?: (url: string) => void;
}

function getFileBaseName(path: string): string {
  return path.split("/").filter(Boolean).pop() || path;
}

function getBrowserTabTitle(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    try {
      return new URL(url).hostname;
    } catch {
      return url;
    }
  }
  return getFileBaseName(url);
}

function getTabIcon(type: PreviewFileType) {
  switch (type) {
    case "code":
      return FileCode2;
    case "image":
      return Image;
    case "csv":
    case "xlsx":
      return Table;
    case "pdf":
      return FileText;
    case "markdown":
      return BookOpen;
    case "notebook":
      return BookOpen;
    case "chart":
      return BarChart3;
    case "database":
      return Database;
    case "html":
      return Globe;
    default:
      return File;
  }
}

function createTabDragImage(text: string): HTMLElement {
  const el = document.createElement("div");
  el.className =
    "flex items-center gap-1.5 rounded-md border border-black/5 bg-background/90 px-3.5 py-1.5 text-xs font-medium text-foreground shadow-lg backdrop-blur";
  el.style.position = "fixed";
  el.style.top = "-9999px";
  el.style.left = "-9999px";
  el.style.zIndex = "9999";
  el.style.pointerEvents = "none";
  el.style.maxWidth = "200px";
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  svg.setAttribute("width", "12");
  svg.setAttribute("height", "12");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("class", "shrink-0 text-muted-foreground");

  const path1 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path1.setAttribute("d", "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z");
  svg.appendChild(path1);

  const path2 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path2.setAttribute("d", "M14 2v4a2 2 0 0 0 2 2h4");
  svg.appendChild(path2);

  el.appendChild(svg);
  const nameSpan = document.createElement("span");
  nameSpan.className = "truncate font-mono";
  nameSpan.textContent = text;
  el.appendChild(nameSpan);
  document.body.appendChild(el);
  return el;
}

interface TabContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  tabId: string;
}

export function WorkspaceTabBar({
  tabs,
  activeTabId,
  leafId,
  onTabClick,
  onTabClose,
  onTabCloseOthers,
  onTabCloseRight,
  onTabCloseAll,
  onTabSplitRight,
  onTabSplitDown,
  onTabReorder,
  onTabDirtyCheck,
  onNewTerminalTab,
  onOpenRuntimeTab,
  onNewTab,
  onNewBrowserTab,
}: WorkspaceTabBarProps) {
  const showActionButtons = activeTabId !== null;
  const activeTab = tabs.find((tab) => tab.id === activeTabId);
  const showTerminalNewTabButton = Boolean(activeTab?.terminalId && onNewTerminalTab);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  const [draggingIndex, setDraggingIndex] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [contextMenu, setContextMenu] = useState<TabContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    tabId: "",
  });
  const contextMenuRef = useRef<HTMLDivElement | null>(null);
  const [showNewTabDropdown, setShowNewTabDropdown] = useState(false);
  const [showUrlDialog, setShowUrlDialog] = useState(false);
  const [urlInput, setUrlInput] = useState("");
  const dropdownRef = useRef<HTMLDivElement | null>(null);

  const handleContextMenu = useCallback(
    (e: React.MouseEvent, tabId: string) => {
      e.preventDefault();
      e.stopPropagation();
      setContextMenu({ visible: true, x: e.clientX, y: e.clientY, tabId });
    },
    [],
  );

  const hideContextMenu = useCallback(() => {
    setContextMenu((prev) => ({ ...prev, visible: false }));
  }, []);

  useEffect(() => {
    if (!contextMenu.visible) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (contextMenuRef.current?.contains(event.target as Node)) return;
      hideContextMenu();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") hideContextMenu();
    };
    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [contextMenu.visible, hideContextMenu]);

  // 点击外部关闭下拉菜单
  useEffect(() => {
    if (!showNewTabDropdown) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (dropdownRef.current?.contains(event.target as Node)) return;
      setShowNewTabDropdown(false);
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [showNewTabDropdown]);

  const contextMenuTabIndex = tabs.findIndex((t) => t.id === contextMenu.tabId);
  const hasRightTabs = contextMenuTabIndex >= 0 && contextMenuTabIndex < tabs.length - 1;
  const hasOtherTabs = tabs.length > 1;

  const handleTabDragStart = (
    e: React.DragEvent,
    tab: WorkspaceTab,
    index: number,
  ) => {
    e.dataTransfer.setData("application/x-canvas-tab-id", tab.id);
    e.dataTransfer.setData("application/x-canvas-leaf-id", leafId);
    e.dataTransfer.effectAllowed = "move";
    setDraggingIndex(index);

    const ghost = createTabDragImage(
      tab.terminalId
        ? "终端"
        : tab.databaseHandle
          ? `查询 ${tab.databaseHandle}`
          : tab.capabilityDetail
            ? tab.capabilityDetail.displayName
            : tab.url
              ? tab.url
              : tab.runtime
                ? "执行环境"
                : getFileBaseName(tab.file?.name ?? tab.subagentId?.slice(0, 8) ?? "标签"),
    );
    e.dataTransfer.setDragImage(ghost, 10, 10);
    requestAnimationFrame(() => {
      setTimeout(() => {
        if (ghost.parentNode) ghost.parentNode.removeChild(ghost);
      }, 0);
    });
  };

  const handleTabDragEnd = () => {
    setDraggingIndex(null);
    setDragOverIndex(null);
  };

  const handleContainerDragOver = (e: React.DragEvent) => {
    const types = e.dataTransfer.types;
    const isTabDrag =
      types.includes("application/x-canvas-tab-id") ||
      types.includes("application/x-canvas-leaf-id");
    if (!isTabDrag || !onTabReorder || tabs.length < 2) return;

    e.preventDefault();
    e.dataTransfer.dropEffect = "move";

    const container = containerRef.current;
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const children = Array.from(container.children) as HTMLElement[];

    let insertIndex = children.length;
    for (let i = 0; i < children.length; i++) {
      const child = children[i];
      const childRect = child.getBoundingClientRect();
      const childCenter = childRect.left - rect.left + childRect.width / 2;
      if (x < childCenter) {
        insertIndex = i;
        break;
      }
    }
    setDragOverIndex(insertIndex);
  };

  const handleContainerDragLeave = (e: React.DragEvent) => {
    if (!containerRef.current?.contains(e.relatedTarget as Node)) {
      setDragOverIndex(null);
    }
  };

  const handleContainerDrop = (e: React.DragEvent) => {
    const tabId = e.dataTransfer.getData("application/x-canvas-tab-id");
    const sourceLeafId = e.dataTransfer.getData("application/x-canvas-leaf-id");
    if (!tabId) {
      setDragOverIndex(null);
      setDraggingIndex(null);
      return;
    }
    // 跨 leaf 拖拽：不拦截，让事件冒泡到 PaneRenderer 处理
    if (sourceLeafId !== leafId) {
      setDragOverIndex(null);
      setDraggingIndex(null);
      return;
    }
    // 同 leaf 拖拽重排：需要拖到 tab 之间的插入位置才处理
    if (dragOverIndex === null) {
      setDragOverIndex(null);
      setDraggingIndex(null);
      return;
    }

    e.preventDefault();
    e.stopPropagation();

    const fromIndex = tabs.findIndex((t) => t.id === tabId);
    if (fromIndex < 0) {
      setDragOverIndex(null);
      setDraggingIndex(null);
      return;
    }

    let toIndex = dragOverIndex;
    if (fromIndex < toIndex) {
      toIndex = Math.max(0, toIndex - 1);
    }
    if (fromIndex !== toIndex) {
      onTabReorder?.(fromIndex, toIndex);
    }

    setDragOverIndex(null);
    setDraggingIndex(null);
  };

  return (
    <div className="relative flex h-11 min-h-11 items-center gap-1 border-b border-border bg-muted/40 px-1.5">
      {showTerminalNewTabButton ? (
        <button
          type="button"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-background hover:text-foreground"
          title="新建终端"
          aria-label="新建终端"
          onClick={onNewTerminalTab}
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      ) : null}
      <div
        ref={containerRef}
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto px-1"
        onDragOver={handleContainerDragOver}
        onDragLeave={handleContainerDragLeave}
        onDrop={handleContainerDrop}
      >
        {tabs.map((tab, index) => {
          const isActive = tab.id === activeTabId;
          const isDragging = draggingIndex === index;
          const showInsertBefore = dragOverIndex === index && draggingIndex !== index;
          const isDirty = onTabDirtyCheck?.(tab.id) ?? false;
          const isSubagent = !!tab.subagentId;
          const isTerminal = !!tab.terminalId;
          const isDatabase = !!tab.databaseHandle;
          const isCapabilityDetail = !!tab.capabilityDetail;
          const isBrowser = !!tab.url;
          const isRuntime = !!tab.runtime;
          const TabIcon = isSubagent
            ? Bot
            : isTerminal
              ? Terminal
              : isDatabase
                ? Database
                : isCapabilityDetail
                  ? Eye
                  : isBrowser
                    ? Globe
                    : isRuntime
                      ? FlaskConical
                      : getTabIcon(tab.file?.type ?? "unknown");
          const tabTitle = isSubagent
            ? tab.subagentId!.slice(0, 8) + "..."
            : isTerminal
              ? "终端"
              : isDatabase
                ? `查询 ${tab.databaseHandle}`
                : isCapabilityDetail
                  ? tab.capabilityDetail!.displayName
                  : isBrowser
                    ? getBrowserTabTitle(tab.url!)
                    : isRuntime
                      ? "执行环境"
                      : (tab.file?.name ?? "");
          return (
            <div key={tab.id} className="flex items-center">
              {showInsertBefore ? (
                <div className="mx-0.5 h-5 w-0.5 shrink-0 rounded-full bg-primary" />
              ) : null}
              <div
                draggable
                onDragStart={(e) => handleTabDragStart(e, tab, index)}
                onDragEnd={handleTabDragEnd}
                onContextMenu={(e) => handleContextMenu(e, tab.id)}
                className={cn(
                  "group flex max-w-[220px] shrink-0 items-center gap-1.5 rounded-md border px-3.5 py-1.5 text-xs font-medium transition-all duration-200 ease-in-out",
                  isActive
                    ? "border-black/5 bg-background text-foreground shadow-sm"
                    : "border-transparent bg-transparent text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                  isDragging && "opacity-40",
                )}
                title={tabTitle}
              >
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
                  onClick={() => onTabClick(tab.id)}
                >
                  <TabIcon className="h-3.5 w-3.5 shrink-0" />
                  <span className={cn("truncate", !isBrowser && "font-mono")}>
                  {isSubagent || isTerminal || isDatabase || isCapabilityDetail || isBrowser || isRuntime
                    ? tabTitle
                    : getFileBaseName(tab.file!.name)}
                  </span>
                  {isDirty ? (
                    <span className="ml-0.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warning" />
                  ) : null}
                </button>
                <button
                  type="button"
                  className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground opacity-0 transition-all duration-200 ease-in-out hover:bg-muted hover:text-foreground group-hover:opacity-100"
                  title="关闭标签"
                  onClick={(event) => {
                    event.stopPropagation();
                    onTabClose(tab.id);
                  }}
                >
                  <X className="h-3 w-3" />
                </button>
              </div>
            </div>
          );
        })}
        {dragOverIndex === tabs.length && draggingIndex !== tabs.length ? (
          <div className="mx-0.5 h-5 w-0.5 shrink-0 rounded-full bg-primary" />
        ) : null}
      </div>

      {/* 右侧操作区 */}
      <div className="flex shrink-0 items-center gap-0.5 border-l border-border pl-1.5">
        {onNewTab || onNewBrowserTab || onNewTerminalTab ? (
          <div className="relative">
            <button
              type="button"
              className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="新建"
              onClick={() => setShowNewTabDropdown((v) => !v)}
            >
              <Plus className="h-3.5 w-3.5" />
            </button>
            {showNewTabDropdown ? (
              <div
                ref={dropdownRef}
                className="absolute right-0 top-full z-50 mt-1 w-40 overflow-hidden rounded-md border border-border bg-background p-1 text-xs text-foreground shadow-lg"
              >
                {onNewBrowserTab ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
                    onClick={() => {
                      setShowNewTabDropdown(false);
                      setShowUrlDialog(true);
                      setUrlInput("");
                    }}
                  >
                    <Globe className="h-3.5 w-3.5 text-muted-foreground" />
                    浏览器视图
                  </button>
                ) : null}
                {onOpenRuntimeTab ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
                    onClick={() => {
                      setShowNewTabDropdown(false);
                      onOpenRuntimeTab();
                    }}
                  >
                    <FlaskConical className="h-3.5 w-3.5 text-muted-foreground" />
                    执行环境
                  </button>
                ) : null}
                {onNewTerminalTab ? (
                  <button
                    type="button"
                    className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
                    onClick={() => {
                      setShowNewTabDropdown(false);
                      onNewTerminalTab();
                    }}
                  >
                    <Terminal className="h-3.5 w-3.5 text-muted-foreground" />
                    终端
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
        ) : null}
        {showActionButtons && onTabSplitRight ? (
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="向右拆分"
            onClick={() => onTabSplitRight(activeTabId!)}
          >
            <Columns2 className="h-3.5 w-3.5" />
          </button>
        ) : null}
        {showActionButtons && onTabSplitDown ? (
          <button
            type="button"
            className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="向下拆分"
            onClick={() => onTabSplitDown(activeTabId!)}
          >
            <Rows2 className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>

      {/* Tab 右键菜单 */}
      {contextMenu.visible && (
        <div
          ref={contextMenuRef}
          className="fixed z-[60] min-w-[160px] overflow-hidden rounded-md border border-border bg-background p-1 text-xs text-foreground shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onPointerDown={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="flex w-full items-center rounded-sm px-2.5 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
            onClick={() => {
              onTabClose(contextMenu.tabId);
              hideContextMenu();
            }}
          >
            关闭
          </button>
          {hasOtherTabs && onTabCloseOthers ? (
            <button
              type="button"
              className="flex w-full items-center rounded-sm px-2.5 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                onTabCloseOthers(contextMenu.tabId);
                hideContextMenu();
              }}
            >
              关闭其他
            </button>
          ) : null}
          {hasRightTabs && onTabCloseRight ? (
            <button
              type="button"
              className="flex w-full items-center rounded-sm px-2.5 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                onTabCloseRight(contextMenu.tabId);
                hideContextMenu();
              }}
            >
              关闭右侧
            </button>
          ) : null}
          <div className="my-1 h-px bg-border" />
          {onTabCloseAll ? (
            <button
              type="button"
              className="flex w-full items-center rounded-sm px-2.5 py-1.5 text-left transition-colors hover:bg-accent hover:text-accent-foreground"
              onClick={() => {
                onTabCloseAll();
                hideContextMenu();
              }}
            >
              关闭全部
            </button>
          ) : null}
        </div>
      )}

      {/* URL 输入对话框 */}
      {showUrlDialog ? (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/50">
          <div className="w-[420px] rounded-xl border border-border bg-background p-5 shadow-xl">
            <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              <Globe className="h-4 w-4 text-accent" />
              新建浏览器视图
            </h3>
            <input
              type="text"
              className="mb-4 w-full rounded-md border border-border bg-muted/50 px-3 py-2 text-xs font-mono text-foreground outline-none transition-colors focus:border-accent"
              placeholder="https://example.com 或 reports/dashboard.html"
              value={urlInput}
              onChange={(e) => setUrlInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && urlInput.trim()) {
                  onNewBrowserTab?.(urlInput.trim());
                  setShowUrlDialog(false);
                  setUrlInput("");
                }
                if (e.key === "Escape") {
                  setShowUrlDialog(false);
                  setUrlInput("");
                }
              }}
              autoFocus
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                className="rounded-md px-3 py-1.5 text-xs transition-colors hover:bg-muted"
                onClick={() => {
                  setShowUrlDialog(false);
                  setUrlInput("");
                }}
              >
                取消
              </button>
              <button
                type="button"
                className="rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground transition-colors hover:bg-primary/90 disabled:bg-muted disabled:text-muted-foreground disabled:opacity-100"
                disabled={!urlInput.trim()}
                onClick={() => {
                  if (urlInput.trim()) {
                    onNewBrowserTab?.(urlInput.trim());
                    setShowUrlDialog(false);
                    setUrlInput("");
                  }
                }}
              >
                打开
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default WorkspaceTabBar;
