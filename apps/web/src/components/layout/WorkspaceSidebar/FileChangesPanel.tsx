import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  FolderClosed,
  FolderOpen,
  GitBranch,
  History,
  List,
  ListTree,
  Loader2,
  RefreshCw,
  RotateCcw,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { DiffViewer } from "@/components/diff/DiffViewer";
import {
  type RecentChangeItem,
  type FileChangesScope,
  listRecentChanges,
} from "@/lib/api/fileChanges";
import {
  getFileHistoryDiff,
  type FileHistoryDiffResponse,
  restoreFileHistoryEntry,
} from "@/lib/api/fileHistory";
import type { WorkspaceFile } from "@/types/task";
import {
  FileHistoryDialog,
} from "@/components/layout/WorkspaceSidebar/FileHistoryDialog";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

type ViewMode = "list" | "tree";

const OPERATION_ICONS: Record<string, React.ReactNode> = {
  before_update: <GitBranch className="h-3.5 w-3.5 text-warning" />,
  before_overwrite: <GitBranch className="h-3.5 w-3.5 text-info" />,
  before_delete: <GitBranch className="h-3.5 w-3.5 text-error" />,
  before_move: <GitBranch className="h-3.5 w-3.5 text-tertiary" />,
  before_restore: <GitBranch className="h-3.5 w-3.5 text-success" />,
};

const OPERATION_LABELS: Record<string, string> = {
  before_update: "修改",
  before_overwrite: "覆盖",
  before_delete: "删除",
  before_move: "移动",
  before_restore: "恢复",
};

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

interface TreeNode {
  name: string;
  path: string;
  children: Map<string, TreeNode>;
  item?: RecentChangeItem;
}

function buildTree(items: RecentChangeItem[]): TreeNode {
  const root: TreeNode = { name: "", path: "", children: new Map() };
  for (const item of items) {
    const parts = item.file_path.split("/");
    let current = root;
    for (let i = 0; i < parts.length; i++) {
      const part = parts[i];
      const isLast = i === parts.length - 1;
      if (!current.children.has(part)) {
        current.children.set(part, {
          name: part,
          path: parts.slice(0, i + 1).join("/"),
          children: new Map(),
          item: isLast ? item : undefined,
        });
      }
      const child = current.children.get(part)!;
      if (isLast) {
        child.item = item;
      }
      current = child;
    }
  }
  return root;
}

interface FileChangesPanelProps {
  workspaceId: string | null;
  scope?: FileChangesScope;
  headers?: HeadersInit;
}

