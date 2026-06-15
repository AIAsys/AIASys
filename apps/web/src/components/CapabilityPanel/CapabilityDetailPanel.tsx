import { useEffect, useState, useCallback } from "react";
import {
  Loader2,
  RefreshCw,
  Trash2,
  CheckCircle2,
  XCircle,
  CircleOff,
  Package,
  FileJson,
} from "lucide-react";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  listWorkspaceCapabilities,
  listAvailableCapabilities,
  installCapability,
  uninstallCapability,
  activateCapability,
  deactivateCapability,
  verifyCapability,
  listGlobalCapabilities,
  installGlobalCapability,
  uninstallGlobalCapability,
  activateGlobalCapability,
  deactivateGlobalCapability,
  verifyGlobalCapability,
  getCapabilitySourceFile,
  listCapabilitySourceTree,
  type WorkspaceCapabilityItem,
  type CapabilityItem,
  type CapabilitySourceTreeEntry,
} from "@/lib/api/capabilities";
import { CapabilitySourceTree } from "./CapabilitySourceTree";

const KIND_LABEL: Record<string, string> = {
  skill_pack: "技能",
  mcp_server: "连接器",
  subagent: "专家",
};

const STATUS_ICON: Record<string, React.ReactNode> = {
  active: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  healthy: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  normal: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  ok: <CheckCircle2 className="h-4 w-4 text-green-500" />,
  error: <XCircle className="h-4 w-4 text-red-500" />,
  disabled: <CircleOff className="h-4 w-4 text-slate-500" />,
  installed: <Package className="h-4 w-4 text-blue-500" />,
  available: <Package className="h-4 w-4 text-muted-foreground" />,
};

const STATUS_LABEL: Record<string, string> = {
  active: "可用",
  healthy: "可用",
  normal: "可用",
  ok: "可用",
  error: "异常",
  disabled: "已禁用",
  installed: "已安装",
  available: "可安装",
};

const STATUS_BADGE_CLASS: Record<string, string> = {
  active:
    "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950 dark:text-green-300",
  healthy:
    "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950 dark:text-green-300",
  normal:
    "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950 dark:text-green-300",
  ok: "border-green-200 bg-green-50 text-green-700 dark:border-green-900 dark:bg-green-950 dark:text-green-300",
  error:
    "border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300",
  disabled:
    "border-slate-200 bg-slate-50 text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300",
  installed:
    "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-300",
  available:
    "border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300",
};

export interface CapabilityDetailPanelProps {
  workspaceId: string;
  capabilityId: string;
  scope?: "workspace" | "global";
}

