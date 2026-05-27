import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { MarkdownRenderer } from "@/components/chat/MarkdownRenderer";
import {
  Loader2,
  RefreshCw,
  Trash2,
  CheckCircle2,
  XCircle,
  CircleOff,
  Package,
  Search,
  X,
  Eye,
  FileJson,
  Plus,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useSkills } from "@/hooks/useSkills";
import type { SkillEntryResponse } from "@/types/api";
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
  listCapabilitySourceTree,
  getCapabilitySourceFile,
  type WorkspaceCapabilityItem,
  type CapabilityItem,
  type CapabilitySourceTreeEntry,
} from "@/lib/api/capabilities";
import { CapabilitySourceTree } from "./CapabilitySourceTree";
import { SkillMarketDialog } from "@/components/SkillMarketDialog";
import { MCPMarketDialog } from "@/components/MCPMarketDialog";
import { CollaborationRolesSettingsDialog } from "@/components/CollaborationRolesSettingsDialog";

interface CapabilityPanelProps {
  workspaceId: string;
  scope?: "workspace" | "global";
  mode?: "full" | "workspace-config";
}

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

const KIND_FILTERS = [
  { id: "all", label: "全部" },
  { id: "skill_pack", label: "技能" },
  { id: "mcp_server", label: "连接器" },
  { id: "subagent", label: "专家协作节点" },
] as const;

const STATUS_FILTERS = [
  { id: "all", label: "全部" },
  { id: "enabled", label: "已启用" },
  { id: "disabled", label: "已禁用" },
  { id: "available", label: "可安装" },
] as const;

type FilterKind = (typeof KIND_FILTERS)[number]["id"];
type FilterStatus = (typeof STATUS_FILTERS)[number]["id"];