export function FileChangesPanel({
  workspaceId,
  scope = "workspace",
  headers,
}: FileChangesPanelProps) {
  const [items, setItems] = useState<RecentChangeItem[]>([]);
  const [viewMode, setViewMode] = useState<ViewMode>("list");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set());
  const [selectedFilePath, setSelectedFilePath] = useState<string | null>(null);
  const [diffDetail, setDiffDetail] = useState<FileHistoryDiffResponse | null>(null);
  const [isLoadingDiff, setIsLoadingDiff] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [historyDialogOpen, setHistoryDialogOpen] = useState(false);
  const [historyDialogFile, setHistoryDialogFile] = useState<WorkspaceFile | null>(null);
  const [restoreConfirmOpen, setRestoreConfirmOpen] = useState(false);
  const requestIdRef = useRef(0);

  const loadData = useCallback(async () => {
    if (!workspaceId) return;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    setIsLoading(true);
    setError(null);
    try {
      const response = await listRecentChanges(scope, workspaceId, 50);
      if (requestIdRef.current !== requestId) return;
      setItems(response.files);
      setSelectedFilePath(null);
      setDiffDetail(null);
      setDiffError(null);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setItems([]);
      setError(err instanceof Error ? err.message : "加载文件变更失败");
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, [workspaceId, scope]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const tree = useMemo(() => buildTree(items), [items]);

  const selectedItem = useMemo(
    () => items.find((item) => item.file_path === selectedFilePath) ?? null,
    [items, selectedFilePath],
  );

  const loadDiff = useCallback(
    async () => {
      if (!workspaceId || !selectedItem) return;
      setIsLoadingDiff(true);
      setDiffError(null);
      try {
        const response = await getFileHistoryDiff(
          scope,
          workspaceId,
          selectedItem.latest_entry.id,
          { headers },
        );
        setDiffDetail(response);
      } catch (err) {
        setDiffError(err instanceof Error ? err.message : "加载差异失败");
      } finally {
        setIsLoadingDiff(false);
      }
    },
    [workspaceId, scope, selectedItem, headers],
  );

  useEffect(() => {
    if (selectedFilePath && selectedItem) {
      void loadDiff();
    }
  }, [selectedFilePath, selectedItem, loadDiff]);

  const toggleDir = useCallback((path: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  const handleSelectFile = useCallback(
    (item: RecentChangeItem) => {
      if (selectedFilePath === item.file_path) {
        setSelectedFilePath(null);
        setDiffDetail(null);
      } else {
        setSelectedFilePath(item.file_path);
      }
    },
    [selectedFilePath],
  );

  const handleOpenHistory = useCallback(
    (item: RecentChangeItem) => {
      setHistoryDialogFile({
        name: item.file_path,
        path: item.file_path,
        size: item.latest_entry.size,
        mtime: item.latest_entry.timestamp,
        type: "file",
      } as WorkspaceFile);
      setHistoryDialogOpen(true);
    },
    [],
  );

  const handleRestoreClick = useCallback(() => {
    setRestoreConfirmOpen(true);
  }, []);

  const handleRestore = useCallback(async () => {
    if (!workspaceId || !selectedItem) return;
    setRestoreConfirmOpen(false);
    setIsRestoring(true);
    setDiffError(null);
    try {
      await restoreFileHistoryEntry(scope, workspaceId, selectedItem.latest_entry.id, {
        headers,
      });
      await loadData();
    } catch (err) {
      setDiffError(err instanceof Error ? err.message : "恢复文件失败");
    } finally {
      setIsRestoring(false);
    }
  }, [workspaceId, scope, selectedItem, headers, loadData]);

  const canLoad = Boolean(workspaceId);

  const renderFileRow = (item: RecentChangeItem, depth: number = 0) => {
    const fileName = item.file_path.split("/").pop() || item.file_path;
    const dirPath = item.file_path.includes("/")
      ? item.file_path.substring(0, item.file_path.lastIndexOf("/"))
      : "";
    const isSelected = selectedFilePath === item.file_path;

    return (
      <div key={item.file_path}>
        <button
          type="button"
          className={cn(
            "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors",
            isSelected
              ? "bg-primary/10 text-primary"
              : "text-foreground hover:bg-muted/50",
          )}
          style={{ paddingLeft: `${8 + depth * 16}px` }}
          onClick={() => handleSelectFile(item)}
        >
          <span className="shrink-0">
            {OPERATION_ICONS[item.latest_entry.operation] ?? (
              <GitBranch className="h-3.5 w-3.5 text-muted-foreground" />
            )}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate font-mono text-xs">{fileName}</span>
            {dirPath && (
              <span className="block truncate text-[11px] text-muted-foreground">
                {dirPath}
              </span>
            )}
          </span>
          <span className="shrink-0 text-[11px] text-muted-foreground">
            {formatTime(item.latest_entry.timestamp)}
          </span>
        </button>
      </div>
    );
  };

  const renderTreeNode = (
    treeNode: TreeNode,
    depth: number,
    flatIndex: number,
  ) => {
    const isDir = treeNode.children.size > 0;
    const isExpanded = expandedDirs.has(treeNode.path);

    if (isDir) {
      return (
        <div key={treeNode.path}>
          <button
            type="button"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-foreground hover:bg-muted/50 transition-colors"
            style={{ paddingLeft: `${8 + depth * 16}px` }}
            onClick={() => toggleDir(treeNode.path)}
          >
            <ChevronRight
              className={cn(
                "h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform",
                isExpanded && "rotate-90",
              )}
            />
            {isExpanded ? (
              <FolderOpen className="h-3.5 w-3.5 shrink-0 text-warning" />
            ) : (
              <FolderClosed className="h-3.5 w-3.5 shrink-0 text-warning" />
            )}
            <span className="truncate font-mono text-xs">{treeNode.name}</span>
          </button>
          {isExpanded &&
            Array.from(treeNode.children.values()).map((child) => {
              if (child.children.size > 0) {
                return renderTreeNode(child, depth + 1, flatIndex);
              }
              if (child.item) {
                return renderFileRow(child.item, depth + 1);
              }
              return null;
            })}
        </div>
      );
    }

    if (treeNode.item) {
      return renderFileRow(treeNode.item, depth);
    }

    return null;
  };

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Header */}
      <div className="flex h-11 items-center justify-between border-b border-border px-3">
        <span className="text-xs font-medium text-muted-foreground">
          {isLoading
            ? "加载中"
            : items.length > 0
              ? `${items.length} 个文件有变更`
              : "文件变更"}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant={viewMode === "list" ? "default" : "ghost"}
            size="icon-sm"
            onClick={() => setViewMode("list")}
            aria-label="列表视图"
          >
            <List className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant={viewMode === "tree" ? "default" : "ghost"}
            size="icon-sm"
            onClick={() => setViewMode("tree")}
            aria-label="树形视图"
          >
            <ListTree className="h-3.5 w-3.5" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => void loadData()}
            disabled={!canLoad || isLoading}
            aria-label="刷新文件变更"
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isLoading && "animate-spin")}
            />
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,auto)_minmax(0,1fr)]">
        {/* File list */}
        <ScrollArea className="min-h-0 border-b border-border">
          {!canLoad ? (
            <div className="flex h-32 items-center justify-center px-6 text-sm text-muted-foreground">
              请先打开一个工作区。
            </div>
          ) : error ? (
            <div className="px-3 py-4 text-xs text-error">{error}</div>
          ) : items.length === 0 && !isLoading ? (
            <div className="flex h-32 items-center justify-center px-6 text-center text-xs text-muted-foreground">
              暂无文件变更记录。
            </div>
          ) : viewMode === "list" ? (
            <div className="py-1">
              {items.map((item) => renderFileRow(item))}
            </div>
          ) : (
            <div className="py-1">
              {Array.from(tree.children.values()).map((child) => {
                if (child.children.size > 0) {
                  return renderTreeNode(child, 0, 0);
                }
                if (child.item) {
                  return renderFileRow(child.item, 0);
                }
                return null;
              })}
            </div>
          )}
        </ScrollArea>

        {/* Diff preview */}
        <div className="min-h-0 flex flex-col">
          {selectedItem ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex h-9 items-center justify-between border-b border-border px-3">
                <div className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  <span className="font-mono text-foreground">
                    {selectedItem.file_path.split("/").pop()}
                  </span>
                  <span className="ml-2">
                    {OPERATION_LABELS[selectedItem.latest_entry.operation] ??
                      selectedItem.latest_entry.operation}{" "}
                    · {formatTime(selectedItem.latest_entry.timestamp)}{" "}
                    · {selectedItem.total_versions} 个版本
                  </span>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-7 text-xs text-error hover:bg-error/10 hover:text-error"
                    onClick={() => void handleRestoreClick()}
                    disabled={isRestoring}
                  >
                    {isRestoring ? (
                      <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <RotateCcw className="mr-1 h-3.5 w-3.5" />
                    )}
                    {isRestoring ? "恢复中" : "恢复到此版本"}
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="h-7 text-xs"
                    onClick={() => handleOpenHistory(selectedItem)}
                  >
                    <History className="mr-1 h-3.5 w-3.5" />
                    完整历史
                  </Button>
                </div>
              </div>
              <ScrollArea className="min-h-0 flex-1">
                <div className="p-3">
                  {isLoadingDiff ? (
                    <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      加载差异中
                    </div>
                  ) : diffError ? (
                    <div className="rounded-md border border-error/30 bg-error-container/20 px-3 py-2 text-xs text-error">
                      {diffError}
                    </div>
                  ) : diffDetail ? (
                    <DiffViewer
                      unifiedDiff={diffDetail.diff}
                      leftLabel={diffDetail.left_label ?? `history/${selectedItem.file_path}`}
                      rightLabel={diffDetail.right_label ?? `current/${selectedItem.file_path}`}
                      status={diffDetail.status}
                      canShowContent={diffDetail.can_show_content}
                      skipReason={diffDetail.skip_reason ?? undefined}
                      currentExists={diffDetail.current_exists}
                      emptyMessage="当前内容和历史版本一样"
                      className="border-0"
                    />
                  ) : null}
                </div>
              </ScrollArea>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center px-6 text-center text-xs text-muted-foreground">
              选择一个文件查看差异。
            </div>
          )}
        </div>
      </div>

      {historyDialogFile && (
        <FileHistoryDialog
          open={historyDialogOpen}
          onOpenChange={setHistoryDialogOpen}
          scope={scope}
          workspaceId={workspaceId}
          file={historyDialogFile}
          headers={headers}
          onRestored={() => void loadData()}
        />
      )}

      <AlertDialog open={restoreConfirmOpen} onOpenChange={setRestoreConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>恢复文件</AlertDialogTitle>
            <AlertDialogDescription>
              {selectedItem
                ? `确认把 ${selectedItem.file_path.split("/").pop() || selectedItem.file_path} 恢复到 ${formatTime(selectedItem.latest_entry.timestamp)} 的内容吗？`
                : "确认恢复当前文件吗？"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isRestoring}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleRestore()}
              disabled={isRestoring}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isRestoring && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              恢复
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}