export function CapabilityDetailPanel({
  workspaceId,
  capabilityId,
  scope = "workspace",
}: CapabilityDetailPanelProps) {
  const [workspaceCaps, setWorkspaceCaps] = useState<WorkspaceCapabilityItem[]>([]);
  const [availableCaps, setAvailableCaps] = useState<CapabilityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [error, setError] = useState(false);

  // Source tree preview
  const [sourceTreeLoading, setSourceTreeLoading] = useState(false);
  const [sourceTreeEntries, setSourceTreeEntries] = useState<CapabilitySourceTreeEntry[]>([]);
  const [selectedSourceFile, setSelectedSourceFile] = useState<string>("");
  const [sourceFileContent, setSourceFileContent] = useState<string | null>(null);
  const [sourceFileLoading, setSourceFileLoading] = useState(false);

  // MCP config
  const [mcpConfigOpen, setMcpConfigOpen] = useState(false);
  const [mcpConfigDraft, setMcpConfigDraft] = useState("{}");
  const [mcpConfigError, setMcpConfigError] = useState<string | null>(null);

  const isGlobal = scope === "global";

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const [ws, avail] = await Promise.all([
        isGlobal ? listGlobalCapabilities() : listWorkspaceCapabilities(workspaceId),
        listAvailableCapabilities(),
      ]);
      setWorkspaceCaps(ws);
      setAvailableCaps(avail);
    } catch (err) {
      console.error(err);
      setError(true);
      setWorkspaceCaps([]);
      setAvailableCaps([]);
    } finally {
      setLoading(false);
    }
  }, [workspaceId, isGlobal]);

  useEffect(() => {
    void load();
  }, [load]);

  const cap =
    workspaceCaps.find((c) => c.capability_id === capabilityId) ??
    availableCaps.find((c) => c.capability_id === capabilityId) ??
    null;

  // Auto-load source tree when cap is a skill_pack or subagent
  useEffect(() => {
    if (!cap || (cap.kind !== "skill_pack" && cap.kind !== "subagent")) {
      setSourceTreeEntries([]);
      setSelectedSourceFile("");
      setSourceFileContent(null);
      return;
    }
    setSourceTreeLoading(true);
    setSourceTreeEntries([]);
    setSelectedSourceFile("");
    setSourceFileContent(null);

    listCapabilitySourceTree(cap.capability_id)
      .then((resp) => {
        const entries = resp?.entries ?? [];
        setSourceTreeEntries(entries);

        // Auto-select entry file
        const defaultFile = cap.kind === "subagent" ? "prompt.md" : "SKILL.md";
        const entry = entries.find((e) => e.path === defaultFile && !e.is_dir);
        if (entry) {
          setSelectedSourceFile(entry.path);
          setSourceFileLoading(true);
          getCapabilitySourceFile(cap.capability_id, entry.path)
            .then((fileResp) => {
              setSourceFileContent(fileResp?.content ?? "暂无内容");
            })
            .catch(() => setSourceFileContent(null))
            .finally(() => setSourceFileLoading(false));
        }
      })
      .catch(() => setSourceTreeEntries([]))
      .finally(() => setSourceTreeLoading(false));
  }, [cap, capabilityId]);

  const handleSelectSourceFile = useCallback(
    (path: string) => {
      if (!cap || path === selectedSourceFile) return;
      setSelectedSourceFile(path);
      setSourceFileLoading(true);
      getCapabilitySourceFile(cap.capability_id, path)
        .then((resp) => {
          setSourceFileContent(resp?.content ?? "暂无内容");
        })
        .catch(() => setSourceFileContent(null))
        .finally(() => setSourceFileLoading(false));
    },
    [cap, selectedSourceFile],
  );

  const isWorkspaceCap = (c: unknown): c is WorkspaceCapabilityItem =>
    typeof c === "object" && c !== null && "enabled" in c;
  const canToggle = (_c: WorkspaceCapabilityItem) => true;

  const handleInstall = async (config?: Record<string, unknown>) => {
    if (!cap) return;
    setProcessingId(capabilityId);
    try {
      if (isGlobal) {
        await installGlobalCapability(capabilityId, config);
      } else {
        await installCapability(workspaceId, capabilityId, config);
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handleUninstall = async () => {
    setProcessingId(capabilityId);
    try {
      if (isGlobal) {
        await uninstallGlobalCapability(capabilityId);
      } else {
        await uninstallCapability(workspaceId, capabilityId);
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handleToggle = async (enabled: boolean) => {
    setProcessingId(capabilityId);
    try {
      if (enabled) {
        if (isGlobal) {
          await deactivateGlobalCapability(capabilityId);
        } else {
          await deactivateCapability(workspaceId, capabilityId);
        }
      } else {
        if (isGlobal) {
          await activateGlobalCapability(capabilityId);
        } else {
          await activateCapability(workspaceId, capabilityId);
        }
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handleVerify = async () => {
    setProcessingId(capabilityId);
    try {
      if (isGlobal) {
        await verifyGlobalCapability(capabilityId);
      } else {
        await verifyCapability(workspaceId, capabilityId);
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const openMcpConfig = () => {
    if (!cap || isWorkspaceCap(cap)) return;
    setMcpConfigError(null);
    const schema = cap.config_schema;
    const defaultConfig: Record<string, unknown> = {};
    if (schema && typeof schema === "object" && "properties" in schema) {
      const props = (schema as Record<string, unknown>).properties as Record<string, unknown>;
      for (const [key, val] of Object.entries(props)) {
        if (val && typeof val === "object" && "default" in val) {
          defaultConfig[key] = (val as Record<string, unknown>).default;
        }
      }
    }
    setMcpConfigDraft(JSON.stringify(defaultConfig, null, 2));
    setMcpConfigOpen(true);
  };

  const handleMcpConfigInstall = async () => {
    if (!cap || cap.kind !== "mcp_server" || isWorkspaceCap(cap)) return;
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(mcpConfigDraft);
    } catch (e) {
      setMcpConfigError(e instanceof Error ? e.message : "JSON 格式错误");
      return;
    }
    setMcpConfigOpen(false);
    await handleInstall(config);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!cap) {
    if (error) {
      return (
        <div className="flex h-full flex-col items-center justify-center gap-3 text-sm text-muted-foreground">
          <span>加载失败，请重试</span>
          <Button size="sm" variant="outline" onClick={() => void load()}>
            <RefreshCw className="mr-1 h-3 w-3" />
            重试
          </Button>
        </div>
      );
    }
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        未找到该能力
      </div>
    );
  }

  const status = isWorkspaceCap(cap) ? (cap.enabled ? cap.status : "disabled") : "available";

  return (
    <div className="h-full overflow-y-auto">
      <div className="space-y-4 p-4">
        {/* 头部 */}
        <div className="space-y-3">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <h3 className="text-lg font-medium">
                {cap.display_name || cap.capability_id}
              </h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Badge variant="outline" className="text-[10px]">
                  {KIND_LABEL[cap.kind] ?? cap.kind}
                </Badge>
                {(cap as CapabilityItem).version && (
                  <span>v{(cap as CapabilityItem).version}</span>
                )}
                {(cap as WorkspaceCapabilityItem).source && (
                  <span>{(cap as WorkspaceCapabilityItem).source}</span>
                )}
              </div>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {isWorkspaceCap(cap) ? (
                <>
                  <Button
                    size="sm"
                    variant="outline"
                    className="shrink-0"
                    onClick={() => void handleVerify()}
                    disabled={processingId === capabilityId}
                  >
                    {processingId === capabilityId ? (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    ) : (
                      <RefreshCw className="mr-1 h-3 w-3" />
                    )}
                    验活
                  </Button>
                  {canToggle(cap) && (
                    <Button
                      size="sm"
                      variant="outline"
                      className="shrink-0"
                      onClick={() => void handleToggle(cap.enabled)}
                      disabled={processingId === capabilityId}
                    >
                      {cap.enabled ? "禁用" : "激活"}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="destructive"
                    className="shrink-0"
                    onClick={() => void handleUninstall()}
                    disabled={processingId === capabilityId}
                  >
                    <Trash2 className="mr-1 h-3 w-3" />
                    卸载
                  </Button>
                </>
              ) : (
                <>
                  {cap.kind === "mcp_server" &&
                    Object.keys(cap.config_schema || {}).length > 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        onClick={() => openMcpConfig()}
                        disabled={processingId === capabilityId}
                      >
                        <FileJson className="mr-1 h-3 w-3" />
                        配置并安装
                      </Button>
                    )}
                  <Button
                    size="sm"
                    className="shrink-0"
                    onClick={() => void handleInstall()}
                    disabled={processingId === capabilityId}
                  >
                    {processingId === capabilityId ? (
                      <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                    ) : null}
                    安装
                  </Button>
                </>
              )}
            </div>
          </div>
          {isWorkspaceCap(cap) && (
            <div
              className={cn(
                "inline-flex max-w-full items-center gap-1.5 self-start rounded-md border px-2 py-1 text-xs",
                STATUS_BADGE_CLASS[status] ?? STATUS_BADGE_CLASS.available
              )}
            >
              {STATUS_ICON[status] ?? STATUS_ICON.available}
              <span className="truncate">{STATUS_LABEL[status] ?? status}</span>
            </div>
          )}
        </div>

        {/* 描述 */}
        {cap.description && (
          <p className="break-words text-sm leading-5 text-muted-foreground">
            {cap.description}
          </p>
        )}

        {/* 错误信息 */}
        {isWorkspaceCap(cap) && cap.error_message && (
          <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            {cap.error_message}
          </div>
        )}

        {/* 工具列表 */}
        {!isWorkspaceCap(cap) && (cap as CapabilityItem).tool_names && (cap as CapabilityItem).tool_names.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-medium text-muted-foreground">
              包含工具 ({(cap as CapabilityItem).tool_names.length})
            </div>
            <div className="flex flex-wrap gap-1">
              {(cap as CapabilityItem).tool_names.map((t) => (
                <Badge key={t} variant="secondary" className="text-[10px]">
                  {t.split(":").pop()}
                </Badge>
              ))}
            </div>
          </div>
        )}

        {/* 能力源文件树 + 预览 */}
        {(cap.kind === "skill_pack" || cap.kind === "subagent") && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">能力源文件</div>
            {sourceTreeLoading ? (
              <div className="flex items-center gap-2 py-4 text-xs text-muted-foreground">
                <Loader2 className="h-3 w-3 animate-spin" />
                正在扫描文件...
              </div>
            ) : sourceTreeEntries.length === 0 ? (
              <div className="rounded-md border border-dashed border-border bg-muted/40 p-3 text-xs text-muted-foreground">
                该能力源下暂无文件。
              </div>
            ) : (
              <div className="flex gap-2 rounded-md border border-border bg-muted/20 overflow-hidden" style={{ minHeight: "200px", maxHeight: "500px" }}>
                {/* 文件树 */}
                <div className="w-44 shrink-0 overflow-y-auto border-r border-border bg-background py-2">
                  <CapabilitySourceTree
                    entries={sourceTreeEntries}
                    selectedPath={selectedSourceFile}
                    onSelectFile={handleSelectSourceFile}
                  />
                </div>
                {/* 内容区 */}
                <div className="flex-1 min-w-0 overflow-y-auto">
                  {sourceFileLoading ? (
                    <div className="flex items-center justify-center gap-2 py-10 text-xs text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      正在加载...
                    </div>
                  ) : sourceFileContent !== null ? (
                    selectedSourceFile === "README.md" ? (
                      <div className="prose prose-sm max-w-none dark:prose-invert p-3 text-[11px] leading-5 text-foreground">
                        <MarkdownRenderer content={sourceFileContent} />
                      </div>
                    ) : (
                      <pre className="p-3 text-[11px] leading-5 text-foreground whitespace-pre-wrap break-words">
                        {sourceFileContent}
                      </pre>
                    )
                  ) : (
                    <div className="flex items-center justify-center py-10 text-xs text-muted-foreground">
                      无法加载文件内容
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* MCP Config Schema：已安装/未安装都显示 */}
        {cap.kind === "mcp_server" && (cap as CapabilityItem).config_schema && (
          <div className="space-y-2">
            <div className="text-xs font-medium text-muted-foreground">配置说明</div>
            <pre className="overflow-auto rounded-md border border-border bg-muted/40 p-3 text-[11px] leading-5 text-foreground">
              {JSON.stringify((cap as CapabilityItem).config_schema, null, 2)}
            </pre>
          </div>
        )}
      </div>

      {/* MCP Config Dialog */}
      <Dialog open={mcpConfigOpen} onOpenChange={setMcpConfigOpen}>
        <DialogContent className="max-h-[90vh] max-w-lg overflow-hidden flex flex-col bg-background">
          <DialogHeader className="shrink-0">
            <DialogTitle>配置并安装</DialogTitle>
            <DialogDescription>
              {cap.display_name || cap.capability_id || "MCP 服务器"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto min-h-0 space-y-4">
            {!isWorkspaceCap(cap) && cap.config_schema && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground">配置说明</div>
                <pre className="overflow-auto rounded-md border border-border bg-muted/40 p-2 text-[11px] leading-4 text-foreground">
                  {JSON.stringify(cap.config_schema, null, 2)}
                </pre>
              </div>
            )}
            <div className="space-y-1">
              <div className="text-xs font-medium text-muted-foreground">配置 JSON</div>
              <Textarea
                value={mcpConfigDraft}
                onChange={(e) => {
                  setMcpConfigDraft(e.target.value);
                  setMcpConfigError(null);
                }}
                className="min-h-[120px] font-mono text-xs"
                placeholder='{"key": "value"}'
              />
              {mcpConfigError && <div className="text-xs text-red-500">{mcpConfigError}</div>}
            </div>
          </div>
          <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setMcpConfigOpen(false)}
            >
              取消
            </Button>
            <Button
              type="button"
              size="sm"
              className="h-8 text-xs"
              onClick={() => void handleMcpConfigInstall()}
            >
              安装
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
