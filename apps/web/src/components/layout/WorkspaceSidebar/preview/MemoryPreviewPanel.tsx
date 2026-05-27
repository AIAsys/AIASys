import React, { useCallback, useEffect, useState, Suspense } from "react";
import {
  AlertCircle,
  Brain,
  Eye,
  FileText,
  History,
  Loader2,
  RefreshCw,
  Trash2,
  RotateCcw,
} from "lucide-react";
import {
  applyMemoryRetention,
  getUserDefaultMemoryFileContent,
  getMemoryPipelineStatus,
  resolveMemory,
  getMemoryVersions,
  getMemoryVersion,
  restoreMemoryVersion,
  USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE,
  type MemoryPipelineStatusResponse,
} from "@/lib/api/memory";
import type { AssetResourceNode } from "../assetPreviewFactory";
import { CanvasActionMenu } from "@/pages/DataAnalysisPage/components/AnalysisWorkspaceLayout/components/CanvasActionMenu";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

const MarkdownRenderer = React.lazy(() =>
  import("../../../chat/MarkdownRenderer").then((module) => ({
    default: module.MarkdownRenderer,
  })),
);

function formatTime(value?: number | null) {
  if (!value) return "暂无";
  const date = new Date(value * 1000);
  if (Number.isNaN(date.getTime())) return "暂无";
  return date.toLocaleString();
}

function jobStatusLabel(status?: string | null) {
  switch (status) {
    case "done":
      return "已完成";
    case "running":
      return "运行中";
    case "failed":
      return "失败";
    case "leased":
      return "已租约";
    case "throttled":
      return "等待中";
    default:
      return status || "暂无";
  }
}

function jobStatusVariant(status?: string | null) {
  if (status === "done") return "success";
  if (status === "running" || status === "leased") return "info";
  if (status === "failed") return "error";
  return "secondary";
}

function isUserDefaultMemoryFile(node: AssetResourceNode): boolean {
  const source = typeof node.meta?.source === "string" ? node.meta.source : "";
  return (
    node.meta?._globalResource === true ||
    source === "global_workspace_asset" ||
    source === "global_workspace_file_metadata" ||
    node.path.startsWith("global/")
  );
}

