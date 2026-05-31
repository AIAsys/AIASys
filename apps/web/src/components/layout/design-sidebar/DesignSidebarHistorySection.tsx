import {
  Check,
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
import { useState, lazy, Suspense } from "react";
import type { TaskWorkspaceSummary } from "@/pages/DataAnalysisPage/types";
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

  const hasSearchQuery = searchQuery.trim().length > 0;
  const displayedWorkspaces = hasSearchQuery ? filteredWorkspaces : workspaces;
  const shouldShowWorkspaceLoadingState =
    isLoadingHistory &&
    workspaces.length === 0 &&
    !hasSearchQuery;
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
    const title = workspaceTitleDraft.trim() || "未命名工作区";
    const description = workspaceDescriptionDraft.trim();
    setSavingWorkspaceId(workspace.workspace_id);
    try {
      await onUpdateWorkspace?.(workspace.workspace_id, {
        title,
        description: description || null,
      });
      cancelWorkspaceEdit();
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

  const toggleSelectAll = () => {
    if (selectedIds.size === displayedWorkspaces.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(displayedWorkspaces.map((w) => w.workspace_id)));
    }
  };

  const exitMultiSelectMode = () => {
    setIsMultiSelectMode(false);
    setSelectedIds(new Set());
  };

  const handleDeleteSelected = () => {
    if (selectedIds.size === 0) return;
    onDeleteSelectedWorkspaces?.(Array.from(selectedIds));
    exitMultiSelectMode();
  };

  return (
    <div className="px-4 flex-1 overflow-y-auto">
      {isMultiSelectMode ? (
        <div className="flex items-center justify-end mb-3 gap-2">
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
            {selectedIds.size === displayedWorkspaces.length ? "全不选" : "全选"}
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

      <div className="space-y-1 text-foreground">
        {displayedWorkspaces.length > 0 ? (
            displayedWorkspaces.map((workspace) => {
              const isCurrentWorkspace =
                workspace.workspace_id === currentWorkspaceId;
              const isEditing = editingWorkspaceId === workspace.workspace_id;
              const isSaving = savingWorkspaceId === workspace.workspace_id;
              const isSelected = selectedIds.has(workspace.workspace_id);
              return (
                <div
                key={workspace.workspace_id}
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
                        autoFocus
                        className="h-8 w-full rounded-md border border-border bg-background px-2 text-sm font-medium text-foreground outline-none focus:ring-2 focus:ring-ring"
                      />
                      <textarea
                        value={workspaceDescriptionDraft}
                        onChange={(event) =>
                          setWorkspaceDescriptionDraft(event.target.value)
                        }
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
                    <DropdownMenu>
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
                            void onDeleteWorkspace?.(workspace.workspace_id);
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
            );
          })
        ) : shouldShowWorkspaceLoadingState ? (
          <div className="text-muted-foreground text-xs italic py-2">
            正在加载工作区...
          </div>
        ) : null}

        {displayedWorkspaces.length > 0 ? null : hasSearchQuery ? (
          <div className="text-muted-foreground text-xs italic py-2">
            未找到匹配的工作区
          </div>
        ) : isLoadingHistory ? null : (
          <div className="text-muted-foreground text-xs italic py-2">
            暂无工作区
          </div>
        )}
      </div>

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
    </div>
  );
}
