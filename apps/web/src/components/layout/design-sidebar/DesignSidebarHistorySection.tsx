import {
  Check,
  Download,
  FolderOpen,
  History,
  Loader2,
  MoreHorizontal,
  Pencil,
  Search,
  Trash2,
  X,
  LayoutTemplate,
} from "lucide-react";
import { useState, lazy, Suspense, useRef, useEffect, useMemo } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
const LazySaveWorkspaceAsTemplateDialog = lazy(() =>
  import("@/components/SaveWorkspaceAsTemplateDialog").then((module) => ({
    default: module.SaveWorkspaceAsTemplateDialog,
  })),
);
const LazyExportWorkspaceDialog = lazy(() =>
  import("@/components/ExportWorkspaceDialog").then((module) => ({
    default: module.ExportWorkspaceDialog,
  })),
);

interface DesignSidebarHistorySectionProps {
  workspaces?: TaskWorkspaceSummary[];
  filteredWorkspaces?: TaskWorkspaceSummary[];
  currentWorkspaceId?: string;
  isLoadingHistory: boolean;
  searchQuery: string;
  onSearchQueryChange: (value: string) => void;
  onClearSearch: () => void;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onDeleteWorkspace?: (workspaceId: string) => void | Promise<void>;
  onDeleteAllWorkspaces?: () => void;
  onDeleteSelectedWorkspaces?: (ids: string[]) => void;
  onExportWorkspace?: (workspaceId: string) => void | Promise<void>;
  onUpdateWorkspace?: (
    workspaceId: string,
    patch: { title?: string; description?: string | null },
  ) => Promise<void> | void;
}