function getMemoryAssetPath(node: AssetResourceNode): string {
  const relativePath =
    typeof node.meta?.relative_path === "string" ? node.meta.relative_path : "";
  if (relativePath) return relativePath;
  return node.path.replace(/^global\//, "").replace(/^workspace\//, "");
}

interface MemoryPreviewPanelProps {
  node: AssetResourceNode;
  sessionId?: string | null;
  workspaceId?: string | null;
  onClose?: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
}

export function MemoryPreviewPanel({
  node,
  sessionId,
  workspaceId,
  onClose,
  closeLabel = "关闭",
  onSplitRight,
  onSplitDown,
}: MemoryPreviewPanelProps) {
  const [markdown, setMarkdown] = useState("");
  const [loading, setLoading] = useState(false);
  const [statusLoading, setStatusLoading] = useState(false);
  const [retentionRunning, setRetentionRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [status, setStatus] = useState<MemoryPipelineStatusResponse | null>(null);
  const [viewMode, setViewMode] = useState<"reading" | "source">("reading");
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<Array<{ id: string; version_type: string; source: string | null; created_at: number; summary: string }>>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [versionDetail, setVersionDetail] = useState<{
    id: string;
    memory_content: string;
    created_at: number;
  } | null>(null);
  const [restoreConfirmId, setRestoreConfirmId] = useState<string | null>(null);
  const [hasVersions, setHasVersions] = useState(false);
  const userDefaultFile = isUserDefaultMemoryFile(node);
  const assetPath = getMemoryAssetPath(node);

  const fetchStatus = useCallback(async () => {
    setStatusLoading(true);
    setStatusError(null);
    try {
      const nextStatus = await getMemoryPipelineStatus();
      setStatus(nextStatus);
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "状态加载失败");
    } finally {
      setStatusLoading(false);
    }
  }, []);

  const fetchMemory = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (userDefaultFile) {
        if (!workspaceId) {
          setMarkdown("");
          setError("当前缺少工作区上下文，无法读取用户默认层文件");
          return;
        }
        const res = await getUserDefaultMemoryFileContent(workspaceId, assetPath);
        const content = res.content || "";
        setMarkdown(content || "_文件为空_");
        if (!content.trim()) {
          getMemoryVersions(USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE)
            .then((v) => setHasVersions(v.versions.some((x) => x.summary?.trim()?.length > 0)))
            .catch(() => setHasVersions(false));
        } else {
          setHasVersions(false);
        }
        return;
      }
      if (!sessionId) {
        setMarkdown("");
        setError("当前缺少会话上下文，无法生成 memory 预览");
        return;
      }
      const res = await resolveMemory(sessionId, workspaceId || undefined);
      const rendered = res.rendered_markdown || "";
      setMarkdown(rendered || "_暂无记忆_");
      if (!rendered.trim()) {
        getMemoryVersions(USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE)
          .then((v) => setHasVersions(v.versions.length > 0))
          .catch(() => setHasVersions(false));
      } else {
        setHasVersions(false);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [assetPath, sessionId, userDefaultFile, workspaceId]);

  useEffect(() => {
    void fetchMemory();
    void fetchStatus();
  }, [fetchMemory, fetchStatus]);

  const handleRefresh = useCallback(() => {
    void fetchMemory();
    void fetchStatus();
  }, [fetchMemory, fetchStatus]);

  const handleRetention = useCallback(async () => {
    setRetentionRunning(true);
    setStatusError(null);
    try {
      await applyMemoryRetention();
      await fetchStatus();
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "清理失败");
    } finally {
      setRetentionRunning(false);
    }
  }, [fetchStatus]);

  const fetchVersions = useCallback(async () => {
    setVersionsLoading(true);
    try {
      const res = await getMemoryVersions(USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE);
      setVersions(res.versions.filter((v) => v.summary?.trim()?.length > 0));
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "加载版本历史失败");
    } finally {
      setVersionsLoading(false);
    }
  }, []);

  const handleShowVersions = useCallback(() => {
    setShowVersions(true);
    void fetchVersions();
  }, [fetchVersions]);

  const handleViewVersion = useCallback(async (versionId: string) => {
    try {
      const detail = await getMemoryVersion(versionId);
      setVersionDetail({
        id: detail.id,
        memory_content: detail.memory_content,
        created_at: detail.created_at,
      });
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "加载版本详情失败");
    }
  }, []);

  const handleRestoreVersion = useCallback(async (versionId: string) => {
    try {
      await restoreMemoryVersion(versionId);
      setRestoreConfirmId(null);
      setShowVersions(false);
      setVersionDetail(null);
      void fetchMemory();
      void fetchStatus();
    } catch (err) {
      setStatusError(err instanceof Error ? err.message : "回滚失败");
    }
  }, [fetchMemory, fetchStatus]);

  const latestStage1Job = status?.stage1.latest_job;
  const latestStage2Job = status?.stage2.latest_job;
  const latestFailure =
    latestStage1Job?.status === "failed"
      ? latestStage1Job.last_error
      : latestStage2Job?.status === "failed"
        ? latestStage2Job.last_error
        : null;

  return (
    <div className="relative flex h-full flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Brain className="h-4 w-4 text-primary" />
          <div>
            <h3 className="text-sm font-medium">{node.name}</h3>
            <p className="text-xs text-muted-foreground">
              {userDefaultFile ? "用户默认层文件" : "Memory"}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={handleRefresh}
            title="刷新记忆"
            aria-label="刷新记忆"
          >
            {loading || statusLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <RefreshCw className="h-3.5 w-3.5" />
            )}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={handleShowVersions}
            title="历史版本"
            aria-label="历史版本"
          >
            <History className="h-3.5 w-3.5" />
          </Button>
          <button
            type="button"
            onClick={() =>
              setViewMode((current) =>
                current === "reading" ? "source" : "reading",
              )
            }
            className="inline-flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs font-medium hover:bg-muted"
          >
            {viewMode === "reading" ? (
              <FileText className="h-3 w-3" />
            ) : (
              <Eye className="h-3 w-3" />
            )}
            {viewMode === "reading" ? "源码" : "阅读"}
          </button>
          {onClose && (
            <CanvasActionMenu
              onClose={onClose}
              closeLabel={closeLabel}
              onSplitRight={onSplitRight}
              onSplitDown={onSplitDown}
            />
          )}
        </div>
      </div>

      {/* Content */}
      <div className="border-b border-border bg-muted/20 px-4 py-3">
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border border-border bg-background px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                Stage 1
              </span>
              <Badge variant={jobStatusVariant(latestStage1Job?.status)}>
                {jobStatusLabel(latestStage1Job?.status)}
              </Badge>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              待写入 {status?.stage1.pending_outputs ?? 0} 条
            </div>
          </div>
          <div className="rounded-lg border border-border bg-background px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                Stage 2
              </span>
              <Badge variant={jobStatusVariant(latestStage2Job?.status)}>
                {jobStatusLabel(latestStage2Job?.status)}
              </Badge>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              最近写入 {formatTime(status?.stage2.latest_consolidated_at)}
            </div>
          </div>
          <div className="rounded-lg border border-border bg-background px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-muted-foreground">
                中间材料
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                disabled={retentionRunning}
                onClick={() => void handleRetention()}
              >
                {retentionRunning ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Trash2 className="h-3 w-3" />
                )}
                清理
              </Button>
            </div>
            <div className="mt-1 truncate text-xs text-muted-foreground" title={status?.memory_root_path}>
              {status?.stage1.total_outputs ?? 0} 条 Stage 1 产物
            </div>
          </div>
        </div>
        {statusError ? (
          <div className="mt-2 rounded-md border border-warning/30 bg-warning-container px-3 py-2 text-xs text-on-warning-container">
            {statusError}
          </div>
        ) : null}
        {latestFailure ? (
          <div className="mt-2 rounded-md border border-error/30 bg-error-container px-3 py-2 text-xs text-on-error-container">
            {latestFailure}
          </div>
        ) : null}
      </div>

      {hasVersions && (
        <div className="mx-4 mt-2 rounded-md border border-info/30 bg-info-container px-3 py-2 text-xs text-on-info-container">
          <div className="flex items-center justify-between">
            <span>检测到历史版本，可从最近版本恢复</span>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 px-2 text-xs"
              onClick={handleShowVersions}
            >
              查看历史版本
            </Button>
          </div>
        </div>
      )}

      <div className="flex-1 overflow-auto p-4">
        {loading && (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            <span className="ml-2 text-sm text-muted-foreground">加载中...</span>
          </div>
        )}

        {error && (
          <div className="flex items-center gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            <AlertCircle className="h-4 w-4" />
            {error}
          </div>
        )}

        {!loading && !error && viewMode === "source" ? (
          <pre className="m-0 h-full overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border bg-muted/40 p-4 font-mono text-xs leading-6 text-foreground">
            {markdown}
          </pre>
        ) : null}

        {!loading && !error && viewMode === "reading" && (
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <Suspense
              fallback={
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                </div>
              }
            >
              <MarkdownRenderer content={markdown} />
            </Suspense>
          </div>
        )}

        {/* Versions Panel */}
        {showVersions && (
          <div className="absolute inset-0 z-10 flex flex-col bg-background">
            <div className="flex items-center justify-between border-b px-4 py-3">
              <h4 className="text-sm font-medium">历史版本</h4>
              <div className="flex items-center gap-2">
                {versionsLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setShowVersions(false);
                    setVersionDetail(null);
                  }}
                >
                  关闭
                </Button>
              </div>
            </div>
            <div className="flex-1 overflow-auto p-4">
              {versionDetail ? (
                <div className="space-y-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-muted-foreground">
                      {formatTime(versionDetail.created_at)}
                    </span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setVersionDetail(null)}
                    >
                      返回列表
                    </Button>
                  </div>
                  <pre className="whitespace-pre-wrap break-words rounded-xl border border-border bg-muted/40 p-4 font-mono text-xs leading-6">
                    {versionDetail.memory_content}
                  </pre>
                </div>
              ) : versions.length === 0 ? (
                <div className="py-12 text-center text-sm text-muted-foreground">
                  暂无历史版本
                </div>
              ) : (
                <div className="space-y-2">
                  {versions.map((v) => (
                    <div
                      key={v.id}
                      className="rounded-lg border border-border bg-muted/20 px-3 py-2"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <Badge variant={v.version_type === "consolidation" ? "default" : "secondary"}>
                            {v.version_type === "consolidation" ? "Consolidation" : "Manual"}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatTime(v.created_at)}
                          </span>
                        </div>
                        <div className="flex items-center gap-1">
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={() => void handleViewVersion(v.id)}
                          >
                            查看
                          </Button>
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-xs"
                            onClick={() => setRestoreConfirmId(v.id)}
                          >
                            <RotateCcw className="mr-1 h-3 w-3" />
                            回滚
                          </Button>
                        </div>
                      </div>
                      {v.source ? (
                        <div className="mt-1 text-xs text-muted-foreground">
                          来源: {v.source}
                        </div>
                      ) : null}
                      <div className="mt-1 line-clamp-2 text-xs text-muted-foreground">
                        {v.summary || "无摘要"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Restore Confirm Dialog */}
        {restoreConfirmId && (
          <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/30">
            <div className="w-80 rounded-lg border border-border bg-background p-4 shadow-lg">
              <h4 className="text-sm font-medium">确认回滚</h4>
              <p className="mt-2 text-xs text-muted-foreground">
                回滚后当前 memory 内容将被替换为历史版本。db 状态（watermark）不会改变，后续新内容仍会正常追加。
              </p>
              <div className="mt-4 flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setRestoreConfirmId(null)}
                >
                  取消
                </Button>
                <Button
                  type="button"
                  variant="default"
                  size="sm"
                  onClick={() => {
                    if (restoreConfirmId) {
                      void handleRestoreVersion(restoreConfirmId);
                    }
                  }}
                >
                  确认回滚
                </Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
