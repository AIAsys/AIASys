/**
 * 全局监控任务管理弹窗
 *
 * 跨工作区查看所有 Monitor 任务，支持筛选、搜索、轻量控制和跳转。
 */

import {
  RefreshCw,
  Search,
  Square,
  Terminal,
  Trash2,
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  listGlobalMonitors,
  getGlobalMonitorSummary,
  killMonitor,
  deleteMonitor,
} from "@/lib/api/monitors";
import { cn } from "@/lib/utils";
import type { GlobalMonitorInfo, GlobalMonitorSummaryResponse } from "@/types/monitors";
import type { TaskWorkspaceSummary } from "../types";

interface GlobalMonitorDialogProps {
  currentWorkspaceId?: string | null;
  workspaces: TaskWorkspaceSummary[];
}

type MonitorStatusFilter = "all" | GlobalMonitorInfo["status"];

const STATUS_LABEL: Record<GlobalMonitorInfo["status"], string> = {
  running: "运行中",
  completed: "已完成",
  error: "错误",
  killed: "已终止",
};

const STATUS_BADGE_CLASS: Record<GlobalMonitorInfo["status"], string> = {
  running: "border-success/20 bg-success-container text-success",
  completed: "border-foreground/10 bg-muted text-muted-foreground",
  error: "border-error/20 bg-error-container text-error",
  killed: "border-warning/20 bg-warning-container text-warning",
};

const FILTER_OPTIONS: Array<{ value: MonitorStatusFilter; label: string }> = [
  { value: "all", label: "全部" },
  { value: "running", label: "运行中" },
  { value: "completed", label: "已完成" },
  { value: "error", label: "错误" },
  { value: "killed", label: "已终止" },
];

function formatDuration(createdAt: number, completedAt?: number | null): string {
  const end = completedAt ?? Date.now() / 1000;
  const diff = Math.max(0, end - createdAt);
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  return `${Math.floor(diff / 3600)}h${Math.floor((diff % 3600) / 60)}m`;
}

