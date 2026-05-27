import {
  getFileHistoryContent,
  getFileHistoryDiff,
  listFileHistory,
  restoreFileHistoryEntry,
  type FileHistoryEntry,
  type FileHistoryDiffResponse,
  type FileHistoryScope,
} from "@/lib/api/fileHistory";
import { cn } from "@/lib/utils";
import type { WorkspaceFile } from "@/types/task";
import { DiffViewer } from "@/components/diff/DiffViewer";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  FileText,
  GitCompare,
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

interface FileHistoryDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  scope: FileHistoryScope;
  workspaceId?: string | null;
  file: WorkspaceFile | null;
  headers?: HeadersInit;
  onRestored?: () => Promise<void> | void;
}

type HistoryViewMode = "diff" | "content";

const OPERATION_LABELS: Record<string, string> = {
  before_update: "保存前",
  before_overwrite: "覆盖前",
  before_delete: "删除前",
  before_move: "移动前",
  before_restore: "恢复前",
};

function formatEntryTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function operationLabel(operation: string) {
  return OPERATION_LABELS[operation] ?? operation;
}

export function FileHistoryDialog({
  open,
  onOpenChange,
  scope,
  workspaceId,
  file,
  headers,
  onRestored,
}: FileHistoryDialogProps) {
  const [entries, setEntries] = useState<FileHistoryEntry[]>([]);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<HistoryViewMode>("diff");
  const [diffDetail, setDiffDetail] = useState<FileHistoryDiffResponse | null>(null);
  const [contentText, setContentText] = useState("");
  const [isLoadingEntries, setIsLoadingEntries] = useState(false);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [restoreConfirmOpen, setRestoreConfirmOpen] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const listRequestIdRef = useRef(0);
  const detailRequestIdRef = useRef(0);

  const selectedEntry = useMemo(
    () => entries.find((entry) => entry.id === selectedEntryId) ?? null,
    [entries, selectedEntryId],
  );

  const fileName = file?.name ?? "";
  const canLoad = Boolean(open && workspaceId && fileName);

  const loadEntries = useCallback(async () => {
    if (!workspaceId || !fileName) return;
    const requestId = listRequestIdRef.current + 1;
    listRequestIdRef.current = requestId;
    setIsLoadingEntries(true);
    setListError(null);
    try {
      const response = await listFileHistory(scope, workspaceId, fileName, {
        headers,
      });
      if (listRequestIdRef.current !== requestId) return;
      setEntries(response.entries);
      setSelectedEntryId((current) => {
        if (current && response.entries.some((entry) => entry.id === current)) {
          return current;
        }
        return response.entries[0]?.id ?? null;
      });
    } catch (error) {
      if (listRequestIdRef.current !== requestId) return;
      setEntries([]);
      setSelectedEntryId(null);
      setListError(error instanceof Error ? error.message : "加载文件历史失败");
    } finally {
      if (listRequestIdRef.current === requestId) {
        setIsLoadingEntries(false);
      }
    }
  }, [fileName, headers, scope, workspaceId]);

  useEffect(() => {
    if (!canLoad) {
      setEntries([]);
      setSelectedEntryId(null);
      setListError(null);
      return;
    }
    void loadEntries();
  }, [canLoad, loadEntries]);

  useEffect(() => {
    if (!open) {
      setViewMode("diff");
      setDiffDetail(null);
      setContentText("");
      setDetailError(null);
    }
  }, [open]);

  useEffect(() => {
    if (!workspaceId || !selectedEntryId) {
      setDiffDetail(null);
      setContentText("");
      setDetailError(null);
      return;
    }
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    setIsLoadingDetail(true);
    setDetailError(null);

    const loadDetail = async () => {
      try {
        if (viewMode === "diff") {
          const response = await getFileHistoryDiff(scope, workspaceId, selectedEntryId, {
            headers,
          });
          if (detailRequestIdRef.current !== requestId) return;
          setDiffDetail(response);
          return;
        }
        const response = await getFileHistoryContent(scope, workspaceId, selectedEntryId, {
          headers,
        });
        if (detailRequestIdRef.current !== requestId) return;
        setContentText(response.content);
      } catch (error) {
        if (detailRequestIdRef.current !== requestId) return;
        setDetailError(error instanceof Error ? error.message : "加载历史内容失败");
      } finally {
        if (detailRequestIdRef.current === requestId) {
          setIsLoadingDetail(false);
        }
      }
    };

    void loadDetail();
  }, [headers, scope, selectedEntryId, viewMode, workspaceId]);

  const handleRestoreClick = useCallback(() => {
    setRestoreConfirmOpen(true);
  }, []);

  const handleRestore = useCallback(async () => {
    if (!workspaceId || !selectedEntry) return;
    setRestoreConfirmOpen(false);
    setIsRestoring(true);
    setDetailError(null);
    try {
      await restoreFileHistoryEntry(scope, workspaceId, selectedEntry.id, {
        headers,
      });
      await onRestored?.();
      await loadEntries();
      setViewMode("diff");
    } catch (error) {
      setDetailError(error instanceof Error ? error.message : "恢复文件失败");
    } finally {
      setIsRestoring(false);
    }
  }, [fileName, headers, loadEntries, onRestored, scope, selectedEntry, workspaceId]);

  return (
    <>
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[86vh] max-h-[720px] max-w-5xl grid-rows-none flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b border-border px-5 py-4">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <DialogTitle className="truncate text-base">文件历史</DialogTitle>
          </div>
          <DialogDescription className="truncate font-mono text-xs">
            {fileName || "未选择文件"}
          </DialogDescription>
        </DialogHeader>

        <div className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)]">
          <aside className="flex min-h-0 flex-col border-r border-border bg-muted/20">
            <div className="flex h-11 items-center justify-between border-b border-border px-3">
              <span className="text-xs font-medium text-muted-foreground">
                {isLoadingEntries ? "加载中" : `${entries.length} 条记录`}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="icon-sm"
                onClick={() => void loadEntries()}
                disabled={!workspaceId || !fileName || isLoadingEntries}
                aria-label="刷新文件历史"
              >
                <RefreshCw
                  className={cn("h-3.5 w-3.5", isLoadingEntries && "animate-spin")}
                />
              </Button>
            </div>
            <ScrollArea className="min-h-0 flex-1">
              {listError ? (
                <div className="px-3 py-4 text-xs text-error">{listError}</div>
              ) : entries.length === 0 && !isLoadingEntries ? (
                <div className="px-3 py-4 text-xs text-muted-foreground">
                  暂无历史
                </div>
              ) : (
                <div className="p-2">
                  {entries.map((entry) => (
                    <button
                      key={entry.id}
                      type="button"
                      className={cn(
                        "mb-1 flex w-full flex-col gap-1 rounded-md px-2.5 py-2 text-left transition-colors",
                        selectedEntryId === entry.id
                          ? "bg-primary/10 text-primary"
                          : "text-foreground hover:bg-muted",
                      )}
                      onClick={() => setSelectedEntryId(entry.id)}
                    >
                      <span className="flex items-center justify-between gap-2 text-xs font-medium">
                        <span>{operationLabel(entry.operation)}</span>
                        <span className="shrink-0 text-[11px] text-muted-foreground">
                          {formatBytes(entry.size)}
                        </span>
                      </span>
                      <span className="text-[11px] text-muted-foreground">
                        {formatEntryTime(entry.timestamp)}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </ScrollArea>
          </aside>

          <section className="flex min-h-0 flex-col">
            <div className="flex h-11 items-center justify-between gap-3 border-b border-border px-4">
              <div className="min-w-0 text-xs text-muted-foreground">
                {selectedEntry
                  ? `${operationLabel(selectedEntry.operation)} · ${formatEntryTime(selectedEntry.timestamp)}`
                  : "选择一条历史记录"}
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Button
                  type="button"
                  variant={viewMode === "diff" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setViewMode("diff")}
                  disabled={!selectedEntry}
                >
                  <GitCompare className="h-3.5 w-3.5" />
                  差异
                </Button>
                <Button
                  type="button"
                  variant={viewMode === "content" ? "default" : "outline"}
                  size="sm"
                  onClick={() => setViewMode("content")}
                  disabled={!selectedEntry}
                >
                  <FileText className="h-3.5 w-3.5" />
                  内容
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void handleRestoreClick()}
                  disabled={!selectedEntry || isRestoring}
                >
                  {isRestoring ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <RotateCcw className="h-3.5 w-3.5" />
                  )}
                  恢复
                </Button>
              </div>
            </div>

            <ScrollArea className="min-h-0 flex-1">
              <div className="min-h-full bg-background p-4">
                {isLoadingDetail ? (
                  <div className="flex h-48 items-center justify-center text-xs text-muted-foreground">
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    加载中
                  </div>
                ) : detailError ? (
                  <div className="rounded-md border border-error/30 bg-error-container/20 px-3 py-2 text-xs text-error">
                    {detailError}
                  </div>
                ) : !selectedEntry ? (
                  <div className="text-xs text-muted-foreground">暂无可查看记录</div>
                ) : viewMode === "diff" ? (
                  <DiffViewer
                    unifiedDiff={diffDetail?.diff ?? ""}
                    leftLabel={diffDetail?.left_label ?? `history/${selectedEntry.file_path}`}
                    rightLabel={diffDetail?.right_label ?? `current/${selectedEntry.file_path}`}
                    status={diffDetail?.status}
                    canShowContent={diffDetail?.can_show_content ?? true}
                    skipReason={diffDetail?.skip_reason}
                    currentExists={diffDetail?.current_exists ?? true}
                    emptyMessage="当前内容和这条历史一样"
                    className="min-h-[360px]"
                  />
                ) : (
                  <pre className="whitespace-pre-wrap break-words font-mono text-xs leading-5 text-foreground">
                    {contentText}
                  </pre>
                )}
              </div>
            </ScrollArea>
          </section>
        </div>
      </DialogContent>
    </Dialog>

    <AlertDialog open={restoreConfirmOpen} onOpenChange={setRestoreConfirmOpen}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>恢复文件</AlertDialogTitle>
          <AlertDialogDescription>
            {selectedEntry
              ? `确认把 ${fileName} 恢复到 ${formatEntryTime(selectedEntry.timestamp)} 的内容吗？`
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
    </>
  );
}