export function DesignSidebarHistorySection({
  workspaces = [],
  filteredWorkspaces = [],
  currentWorkspaceId,
  isLoadingHistory,
  searchQuery,
  onSearchQueryChange,
  onClearSearch,
  onWorkspaceSelect,
  onDeleteWorkspace,
  onDeleteSelectedWorkspaces,
  onUpdateWorkspace,
}: DesignSidebarHistorySectionProps) {
  const [editingWorkspaceId, setEditingWorkspaceId] = useState<string | null>(
    null,
  );
  const [workspaceTitleDraft, setWorkspaceTitleDraft] = useState("");
  const [workspaceDescriptionDraft, setWorkspaceDescriptionDraft] = useState("");
  const [savingWorkspaceId, setSavingWorkspaceId] = useState<string | null>(null);
  const [isMultiSelectMode, setIsMultiSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [exportingWorkspaceId, setExportingWorkspaceId] = useState<string | null>(null);
  const [dialogExportWorkspaceId, setDialogExportWorkspaceId] = useState<string | null>(null);
  const [openDropdownId, setOpenDropdownId] = useState<string | null>(null);

  const hasSearchQuery = searchQuery.trim().length > 0;
  // 用 useMemo 稳定引用，避免 effect 不必要的重触发
  const displayedWorkspaces = useMemo(
    () => (hasSearchQuery ? filteredWorkspaces : workspaces),
    [hasSearchQuery, filteredWorkspaces, workspaces],
  );
  const shouldShowWorkspaceLoadingState =
    isLoadingHistory &&
    workspaces.length === 0 &&
    !hasSearchQuery;

  const listContainerRef = useRef<HTMLDivElement>(null);

  const virtualizer = useVirtualizer({
    count: displayedWorkspaces.length,
    getScrollElement: () => listContainerRef.current,
    estimateSize: () => 64,
    measureElement: (element) => element.getBoundingClientRect().height,
    overscan: 5,
  });

  // Bug 1: 避免 autoFocus 在虚拟滚动项重新挂载时反复触发
  useEffect(() => {
    if (!editingWorkspaceId || !listContainerRef.current) return;
    const input = listContainerRef.current.querySelector(
      '[data-edit-input]',
    ) as HTMLInputElement | null;
    input?.focus();
  }, [editingWorkspaceId]);

  // Bug 2: 搜索条件变化时，清理不在当前过滤结果中的选中项
  useEffect(() => {
    if (!isMultiSelectMode) return;
    setSelectedIds((prev) => {
      const visibleIds = new Set(
        displayedWorkspaces.map((w) => w.workspace_id),
      );
      const next = new Set<string>();
      prev.forEach((id) => {
        if (visibleIds.has(id)) next.add(id);
      });
      return next;
    });
  }, [searchQuery, isMultiSelectMode, displayedWorkspaces]);

  // 编辑项自动滚动到视口，确保编辑 UI 可见
  useEffect(() => {
    if (!editingWorkspaceId) return;
    const index = displayedWorkspaces.findIndex(
      (w) => w.workspace_id === editingWorkspaceId,
    );
    if (index >= 0) {
      const virtualItems = virtualizer.getVirtualItems();
      const isVisible = virtualItems.some(
        (item) => displayedWorkspaces[item.index]?.workspace_id === editingWorkspaceId,
      );
      if (!isVisible) {
        virtualizer.scrollToIndex(index, { align: 'start' });
      }
    }
  }, [editingWorkspaceId, displayedWorkspaces, virtualizer]);

  // Bug 4: 编辑状态变化时，手动触发对应项的重新测量
  useEffect(() => {
    if (!listContainerRef.current) return;
    const editedIndex = displayedWorkspaces.findIndex(
      (w) => w.workspace_id === editingWorkspaceId,
    );
    if (editedIndex >= 0) {
      const el = listContainerRef.current.querySelector(
        `[data-index="${editedIndex}"]`,
      );
      if (el) {
        virtualizer.measureElement(el as HTMLElement);
      }
    }
  }, [editingWorkspaceId, displayedWorkspaces, virtualizer]);

  // Fix 1: 虚拟滚动时关闭 DropdownMenu，防止 portal 漂
  const prevScrollContainerRef = useRef<HTMLDivElement | null>(null);
  const scrollHandlerRef = useRef(() => setOpenDropdownId(null));
  useEffect(() => {
    const container = listContainerRef.current;
    if (container === prevScrollContainerRef.current) return;
    if (prevScrollContainerRef.current) {
      prevScrollContainerRef.current.removeEventListener('scroll', scrollHandlerRef.current);
    }
    if (container) {
      container.addEventListener('scroll', scrollHandlerRef.current);
    }
    prevScrollContainerRef.current = container;
  });

  // Fix 2: 列表长度减少时（删除/搜索过滤），平滑调整滚动位置
  useEffect(() => {
    const container = listContainerRef.current;
    if (!container) return;
    const maxScroll = container.scrollHeight - container.clientHeight;
    if (container.scrollTop > maxScroll && maxScroll > 0) {
      container.scrollTo({ top: maxScroll, behavior: 'smooth' });
    }
  }, [workspaces.length, displayedWorkspaces.length]);

  // Fix 3: 当前工作区变化或首次进入可视列表时，自动滚动到视口
  const lastWorkspaceIdRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    if (!currentWorkspaceId) {
      lastWorkspaceIdRef.current = undefined;
      return;
    }
    const index = displayedWorkspaces.findIndex(
      (w) => w.workspace_id === currentWorkspaceId,
    );
    if (index >= 0) {
      const isNewId = lastWorkspaceIdRef.current !== currentWorkspaceId;
      const wasNotInResults = lastWorkspaceIdRef.current === undefined;
      if (isNewId || wasNotInResults) {
        const virtualItems = virtualizer.getVirtualItems();
        const isVisible = virtualItems.some(
          (item) => displayedWorkspaces[item.index]?.workspace_id === currentWorkspaceId,
        );
        if (!isVisible) {
          virtualizer.scrollToIndex(index, { align: 'start' });
        }
      }
    }
    lastWorkspaceIdRef.current = currentWorkspaceId;
  }, [currentWorkspaceId, displayedWorkspaces, virtualizer]);

  // Fix 4: workspaces 变化时，清理已不存在的选中项
  useEffect(() => {
    if (!isMultiSelectMode) return;
    const validIds = new Set(workspaces.map((w) => w.workspace_id));
    setSelectedIds((prev) => {
      const next = new Set<string>();
      prev.forEach((id) => {
        if (validIds.has(id)) next.add(id);
      });
      return next;
    });
  }, [workspaces, isMultiSelectMode]);

  const startWorkspaceEdit = (workspace: TaskWorkspaceSummary) => {
    setEditingWorkspaceId(workspace.workspace_id);
    setWorkspaceTitleDraft(workspace.title || "");
    setWorkspaceDescriptionDraft(workspace.description || "");
  };

  const cancelWorkspaceEdit = () => {
    setEditingWorkspaceId(null);
    setWorkspaceTitleDraft("");
    setWorkspaceDescriptionDraft("");
  };

  const saveWorkspaceEdit = async (workspace: TaskWorkspaceSummary) => {
    // 立即捕获当前草稿值，避免异步期间被其他编辑操作覆盖
    const title = workspaceTitleDraft.trim() || "未命名工作区";
    const description = workspaceDescriptionDraft.trim();
    setSavingWorkspaceId(workspace.workspace_id);
    try {
      await onUpdateWorkspace?.(workspace.workspace_id, {
        title,
        description: description || null,
      });
      cancelWorkspaceEdit();
    } catch (err) {
      console.error("Failed to update workspace:", err);
    } finally {
      setSavingWorkspaceId(null);
    }
  };

  const toggleSelection = (workspaceId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(workspaceId)) {
        next.delete(workspaceId);
      } else {
        next.add(workspaceId);
      }
      return next;
    });
  };

  const isAllFilteredSelected =
    displayedWorkspaces.length > 0 &&
    displayedWorkspaces.every((w) => selectedIds.has(w.workspace_id));
  const isAllSelected =
    workspaces.length > 0 &&
    workspaces.every((w) => selectedIds.has(w.workspace_id));
  const canExpandToAll = workspaces.length > displayedWorkspaces.length;

  const toggleSelectAll = () => {
    if (isAllSelected || isAllFilteredSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(displayedWorkspaces.map((w) => w.workspace_id)));
    }
  };

  const expandSelectToAll = () => {
    setSelectedIds(new Set(workspaces.map((w) => w.workspace_id)));
  };

  const exitMultiSelectMode = () => {
    setIsMultiSelectMode(false);
    setSelectedIds(new Set());
  };

  const handleDeleteSelected = () => {
    if (selectedIds.size === 0) return;
    void (async () => {
      try {
        await onDeleteSelectedWorkspaces?.(Array.from(selectedIds));
      } catch (error) {
        console.error("Failed to delete selected workspaces:", error);
      } finally {
        exitMultiSelectMode();
      }
    })();
  };

  return (
    <div className="px-4 flex-1 flex flex-col overflow-hidden">
      {isMultiSelectMode ? (
        <>
          <div className="flex items-center justify-end mb-2 gap-2">
            <button
              type="button"
              onClick={exitMultiSelectMode}
              className="shrink-0 text-xs text-muted-foreground hover:text-foreground transition-colors px-1 py-0.5 rounded whitespace-nowrap"
            >
              取消
            </button>
            <button
              type="button"
              onClick={toggleSelectAll}
              className="shrink-0 text-xs text-muted-foreground hover:text-foreground transition-colors px-1 py-0.5 rounded whitespace-nowrap"
            >
              {isAllSelected || isAllFilteredSelected ? "全不选" : "全选"}
            </button>
            <button
              type="button"
              onClick={handleDeleteSelected}
              disabled={selectedIds.size === 0}
              className="shrink-0 text-xs text-error hover:text-error/80 transition-colors disabled:opacity-40 disabled:cursor-not-allowed px-1 py-0.5 rounded flex items-center gap-1 whitespace-nowrap"
            >
              <Trash2 className="w-3 h-3" />
              删除{selectedIds.size > 0 ? `(${selectedIds.size})` : ""}
            </button>
          </div>
          {isAllFilteredSelected && canExpandToAll && !isAllSelected && (
            <div className="mb-2 text-right text-xs text-muted-foreground">
              已选 {selectedIds.size} 个匹配项，
              <button
                type="button"
                onClick={expandSelectToAll}
                className="underline hover:text-foreground transition-colors"
              >
                全选全部 {workspaces.length} 个工作区
              </button>
            </div>
          )}
        </>
      ) : (
        <div className="flex items-center justify-between mb-3 text-muted-foreground font-medium">
          <span className="text-xs">
            工作区
          </span>
          <div className="flex items-center gap-2">
            {workspaces.length > 0 && onDeleteSelectedWorkspaces ? (
              <button
                type="button"
                onClick={() => setIsMultiSelectMode(true)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors flex items-center gap-1"
                title="多选工作区"
              >
                <Check className="w-3 h-3" />
                多选
              </button>
            ) : null}
            <History className="w-4 h-4" />
          </div>
        </div>
      )}

      <div className="mb-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            type="text"
            placeholder="搜索工作区..."
            value={searchQuery}
            onChange={(event) => onSearchQueryChange(event.target.value)}
            className="w-full pl-9 pr-8 py-2 text-sm bg-background rounded-lg border border-border focus:outline-none focus:ring-2 focus:ring-ring focus:border-transparent"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={onClearSearch}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {displayedWorkspaces.length > 0 ? (
        <div ref={listContainerRef} className="flex-1 overflow-y-auto min-h-0">
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              position: "relative",
            }}
          >
            {virtualizer.getVirtualItems().map((virtualItem) => {
              const workspace = displayedWorkspaces[virtualItem.index];
              if (!workspace) return null;
              const isCurrentWorkspace =
                workspace.workspace_id === currentWorkspaceId;
              const isEditing = editingWorkspaceId === workspace.workspace_id;
              const isSaving = savingWorkspaceId === workspace.workspace_id;
              const isSelected = selectedIds.has(workspace.workspace_id);
              return (
                <div
                  key={workspace.workspace_id}
                  data-index={virtualItem.index}
                  ref={virtualizer.measureElement}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${virtualItem.start}px)`,
                  }}
                  className="pb-1"
                >
                  <div
                    className={`group rounded-xl border text-sm transition-colors ${
                      isCurrentWorkspace
                        ? "border-border bg-background shadow-sm"
                        : "border-transparent hover:border-border/60 hover:bg-sidebar-accent/30"
                    } ${isMultiSelectMode && isSelected ? "bg-sidebar-accent/40 border-border/40" : ""}`}
                  >
                    <div className="flex items-start gap-1 px-2 py-2">
                      {isMultiSelectMode && !isEditing ? (
                        <div className="pt-0.5 flex-shrink-0">
                          <Checkbox
                            checked={isSelected}
                            onCheckedChange={() => toggleSelection(workspace.workspace_id)}
                          />
                        </div>
                      ) : null}
                      {isEditing ? (
                        <div
                          className="min-w-0 flex-1 space-y-2"
                          onClick={(event) => event.stopPropagation()}
                        >
                          <input
                            data-edit-input
                            value={workspaceTitleDraft}
                            onChange={(event) =>
                              setWorkspaceTitleDraft(event.target.value)
                            }
                            onKeyDown={(event) => {
                              if (event.key === "Enter" && !event.shiftKey) {
                                event.preventDefault();
                                void saveWorkspaceEdit(workspace);
                              }
                              if (event.key === "Escape") {
                                cancelWorkspaceEdit();
                              }
                            }}
                            className="h-8 w-full rounded-md border border-border bg-background px-2 text-sm font-medium text-foreground outline-none focus:ring-2 focus:ring-ring"
                          />
                          <textarea
                            value={workspaceDescriptionDraft}
                            onChange={(event) =>
                              setWorkspaceDescriptionDraft(event.target.value)
                            }
                            onKeyDown={(event) => {
                              if (event.key === "Escape") {
                                cancelWorkspaceEdit();
                              }
                            }}
                            rows={2}
                            placeholder="补充工作区描述"
                            className="w-full resize-none rounded-md border border-border bg-background px-2 py-1.5 text-xs leading-5 text-foreground outline-none focus:ring-2 focus:ring-ring"
                          />
                          <div className="flex justify-end gap-1">
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              disabled={isSaving}
                              onClick={cancelWorkspaceEdit}
                            >
                              取消
                            </Button>
                            <Button
                              type="button"
                              size="sm"
                              className="h-7 px-2 text-xs"
                              disabled={isSaving}
                              onClick={() => void saveWorkspaceEdit(workspace)}
                            >
                              {isSaving ? (
                                <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                              ) : (
                                <Check className="mr-1 h-3.5 w-3.5" />
                              )}
                              保存
                            </Button>
                          </div>
                        </div>
                      ) : (
                        <button
                          type="button"
                          onClick={() => {
                            if (isMultiSelectMode) {
                              toggleSelection(workspace.workspace_id);
                            } else {
                              onWorkspaceSelect?.(workspace.workspace_id);
                            }
                          }}
                          onDoubleClick={isMultiSelectMode ? undefined : () => startWorkspaceEdit(workspace)}
                          className="flex min-w-0 flex-1 items-start gap-2 text-left"
                        >
                          {!isMultiSelectMode && (
                            <FolderOpen className="mt-0.5 h-4 w-4 flex-shrink-0 text-tertiary" />
                          )}
                          <div className="flex-1 min-w-0 text-left">
                            <div
                              className="truncate font-medium"
                              title={workspace.title}
                            >
                              {workspace.title || "未命名工作区"}
                            </div>
                            {workspace.description ? (
                              <div
                                className="mt-0.5 line-clamp-2 text-[11px] leading-4 text-muted-foreground"
                                title={workspace.description}
                              >
                                {workspace.description}
                              </div>
                            ) : null}
                          </div>
                        </button>
                      )}
                      {!isMultiSelectMode && (
                        <DropdownMenu
                          open={openDropdownId === workspace.workspace_id}
                          onOpenChange={(open) =>
                            setOpenDropdownId(open ? workspace.workspace_id : null)
                          }
                        >
                          <DropdownMenuTrigger asChild>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="mr-1 h-8 w-8 p-0 opacity-0 transition-opacity group-hover:opacity-100"
                              onClick={(event) => event.stopPropagation()}
                              title="更多操作"
                            >
                              <MoreHorizontal className="h-4 w-4" />
                              <span className="sr-only">更多操作</span>
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-48">
                            <DropdownMenuItem
                              onClick={(event) => {
                                event.stopPropagation();
                                startWorkspaceEdit(workspace);
                              }}
                            >
                              <Pencil className="mr-2 h-4 w-4" />
                              <span>编辑名称和描述</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(event) => {
                                event.stopPropagation();
                                setExportingWorkspaceId(workspace.workspace_id);
                              }}
                            >
                              <LayoutTemplate className="mr-2 h-4 w-4" />
                              <span>保存为模板</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(event) => {
                                event.stopPropagation();
                                setDialogExportWorkspaceId(workspace.workspace_id);
                              }}
                            >
                              <Download className="mr-2 h-4 w-4" />
                              <span>导出工作区</span>
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              onClick={(event) => {
                                event.stopPropagation();
                                void (async () => {
                                  try {
                                    await onDeleteWorkspace?.(workspace.workspace_id);
                                  } catch (err) {
                                    console.error("Failed to delete workspace:", err);
                                  }
                                })();
                              }}
                              className="text-error focus:text-error"
                            >
                              <Trash2 className="mr-2 h-4 w-4" />
                              <span>删除工作区</span>
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto">
          {shouldShowWorkspaceLoadingState ? (
            <div className="text-muted-foreground text-xs italic py-2">
              正在加载工作区...
            </div>
          ) : hasSearchQuery ? (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Search className="h-8 w-8 text-muted-foreground/40 mb-2" />
              <div className="text-sm text-muted-foreground">
                未找到匹配的工作区
              </div>
              <div className="text-xs text-muted-foreground/70 mt-1">
                尝试其他关键词或清除搜索
              </div>
              <button
                type="button"
                onClick={onClearSearch}
                className="mt-3 text-xs text-primary hover:text-primary/80 transition-colors"
              >
                清除搜索
              </button>
            </div>
          ) : isLoadingHistory ? null : (
            <div className="text-muted-foreground text-xs italic py-2">
              暂无工作区
            </div>
          )}
        </div>
      )}

      {exportingWorkspaceId && (
        <Suspense fallback={null}>
          <LazySaveWorkspaceAsTemplateDialog
            workspaceId={exportingWorkspaceId}
            workspaceTitle={
              workspaces.find((w) => w.workspace_id === exportingWorkspaceId)?.title || ""
            }
            isOpen={Boolean(exportingWorkspaceId)}
            onClose={() => setExportingWorkspaceId(null)}
          />
        </Suspense>
      )}

      {dialogExportWorkspaceId && (
        <Suspense fallback={null}>
          <LazyExportWorkspaceDialog
            workspaceId={dialogExportWorkspaceId}
            workspaceTitle={
              workspaces.find((w) => w.workspace_id === dialogExportWorkspaceId)?.title || ""
            }
            isOpen={Boolean(dialogExportWorkspaceId)}
            onClose={() => setDialogExportWorkspaceId(null)}
          />
        </Suspense>
      )}
    </div>
  );
}