export function GlobalMonitorDialog({
  currentWorkspaceId,
  workspaces,
}: GlobalMonitorDialogProps) {
  void workspaces;
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);
  const [summary, setSummary] = useState<GlobalMonitorSummaryResponse | null>(null);
  const [monitors, setMonitors] = useState<GlobalMonitorInfo[]>([]);
  const [statusFilter, setStatusFilter] = useState<MonitorStatusFilter>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [pendingId, setPendingId] = useState<string | null>(null);

  const loadMonitorState = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const [summaryResponse, listResponse] = await Promise.all([
        getGlobalMonitorSummary(),
        listGlobalMonitors(),
      ]);
      setSummary(summaryResponse);
      setMonitors(listResponse.monitors ?? []);
    } catch (error) {
      const message = error instanceof Error ? error.message : "读取全局监控任务状态失败。";
      setLoadError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMonitorState();
  }, [loadMonitorState]);

  const filteredMonitors = useMemo(() => {
    const normalizedQuery = deferredSearchQuery.trim().toLowerCase();
    return monitors
      .filter((m) => statusFilter === "all" || m.status === statusFilter)
      .filter((m) => {
        if (!normalizedQuery) return true;
        return [m.command, m.workspace_title, m.workspace_id, m.session_id]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((left, right) => {
        const rank: Record<GlobalMonitorInfo["status"], number> = {
          running: 0,
          error: 1,
          killed: 2,
          completed: 3,
        };
        const statusDelta = rank[left.status] - rank[right.status];
        if (statusDelta !== 0) return statusDelta;
        return right.created_at - left.created_at;
      });
  }, [deferredSearchQuery, statusFilter, monitors]);

  const handleKill = useCallback(
    async (monitor: GlobalMonitorInfo) => {
      setPendingId(monitor.id);
      setFeedback(null);
      try {
        await killMonitor(
          monitor.session_key.split(":")[0],
          monitor.session_id,
          monitor.id,
        );
        setFeedback({ tone: "success", message: `已终止 ${monitor.command}。` });
        await loadMonitorState();
      } catch (error) {
        const message = error instanceof Error ? error.message : "终止失败。";
        setFeedback({ tone: "error", message });
      } finally {
        setPendingId(null);
      }
    },
    [loadMonitorState],
  );

  const handleDelete = useCallback(
    async (monitor: GlobalMonitorInfo) => {
      setPendingId(monitor.id);
      setFeedback(null);
      try {
        await deleteMonitor(
          monitor.session_key.split(":")[0],
          monitor.session_id,
          monitor.id,
        );
        setFeedback({ tone: "success", message: `已删除 ${monitor.command}。` });
        await loadMonitorState();
      } catch (error) {
        const message = error instanceof Error ? error.message : "删除失败。";
        setFeedback({ tone: "error", message });
      } finally {
        setPendingId(null);
      }
    },
    [loadMonitorState],
  );

  const counts = summary ?? { total: 0, running: 0, completed: 0, error: 0, killed: 0 };

  const content = (
    <div className="min-h-0 flex-1 overflow-hidden px-6 py-5">
          <div className="flex h-full min-h-0 flex-col gap-4">
            {feedback ? (
              <div
                className={cn(
                  "rounded-2xl border px-4 py-3 text-sm",
                  feedback.tone === "success"
                    ? "border-success/20 bg-success-container text-success"
                    : "border-error/20 bg-error-container text-error",
                )}
              >
                {feedback.message}
              </div>
            ) : null}

            {loadError ? (
              <div className="rounded-2xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
                {loadError}
              </div>
            ) : null}

            {/* 筛选 + 搜索 */}
            <div className="flex flex-wrap items-center gap-2">
              {FILTER_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setStatusFilter(option.value)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-[11px] transition-colors",
                    statusFilter === option.value
                      ? "border-border bg-muted text-foreground"
                      : "border-transparent bg-muted/40 text-muted-foreground hover:bg-muted/60",
                  )}
                >
                  {option.label}
                </button>
              ))}
              <div className="ml-auto flex items-center gap-2">
                <Search className="h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder="搜索命令、工作区..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="h-8 w-48 rounded-lg text-[11px]"
                />
              </div>
            </div>

            {/* 列表 */}
            <section className="flex flex-col min-h-0 flex-1 overflow-hidden rounded-2xl border border-border bg-background">
              <div className="border-b border-border px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="text-sm font-semibold text-foreground">任务列表</div>
                    <Badge variant="outline" className="border-border bg-background text-muted-foreground">
                      {counts.total} 条
                    </Badge>
                    {counts.running > 0 ? (
                      <Badge variant="outline" className="border-success/20 bg-success-container text-success">
                        {counts.running} 运行中
                      </Badge>
                    ) : null}
                    {counts.error > 0 ? (
                      <Badge variant="outline" className="border-error/20 bg-error-container text-error">
                        {counts.error} 错误
                      </Badge>
                    ) : null}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-8 gap-1.5 text-[11px]"
                    onClick={() => void loadMonitorState()}
                    disabled={isLoading}
                  >
                    <RefreshCw className={cn("h-3.5 w-3.5", isLoading && "animate-spin")} />
                    刷新状态
                  </Button>
                </div>
              </div>

              <div className="min-h-0 overflow-y-auto px-4 py-3">
                {filteredMonitors.length === 0 ? (
                  <div className="flex h-full flex-col items-center justify-center py-12 text-center">
                    <Terminal className="h-8 w-8 text-muted-foreground/30" />
                    <div className="mt-3 text-sm font-medium text-foreground">暂无监控任务</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      全局范围内没有找到符合条件的监控任务
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {filteredMonitors.map((monitor) => (
                      <div
                        key={monitor.id}
                        className="group relative flex items-start gap-3 rounded-xl border border-border/60 bg-muted/15 px-4 py-3 transition-colors hover:border-border"
                      >
                        {/* 状态指示 */}
                        <div className="mt-0.5 shrink-0">
                          {monitor.status === "running" ? (
                            <span className="relative flex h-2 w-2">
                              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-info opacity-75" />
                              <span className="relative inline-flex h-2 w-2 rounded-full bg-info" />
                            </span>
                          ) : (
                            <span
                              className={cn(
                                "block h-2 w-2 rounded-full",
                                monitor.status === "completed"
                                  ? "bg-success"
                                  : monitor.status === "error"
                                    ? "bg-error"
                                    : "bg-warning",
                              )}
                            />
                          )}
                        </div>

                        {/* 内容 */}
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="min-w-0 truncate font-mono text-[13px] font-medium text-foreground">
                              {monitor.command}
                            </span>
                            <Badge
                              variant="outline"
                              className={cn("shrink-0 text-[10px]", STATUS_BADGE_CLASS[monitor.status])}
                            >
                              {STATUS_LABEL[monitor.status]}
                            </Badge>
                            <Badge variant="outline" className="shrink-0 text-[10px]">
                              {monitor.mode === "silent" ? "静默" : "通知"}
                            </Badge>
                            {monitor.workspace_id === currentWorkspaceId ? (
                              <Badge
                                variant="outline"
                                className="shrink-0 border-info/20 bg-info-container text-info text-[10px]"
                              >
                                当前
                              </Badge>
                            ) : null}
                          </div>

                          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                            <span>
                              工作区: {monitor.workspace_title || monitor.workspace_id.slice(0, 8)}
                            </span>
                            <span>会话: {monitor.session_id.slice(0, 8)}</span>
                            <span>
                              时长: {formatDuration(monitor.created_at, monitor.completed_at)}
                            </span>
                            {monitor.exit_code !== null && (
                              <span>退出码: {monitor.exit_code}</span>
                            )}
                          </div>
                        </div>

                        {/* 操作 */}
                        <div className="flex shrink-0 items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                          {monitor.status === "running" && (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0 text-error hover:bg-error/10 hover:text-error"
                              onClick={() => handleKill(monitor)}
                              disabled={pendingId === monitor.id}
                              title="终止"
                            >
                              <Square className="h-3.5 w-3.5" />
                            </Button>
                          )}
                          {monitor.status !== "running" && (
                            <Button
                              type="button"
                              size="sm"
                              variant="ghost"
                              className="h-7 w-7 p-0 text-muted-foreground hover:bg-error/10 hover:text-error"
                              onClick={() => handleDelete(monitor)}
                              disabled={pendingId === monitor.id}
                              title="删除"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </Button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </section>
          </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-background">
      {content}
    </div>
  );
}

export default GlobalMonitorDialog;
