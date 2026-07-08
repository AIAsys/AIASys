import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  History,
  Loader2,
  RefreshCw,
  RotateCcw,
  GitBranch,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import { DiffViewer } from "@/components/diff/DiffViewer";
import {
  type ChangeEventItem,
  type FileChangesScope,
  listChangeEvents,
} from "@/lib/api/fileChanges";
import {
  getFileHistoryDiff,
  type FileHistoryDiffResponse,
  restoreFileHistoryEntry,
  type FileHistoryEntry,
} from "@/lib/api/fileHistory";
import type { WorkspaceFile } from "@/types/task";
import {
  FileHistoryDialog,
} from "@/components/layout/WorkspaceSidebar/FileHistoryDialog";
import { ChangeEventCard } from "./ChangeEventCard";
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
  const [events, setEvents] = useState<ChangeEventItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
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
      const response = await listChangeEvents(scope, workspaceId, 50);
      if (requestIdRef.current !== requestId) return;
      setEvents(response.events);
      setSelectedEntryId(null);
      setDiffDetail(null);
      setDiffError(null);
    } catch (err) {
      if (requestIdRef.current !== requestId) return;
      setEvents([]);
      setError(err instanceof Error ? err.message : "加载变更流失败");
    } finally {
      if (requestIdRef.current === requestId) {
        setIsLoading(false);
      }
    }
  }, [workspaceId, scope]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const selectedEntry = useMemo(() => {
    for (const event of events) {
      const entry = event.files.find((file) => file.id === selectedEntryId);
      if (entry) return entry;
    }
    return null;
  }, [events, selectedEntryId]);

  const loadDiff = useCallback(
    async () => {
      if (!workspaceId || !selectedEntry) return;
      setIsLoadingDiff(true);
      setDiffError(null);
      try {
        const response = await getFileHistoryDiff(
          scope,
          workspaceId,
          selectedEntry.id,
          { headers },
        );
        setDiffDetail(response);
      } catch (err) {
        setDiffError(err instanceof Error ? err.message : "加载差异失败");
      } finally {
        setIsLoadingDiff(false);
      }
    },
    [workspaceId, scope, selectedEntry, headers],
  );

  useEffect(() => {
    if (selectedEntryId && selectedEntry) {
      void loadDiff();
    }
  }, [selectedEntryId, selectedEntry, loadDiff]);

  const handleSelectEntry = useCallback(
    (entry: FileHistoryEntry) => {
      if (selectedEntryId === entry.id) {
        setSelectedEntryId(null);
        setDiffDetail(null);
      } else {
        setSelectedEntryId(entry.id);
      }
    },
    [selectedEntryId],
  );

  const handleOpenHistory = useCallback(
    (entry: FileHistoryEntry) => {
      setHistoryDialogFile({
        name: entry.file_path,
        path: entry.file_path,
        size: entry.size,
        mtime: entry.timestamp,
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
    if (!workspaceId || !selectedEntry) return;
    setRestoreConfirmOpen(false);
    setIsRestoring(true);
    setDiffError(null);
    try {
      await restoreFileHistoryEntry(scope, workspaceId, selectedEntry.id, {
        headers,
      });
      await loadData();
    } catch (err) {
      setDiffError(err instanceof Error ? err.message : "恢复文件失败");
    } finally {
      setIsRestoring(false);
    }
  }, [workspaceId, scope, selectedEntry, headers, loadData]);

  const canLoad = Boolean(workspaceId);

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {/* Header */}
      <div className="flex h-11 items-center justify-between border-b border-border px-3">
        <span className="text-xs font-medium text-muted-foreground">
          {isLoading
            ? "加载中"
            : events.length > 0
              ? `${events.length} 个变更事件`
              : "变更流"}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => void loadData()}
            disabled={!canLoad || isLoading}
            aria-label="刷新变更流"
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isLoading && "animate-spin")}
            />
          </Button>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,auto)_minmax(0,1fr)]">
        {/* Event list */}
        <ScrollArea className="min-h-0 border-b border-border">
          {!canLoad ? (
            <div className="flex h-32 items-center justify-center px-6 text-sm text-muted-foreground">
              请先打开一个工作区。
            </div>
          ) : error ? (
            <div className="px-3 py-4 text-xs text-error">{error}</div>
          ) : events.length === 0 && !isLoading ? (
            <div className="flex h-32 items-center justify-center px-6 text-center text-xs text-muted-foreground">
              暂无变更记录。
            </div>
          ) : (
            <div>
              {events.map((event) => (
                <ChangeEventCard
                  key={event.id}
                  event={event}
                  selectedEntryId={selectedEntryId}
                  onSelectEntry={handleSelectEntry}
                />
              ))}
            </div>
          )}
        </ScrollArea>

        {/* Diff preview */}
        <div className="min-h-0 flex flex-col">
          {selectedEntry ? (
            <div className="flex min-h-0 flex-1 flex-col">
              <div className="flex h-9 items-center justify-between border-b border-border px-3">
                <div className="min-w-0 flex-1 truncate text-xs text-muted-foreground">
                  <span className="font-mono text-foreground">
                    {selectedEntry.file_path.split("/").pop()}
                  </span>
                  <span className="ml-2">
                    {OPERATION_LABELS[selectedEntry.operation] ??
                      selectedEntry.operation}{" "}
                    · {formatTime(selectedEntry.timestamp)}
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
                    onClick={() => handleOpenHistory(selectedEntry)}
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
                      leftLabel={diffDetail.left_label ?? `history/${selectedEntry.file_path}`}
                      rightLabel={diffDetail.right_label ?? `current/${selectedEntry.file_path}`}
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
              <GitBranch className="mr-2 h-4 w-4 text-muted-foreground" />
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
              {selectedEntry
                ? `确认把 ${selectedEntry.file_path.split("/").pop() || selectedEntry.file_path} 恢复到 ${formatTime(selectedEntry.timestamp)} 的内容吗？`
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
