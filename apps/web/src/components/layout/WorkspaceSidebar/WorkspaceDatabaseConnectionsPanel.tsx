import { useCallback, useEffect, useRef, useState } from "react";
import { Database, Loader2, MoreVertical, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  deleteDatabaseConnector,
  getDatabaseConnectorErrorMessage,
  listRuntimeDatabaseHandles,
  testSavedDatabaseConnector,
} from "@/lib/api/databaseConnectors";
import { subscribeDatabaseConnectorSync } from "@/lib/databaseConnectorEvents";
import { cn } from "@/lib/utils";
import {
  getRuntimeDatabaseTypeLabel,
} from "@/types/databaseConnectors";
import type { RuntimeDatabaseHandleInfo } from "@/types/databaseConnectors";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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

interface WorkspaceDatabaseConnectionsPanelProps {
  sessionId?: string | null;
  selectedHandle?: string | null;
  onSelectHandle?: (handle: string) => void;
  onCreateConnection?: () => void;
  onManageConnections?: () => void;
}

type ConnectionStatus = "testing" | "online" | "offline";

interface ConnectionStatusInfo {
  status: ConnectionStatus;
  error?: string;
}

export function WorkspaceDatabaseConnectionsPanel({
  sessionId,
  selectedHandle,
  onSelectHandle,
  onCreateConnection,
  onManageConnections,
}: WorkspaceDatabaseConnectionsPanelProps) {
  const [handles, setHandles] = useState<RuntimeDatabaseHandleInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMap, setStatusMap] = useState<Map<string, ConnectionStatusInfo>>(new Map());

  const [deletingConnectorId, setDeletingConnectorId] = useState<string | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleAdd = onCreateConnection ?? onManageConnections;
  const handleManage = onManageConnections;

  const selectedHandleRef = useRef(selectedHandle);
  selectedHandleRef.current = selectedHandle;
  const handlesRef = useRef(handles);
  handlesRef.current = handles;

  const testConnections = useCallback(async (handlesToTest: RuntimeDatabaseHandleInfo[]) => {
    const newStatusMap = new Map<string, ConnectionStatusInfo>();
    for (const handle of handlesToTest) {
      newStatusMap.set(handle.handle, { status: "testing" });
    }
    setStatusMap(newStatusMap);

    await Promise.all(
      handlesToTest.map(async (handle) => {
        try {
          const result = await testSavedDatabaseConnector(handle.connector_id);
          setStatusMap((prev) => {
            const next = new Map(prev);
            next.set(handle.handle, {
              status: result.success ? "online" : "offline",
              error: result.success ? undefined : result.message,
            });
            return next;
          });
        } catch (err) {
          setStatusMap((prev) => {
            const next = new Map(prev);
            next.set(handle.handle, {
              status: "offline",
              error: err instanceof Error ? err.message : "连接测试失败",
            });
            return next;
          });
        }
      })
    );
  }, []);

  const loadHandles = useCallback(async () => {
    if (!sessionId) {
      setHandles([]);
      setStatusMap(new Map());
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const response = await listRuntimeDatabaseHandles(sessionId);
      setHandles(response.handles);
      if (!selectedHandleRef.current && response.handles.length > 0) {
        onSelectHandle?.(response.handles[0].handle);
      }
      // 异步测试每个连接的可用性，仅用于状态展示
      void testConnections(response.handles);
    } catch (err) {
      setError(getDatabaseConnectorErrorMessage(err, "加载数据库连接失败"));
    } finally {
      setLoading(false);
    }
  }, [sessionId, onSelectHandle, testConnections]);

  useEffect(() => {
    void loadHandles();
  }, [loadHandles]);

  useEffect(() => {
    return subscribeDatabaseConnectorSync((event) => {
      if (event.sessionId && event.sessionId !== sessionId) {
        return;
      }
      void loadHandles();
    });
  }, [loadHandles, sessionId]);

  const handleTestSingle = useCallback(async (handle: RuntimeDatabaseHandleInfo) => {
    setStatusMap((prev) => {
      const next = new Map(prev);
      next.set(handle.handle, { status: "testing" });
      return next;
    });
    try {
      const result = await testSavedDatabaseConnector(handle.connector_id);
      setStatusMap((prev) => {
        const next = new Map(prev);
        next.set(handle.handle, {
          status: result.success ? "online" : "offline",
          error: result.success ? undefined : result.message,
        });
        return next;
      });
    } catch (err) {
      setStatusMap((prev) => {
        const next = new Map(prev);
        next.set(handle.handle, {
          status: "offline",
          error: err instanceof Error ? err.message : "连接测试失败",
        });
        return next;
      });
    }
  }, []);

  const handleDeleteConfirm = useCallback(async () => {
    if (!deletingConnectorId) return;
    setIsDeleting(true);
    try {
      await deleteDatabaseConnector(deletingConnectorId);
      setHandles((prev) => prev.filter((h) => h.connector_id !== deletingConnectorId));
      setStatusMap((prev) => {
        const next = new Map(prev);
        for (const [handle] of prev) {
          const h = handlesRef.current.find((x) => x.handle === handle);
          if (h && h.connector_id === deletingConnectorId) {
            next.delete(handle);
          }
        }
        return next;
      });
    } catch (err) {
      setError(getDatabaseConnectorErrorMessage(err, "删除数据库连接失败"));
    } finally {
      setIsDeleting(false);
      setDeletingConnectorId(null);
    }
  }, [deletingConnectorId]);

  if (!sessionId) {
    return (
      <div className="flex h-full flex-col items-center justify-center px-6 text-center text-muted-foreground">
        <Database className="mb-2 h-8 w-8 opacity-50" />
        <p className="text-sm font-medium text-foreground/80">当前暂无可用会话</p>
        <p className="mt-1 text-xs leading-5">
          先进入一个具体会话，再管理数据库连接。
        </p>
      </div>
    );
  }

  const deletingHandle = handles.find((h) => h.connector_id === deletingConnectorId);

  return (
    <div className="flex h-full flex-col bg-background">
      {/* Header */}
      <div className="flex-shrink-0 border-b border-border px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <Database className="h-4 w-4 text-tertiary" />
            数据库连接
          </div>
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => void loadHandles()}
              className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted"
              title="刷新"
            >
              {loading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <RefreshCw className="h-3.5 w-3.5" />
              )}
            </button>
            {handleAdd ? (
              <button
                type="button"
                onClick={handleAdd}
                className="inline-flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
                title="添加数据库连接"
              >
                <Plus className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        </div>
      </div>

      {/* Connection list */}
      <div className="min-h-0 flex-1 overflow-y-auto px-2 py-2">
        {loading && handles.length === 0 ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : error ? (
          <div className="px-2 py-4 text-center text-[11px] text-destructive">
            {error}
          </div>
        ) : handles.length === 0 ? (
          <div className="flex flex-col items-center justify-center px-2 py-8 text-center text-muted-foreground">
            <Database className="mb-2 h-6 w-6 opacity-40" />
            <p className="text-[12px]">暂无外部数据库连接</p>
            <p className="mt-1 text-[11px] opacity-60">
              点击 + 添加外部数据库
            </p>
          </div>
        ) : (
          <div className="space-y-0.5">
            {handles.map((handle) => {
              const statusInfo = statusMap.get(handle.handle);
              const isSelected = selectedHandle === handle.handle;
              return (
                <div
                  key={handle.handle}
                  className={cn(
                    "group flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-[12px] transition-colors",
                    isSelected
                      ? "bg-primary/10 text-primary"
                      : "text-foreground hover:bg-muted"
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelectHandle?.(handle.handle)}
                    title={statusInfo?.error}
                    className="flex min-w-0 flex-1 items-center gap-2 text-left"
                  >
                    <div className="relative">
                      <Database className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                      {statusInfo && (
                        <span
                          className={cn(
                            "absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full border border-background",
                            statusInfo.status === "online" && "bg-green-500",
                            statusInfo.status === "offline" && "bg-red-500",
                            statusInfo.status === "testing" && "bg-gray-400 animate-pulse"
                          )}
                        />
                      )}
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="truncate font-medium">{handle.name}</div>
                      <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
                        <span>{getRuntimeDatabaseTypeLabel(handle.db_type)}</span>
                        {statusInfo?.status === "offline" && (
                          <span className="text-red-500">连接失败</span>
                        )}
                      </div>
                    </div>
                  </button>

                  {/* Three-dots action menu */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <button
                        type="button"
                        onClick={(e) => e.stopPropagation()}
                        className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground opacity-0 transition-opacity hover:bg-muted group-hover:opacity-100 focus:opacity-100"
                        title="操作"
                      >
                        <MoreVertical className="h-3.5 w-3.5" />
                      </button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="min-w-[140px]">
                      <DropdownMenuItem
                        onClick={() => void handleTestSingle(handle)}
                        disabled={statusInfo?.status === "testing"}
                        className="gap-2 text-xs"
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                        刷新状态
                      </DropdownMenuItem>
                      {handleManage ? (
                        <DropdownMenuItem
                          onClick={handleManage}
                          className="gap-2 text-xs"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                          编辑连接
                        </DropdownMenuItem>
                      ) : null}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onClick={() => setDeletingConnectorId(handle.connector_id)}
                        className="gap-2 text-xs text-destructive focus:text-destructive"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        删除连接
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Delete confirmation dialog */}
      <AlertDialog
        open={Boolean(deletingConnectorId)}
        onOpenChange={(open) => {
          if (!open && !isDeleting) setDeletingConnectorId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除数据库连接</AlertDialogTitle>
            <AlertDialogDescription>
              {deletingHandle
                ? `确定删除「${deletingHandle.name}」吗？该连接会同时从所有会话挂载中移除。`
                : "确定删除当前数据库连接吗？"}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>取消</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => void handleDeleteConfirm()}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