export function CapabilityPanel({ workspaceId, scope = "workspace", mode = "full" }: CapabilityPanelProps) {
  const isGlobal = scope === "global";
  const isWorkspaceConfig = mode === "workspace-config";
  const [workspaceCaps, setWorkspaceCaps] = useState<WorkspaceCapabilityItem[]>([]);
  const [availableCaps, setAvailableCaps] = useState<CapabilityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterKind, setFilterKind] = useState<FilterKind>("all");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");
  const [selectedCapId, setSelectedCapId] = useState<string | null>(null);

  // Skill preview
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewEntry, setPreviewEntry] = useState<SkillEntryResponse | null>(null);

  // MCP config
  const [mcpConfigOpen, setMcpConfigOpen] = useState(false);
  const [mcpConfigDraft, setMcpConfigDraft] = useState("{}");
  const [mcpConfigError, setMcpConfigError] = useState<string | null>(null);

  // Source tree preview
  const [sourceTreeLoading, setSourceTreeLoading] = useState(false);
  const [sourceTreeEntries, setSourceTreeEntries] = useState<CapabilitySourceTreeEntry[]>([]);
  const [selectedSourceFile, setSelectedSourceFile] = useState<string>("");
  const [sourceFileLoading, setSourceFileLoading] = useState(false);
  const [sourceFileContent, setSourceFileContent] = useState<string | null>(null);

  // Create dialogs
  const [skillMarketOpen, setSkillMarketOpen] = useState(false);
  const [mcpMarketOpen, setMcpMarketOpen] = useState(false);
  const [rolesMarketOpen, setRolesMarketOpen] = useState(false);

  const { getSkillEntryContent } = useSkills();

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const ws = await (isGlobal
        ? listGlobalCapabilities()
        : listWorkspaceCapabilities(workspaceId));
      setWorkspaceCaps(ws);
    } catch (err) {
      console.error("加载工作区能力失败:", err);
      setWorkspaceCaps([]);
    }
    try {
      const avail = await listAvailableCapabilities();
      setAvailableCaps(avail);
    } catch (err) {
      console.error("加载可用能力失败:", err);
      setAvailableCaps([]);
    }
    setLoading(false);
  }, [workspaceId, isGlobal]);

  useEffect(() => {
    void load();
  }, [load]);

  const allItems = useMemo(() => {
    const items: Array<WorkspaceCapabilityItem | (CapabilityItem & { status: string })> = [];
    for (const cap of workspaceCaps) {
      items.push(cap);
    }
    if (!isWorkspaceConfig) {
      const installed = new Set(workspaceCaps.map((c) => c.capability_id));
      for (const cap of availableCaps) {
        if (!installed.has(cap.capability_id)) {
          items.push({ ...cap, status: "available" });
        }
      }
    }
    return items;
  }, [workspaceCaps, availableCaps, isWorkspaceConfig]);

  const filteredItems = useMemo(() => {
    return allItems.filter((item) => {
      if (filterKind !== "all" && item.kind !== filterKind) return false;
      if (filterStatus !== "all") {
        if (filterStatus === "enabled") {
          if (!("enabled" in item) || !item.enabled) return false;
        } else if (filterStatus === "disabled") {
          if (!("enabled" in item) || item.enabled) return false;
        } else if (filterStatus === "available") {
          if ("enabled" in item) return false;
        }
      }
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const text = (
          (item.display_name || "") +
          " " +
          (item.description || "") +
          " " +
          item.capability_id
        ).toLowerCase();
        if (!text.includes(q)) return false;
      }
      return true;
    });
  }, [allItems, filterKind, filterStatus, searchQuery]);

  const selectedCap = useMemo(() => {
    return (
      filteredItems.find((c) => c.capability_id === selectedCapId) ?? filteredItems[0] ?? null
    );
  }, [filteredItems, selectedCapId]);

  const prevFilteredItemsRef = useRef(filteredItems);
  useEffect(() => {
    if (filteredItems === prevFilteredItemsRef.current) return;
    prevFilteredItemsRef.current = filteredItems;
    if (filteredItems.length > 0 && !filteredItems.find((c) => c.capability_id === selectedCapId)) {
      setSelectedCapId(filteredItems[0].capability_id);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filteredItems]);

  const isWorkspaceCap = (cap: unknown): cap is WorkspaceCapabilityItem =>
    typeof cap === "object" && cap !== null && "enabled" in cap;
  const canToggle = (cap: WorkspaceCapabilityItem) => cap.kind !== "skill_pack";

  const handleInstall = async (capId: string, config?: Record<string, unknown>) => {
    setProcessingId(capId);
    try {
      if (isGlobal) {
        await installGlobalCapability(capId, config);
      } else {
        await installCapability(workspaceId, capId, config);
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handleUninstall = async (capId: string) => {
    setProcessingId(capId);
    try {
      if (isGlobal) {
        await uninstallGlobalCapability(capId);
      } else {
        await uninstallCapability(workspaceId, capId);
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handleToggle = async (capId: string, enabled: boolean) => {
    setProcessingId(capId);
    try {
      if (enabled) {
        if (isGlobal) {
          await deactivateGlobalCapability(capId);
        } else {
          await deactivateCapability(workspaceId, capId);
        }
      } else {
        if (isGlobal) {
          await activateGlobalCapability(capId);
        } else {
          await activateCapability(workspaceId, capId);
        }
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handleVerify = async (capId: string) => {
    setProcessingId(capId);
    try {
      if (isGlobal) {
        await verifyGlobalCapability(capId);
      } else {
        await verifyCapability(workspaceId, capId);
      }
      await load();
    } finally {
      setProcessingId(null);
    }
  };

  const handlePreview = async (skillName: string) => {
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewEntry(null);
    try {
      const entry = await getSkillEntryContent(workspaceId, skillName);
      setPreviewEntry(entry);
    } catch (err) {
      console.error("加载技能预览失败:", err);
      setPreviewEntry(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Source tree
  const handleSelectSourceFile = useCallback(async (path: string) => {
    setSelectedSourceFile(path);
    setSourceFileLoading(true);
    setSourceFileContent(null);
    try {
      const capId = selectedCap?.capability_id;
      if (!capId) return;
      const res = await getCapabilitySourceFile(capId, path);
      setSourceFileContent(res?.content ?? null);
    } catch (err) {
      console.error("加载源文件失败:", err);
      setSourceFileContent(null);
    } finally {
      setSourceFileLoading(false);
    }
  }, [selectedCap]);

  useEffect(() => {
    if (!selectedCap || (selectedCap.kind !== "skill_pack" && selectedCap.kind !== "subagent")) {
      setSourceTreeEntries([]);
      setSelectedSourceFile("");
      setSourceFileContent(null);
      return;
    }
    setSourceTreeLoading(true);
    setSourceTreeEntries([]);
    setSelectedSourceFile("");
    setSourceFileContent(null);
    void (async () => {
      try {
        const res = await listCapabilitySourceTree(selectedCap.capability_id);
        const entries = res?.entries ?? [];
        setSourceTreeEntries(entries);

        // Auto-select README.md first, fallback to entry file
        const fallbackFile = selectedCap.kind === "subagent" ? "prompt.md" : "SKILL.md";
        const readmeEntry = entries.find((e) => e.path === "README.md" && !e.is_dir);
        const entry = readmeEntry ?? entries.find((e) => e.path === fallbackFile && !e.is_dir);
        if (entry) {
          setSelectedSourceFile(entry.path);
          setSourceFileLoading(true);
          try {
            const fileRes = await getCapabilitySourceFile(selectedCap.capability_id, entry.path);
            setSourceFileContent(fileRes?.content ?? "暂无内容");
          } catch (err) {
            console.error("加载源文件失败:", err);
            setSourceFileContent(null);
          } finally {
            setSourceFileLoading(false);
          }
        }
      } catch (err) {
        console.error("加载源树失败:", err);
        setSourceTreeEntries([]);
      } finally {
        setSourceTreeLoading(false);
      }
    })();
  }, [selectedCap]);

  const openMcpConfig = (cap: CapabilityItem) => {
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
    if (!selectedCap || selectedCap.kind !== "mcp_server" || isWorkspaceCap(selectedCap)) return;
    let config: Record<string, unknown>;
    try {
      config = JSON.parse(mcpConfigDraft);
    } catch (e) {
      setMcpConfigError(e instanceof Error ? e.message : "JSON 格式错误");
      return;
    }
    setMcpConfigOpen(false);
    await handleInstall(selectedCap.capability_id, config);
  };

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full">
      {/* 左侧列表 */}
      <div className="w-56 shrink-0 border-r flex flex-col">
        {/* 搜索 */}
        <div className="border-b px-3 py-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="搜索能力..."
              className="h-8 pl-8 pr-7 text-xs"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* 创建入口 */}
        <div className="border-b px-3 py-2 flex flex-wrap gap-1.5">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 gap-1 text-[11px]"
            onClick={() => setSkillMarketOpen(true)}
          >
            <Plus className="h-3 w-3" />
            创建技能
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 gap-1 text-[11px]"
            onClick={() => setMcpMarketOpen(true)}
          >
            <Plus className="h-3 w-3" />
            添加连接器
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-7 gap-1 text-[11px]"
            onClick={() => setRolesMarketOpen(true)}
          >
            <Plus className="h-3 w-3" />
            新建专家
          </Button>
        </div>

        {/* 筛选 */}
        <div className="border-b px-3 py-2 space-y-2">
          <div className="flex flex-wrap gap-1">
            {KIND_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilterKind(f.id)}
                className={cn(
                  "rounded px-2 py-0.5 text-[11px] transition-colors",
                  filterKind === f.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1">
            {(isWorkspaceConfig ? STATUS_FILTERS.filter(f => f.id !== "available") : STATUS_FILTERS).map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setFilterStatus(f.id)}
                className={cn(
                  "rounded px-2 py-0.5 text-[11px] transition-colors",
                  filterStatus === f.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted text-muted-foreground hover:bg-muted/80 hover:text-foreground"
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        {/* 列表 */}
        <div className="flex-1 overflow-y-auto divide-y divide-border">
          {filteredItems.map((cap) => {
            const capId = cap.capability_id;
            const ws = isWorkspaceCap(cap);
            const status = ws ? cap.status : "available";
            const active = selectedCap?.capability_id === capId;
            return (
              <div
                key={capId}
                className={cn(
                  "flex w-full items-center gap-2 px-3 py-2 text-sm cursor-pointer transition-colors",
                  active ? "bg-primary/5" : "hover:bg-muted/50"
                )}
                onClick={() => setSelectedCapId(capId)}
              >
                {STATUS_ICON[status] ?? STATUS_ICON.available}
                <div className="flex-1 min-w-0">
                  <div className="truncate text-xs font-medium text-foreground">
                    {cap.display_name || capId}
                  </div>
                  <div className="text-[11px] text-muted-foreground truncate">
                    {KIND_LABEL[cap.kind] ?? cap.kind} · {STATUS_LABEL[status] ?? status}
                  </div>
                </div>
                {ws && canToggle(cap) && (
                  <Switch
                    checked={cap.enabled}
                    className="h-4 w-7 scale-75"
                    disabled={processingId === capId}
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleToggle(capId, cap.enabled);
                    }}
                  />
                )}
              </div>
            );
          })}
          {filteredItems.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">
              {searchQuery || filterKind !== "all" || filterStatus !== "all" ? (
                "没有符合条件的能力"
              ) : isWorkspaceConfig ? (
                <div className="space-y-2">
                  <p>当前工作区未安装任何能力</p>
                  <p className="text-[10px] opacity-70">请去全局设置中安装</p>
                </div>
              ) : (
                "暂无能力"
              )}
            </div>
          )}
        </div>

        {/* 统计 */}
        <div className="shrink-0 border-t px-3 py-1.5 text-[11px] text-muted-foreground flex items-center justify-between">
          <span>共 {filteredItems.length} 项</span>
          <Button variant="ghost" size="icon" className="h-5 w-5" onClick={() => void load()}>
            <RefreshCw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      {/* 右侧详情 */}
      <div className="min-w-0 flex-1 overflow-y-auto">
        {selectedCap ? (
          <div className="space-y-4 p-4">
            {/* 头部 */}
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h3 className="text-lg font-medium">
                    {selectedCap.display_name || selectedCap.capability_id}
                  </h3>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                    <Badge variant="outline" className="text-[10px]">
                      {KIND_LABEL[selectedCap.kind] ?? selectedCap.kind}
                    </Badge>
                    {(selectedCap as CapabilityItem).version && (
                      <span>v{(selectedCap as CapabilityItem).version}</span>
                    )}
                    {(selectedCap as WorkspaceCapabilityItem).source && (
                      <span>{(selectedCap as WorkspaceCapabilityItem).source}</span>
                    )}
                  </div>
                </div>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                  {isWorkspaceCap(selectedCap) ? (
                    <>
                      {selectedCap.kind === "skill_pack" && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="shrink-0"
                          onClick={() => void handlePreview(selectedCap.capability_id)}
                          disabled={processingId === selectedCap.capability_id}
                        >
                          <Eye className="mr-1 h-3 w-3" />
                          预览
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="outline"
                        className="shrink-0"
                        onClick={() => void handleVerify(selectedCap.capability_id)}
                        disabled={processingId === selectedCap.capability_id}
                      >
                        {processingId === selectedCap.capability_id ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <RefreshCw className="mr-1 h-3 w-3" />
                        )}
                        验活
                      </Button>
                      {canToggle(selectedCap) && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="shrink-0"
                          onClick={() =>
                            void handleToggle(selectedCap.capability_id, selectedCap.enabled)
                          }
                          disabled={processingId === selectedCap.capability_id}
                        >
                          {selectedCap.enabled ? "禁用" : "激活"}
                        </Button>
                      )}
                      {!isWorkspaceConfig && (
                        <Button
                          size="sm"
                          variant="destructive"
                          className="shrink-0"
                          onClick={() => void handleUninstall(selectedCap.capability_id)}
                          disabled={processingId === selectedCap.capability_id}
                        >
                          <Trash2 className="mr-1 h-3 w-3" />
                          卸载
                        </Button>
                      )}
                    </>
                  ) : (
                    <>
                      {selectedCap.kind === "mcp_server" &&
                        Object.keys(selectedCap.config_schema || {}).length > 0 && (
                          <Button
                            size="sm"
                            variant="outline"
                            className="shrink-0"
                            onClick={() => openMcpConfig(selectedCap as CapabilityItem)}
                            disabled={processingId === selectedCap.capability_id}
                          >
                            <FileJson className="mr-1 h-3 w-3" />
                            配置并安装
                          </Button>
                        )}
                      <Button
                        size="sm"
                        className="shrink-0"
                        onClick={() => void handleInstall(selectedCap.capability_id)}
                        disabled={processingId === selectedCap.capability_id}
                      >
                        {processingId === selectedCap.capability_id ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : null}
                        安装
                      </Button>
                    </>
                  )}
                </div>
              </div>
              {isWorkspaceCap(selectedCap) && (
                <div
                  className={cn(
                    "inline-flex max-w-full items-center gap-1.5 self-start rounded-md border px-2 py-1 text-xs",
                    STATUS_BADGE_CLASS[selectedCap.status] ?? STATUS_BADGE_CLASS.available
                  )}
                >
                  {STATUS_ICON[selectedCap.status] ?? STATUS_ICON.available}
                  <span className="truncate">
                    {STATUS_LABEL[selectedCap.status] ?? selectedCap.status}
                  </span>
                </div>
              )}
            </div>

            {/* 描述 */}
            {selectedCap.description && (
              <p className="break-words text-sm leading-5 text-muted-foreground">
                {selectedCap.description}
              </p>
            )}

            {/* 错误信息 */}
            {isWorkspaceCap(selectedCap) && selectedCap.error_message && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                {selectedCap.error_message}
              </div>
            )}

            {/* 工具列表 */}
            {!isWorkspaceCap(selectedCap) &&
              (selectedCap as CapabilityItem).tool_names &&
              (selectedCap as CapabilityItem).tool_names.length > 0 && (
                <div className="space-y-1.5">
                  <div className="text-xs font-medium text-muted-foreground">
                    包含工具 ({(selectedCap as CapabilityItem).tool_names.length})
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {(selectedCap as CapabilityItem).tool_names.map((t) => (
                      <Badge key={t} variant="secondary" className="text-[10px]">
                        {t.split(":").pop()}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

            {/* 能力源文件树 + 预览 */}
            {(selectedCap.kind === "skill_pack" || selectedCap.kind === "subagent") && (
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
                  <div
                    className="flex gap-2 rounded-md border border-border bg-muted/20 overflow-hidden"
                    style={{ minHeight: "200px", maxHeight: "500px" }}
                  >
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

            {/* MCP Config Schema */}
            {!isWorkspaceCap(selectedCap) &&
              selectedCap.kind === "mcp_server" &&
              selectedCap.config_schema && (
                <div className="space-y-2">
                  <div className="text-xs font-medium text-muted-foreground">配置说明</div>
                  <pre className="overflow-auto rounded-md border border-border bg-muted/40 p-3 text-[11px] leading-5 text-foreground">
                    {JSON.stringify(selectedCap.config_schema, null, 2)}
                  </pre>
                </div>
              )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            选择一项能力查看详情
          </div>
        )}
      </div>

      {/* Skill Preview Dialog */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="h-[90vh] max-h-[90vh] max-w-2xl overflow-hidden flex flex-col gap-0 bg-background">
          <DialogHeader className="shrink-0">
            <DialogTitle>
              {previewEntry?.display_name || previewEntry?.name || "技能预览"}
            </DialogTitle>
            <DialogDescription>
              {previewEntry ? previewEntry.entry_relative_path : "技能入口文档"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4">
            {previewLoading ? (
              <div className="flex items-center justify-center py-10 text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                正在加载...
              </div>
            ) : previewEntry ? (
              <pre className="overflow-auto rounded-xl border border-border bg-muted/60 p-4 text-xs leading-6 text-foreground">
                {previewEntry.content || "暂无内容"}
              </pre>
            ) : (
              <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                无法加载该技能的预览内容。
              </div>
            )}
          </div>
          <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 text-xs"
              onClick={() => setPreviewOpen(false)}
            >
              关闭
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* MCP Config Dialog */}
      <Dialog open={mcpConfigOpen} onOpenChange={setMcpConfigOpen}>
        <DialogContent className="h-[90vh] max-h-[90vh] max-w-lg overflow-hidden flex flex-col gap-0 bg-background">
          <DialogHeader className="shrink-0">
            <DialogTitle>配置并安装</DialogTitle>
            <DialogDescription>
              {selectedCap?.display_name || selectedCap?.capability_id || "MCP 服务器"}
            </DialogDescription>
          </DialogHeader>
          <div className="flex-1 overflow-y-auto min-h-0 space-y-4">
            {selectedCap && !isWorkspaceCap(selectedCap) && selectedCap.config_schema && (
              <div className="space-y-1">
                <div className="text-xs font-medium text-muted-foreground">配置说明</div>
                <pre className="overflow-auto rounded-md border border-border bg-muted/40 p-2 text-[11px] leading-4 text-foreground">
                  {JSON.stringify(selectedCap.config_schema, null, 2)}
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

      <SkillMarketDialog
        open={skillMarketOpen}
        onOpenChange={(open) => {
          setSkillMarketOpen(open);
          if (!open) void load();
        }}
        workspaceId={isGlobal ? null : workspaceId}
      />

      <MCPMarketDialog
        open={mcpMarketOpen}
        onOpenChange={(open) => {
          setMcpMarketOpen(open);
          if (!open) void load();
        }}
      />

      <CollaborationRolesSettingsDialog
        open={rolesMarketOpen}
        onOpenChange={(open) => {
          setRolesMarketOpen(open);
          if (!open) void load();
        }}
        workspaceId={isGlobal ? null : workspaceId}
      />
    </div>
  );
}
