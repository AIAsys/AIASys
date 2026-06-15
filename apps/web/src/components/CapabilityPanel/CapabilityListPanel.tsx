import { useEffect, useMemo, useState, useCallback } from "react";
import {
  Loader2,
  RefreshCw,
  CheckCircle2,
  XCircle,
  CircleOff,
  Package,
  Search,
  X,
  Trash2,
  Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import {
  listWorkspaceCapabilities,
  listAvailableCapabilities,
  installCapability,
  uninstallCapability,
  activateCapability,
  deactivateCapability,
  listGlobalCapabilities,
  installGlobalCapability,
  uninstallGlobalCapability,
  activateGlobalCapability,
  deactivateGlobalCapability,
  type WorkspaceCapabilityItem,
  type CapabilityItem,
} from "@/lib/api/capabilities";

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

export interface CapabilityListPanelProps {
  workspaceId: string;
  scope?: "workspace" | "global";
  mode?: "full" | "workspace-config";
  selectedCapId?: string | null;
  onSelectCap: (capId: string, displayName: string) => void;
}

export function CapabilityListPanel({
  workspaceId,
  scope = "workspace",
  mode = "full",
  selectedCapId,
  onSelectCap,
}: CapabilityListPanelProps) {
  const isGlobal = scope === "global";
  const isWorkspaceConfig = mode === "workspace-config";
  const [workspaceCaps, setWorkspaceCaps] = useState<WorkspaceCapabilityItem[]>([]);
  const [availableCaps, setAvailableCaps] = useState<CapabilityItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [processingId, setProcessingId] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterKind, setFilterKind] = useState<FilterKind>("all");
  const [filterStatus, setFilterStatus] = useState<FilterStatus>("all");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const ws = await (isGlobal
        ? listGlobalCapabilities()
        : listWorkspaceCapabilities(workspaceId));
      setWorkspaceCaps(ws);
    } catch {
      setWorkspaceCaps([]);
    }
    if (!isWorkspaceConfig) {
      try {
        const avail = await listAvailableCapabilities();
        setAvailableCaps(avail);
      } catch {
        setAvailableCaps([]);
      }
    }
    setLoading(false);
  }, [workspaceId, isGlobal, isWorkspaceConfig]);

  useEffect(() => {
    void load();
  }, [load]);

  const allItems = useMemo(() => {
    const items: Array<WorkspaceCapabilityItem | (CapabilityItem & { status: string })> = [];
    for (const cap of workspaceCaps) items.push(cap);
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

  const isWorkspaceCap = (cap: unknown): cap is WorkspaceCapabilityItem =>
    typeof cap === "object" && cap !== null && "enabled" in cap;
  const canToggle = (_cap: WorkspaceCapabilityItem) => true;

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

  const handleInstall = async (capId: string) => {
    setProcessingId(capId);
    try {
      if (isGlobal) {
        await installGlobalCapability(capId);
      } else {
        await installCapability(workspaceId, capId);
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

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
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
          const status = ws ? (cap.enabled ? cap.status : "disabled") : "available";
          const active = selectedCapId === capId;
          return (
            <div
              key={capId}
              className={cn(
                "flex w-full items-start gap-2 px-3 py-2 text-sm cursor-pointer transition-colors",
                active ? "bg-primary/5" : "hover:bg-muted/50"
              )}
              onClick={() => onSelectCap(capId, cap.display_name || capId)}
            >
              {STATUS_ICON[status] ?? STATUS_ICON.available}
              <div className="flex-1 min-w-0">
                <div className="flex items-start justify-between gap-2">
                  <div className="truncate text-xs font-medium text-foreground">
                    {cap.display_name || capId}
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
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
                    {ws ? (
                      !isWorkspaceConfig ? (
                        <button
                          type="button"
                          title="卸载"
                          disabled={processingId === capId}
                          onClick={(e) => {
                            e.stopPropagation();
                            void handleUninstall(capId);
                          }}
                          className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive disabled:opacity-50"
                        >
                          {processingId === capId ? (
                            <Loader2 className="h-3 w-3 animate-spin" />
                          ) : (
                            <Trash2 className="h-3 w-3" />
                          )}
                        </button>
                      ) : null
                    ) : (
                      <button
                        type="button"
                        title="安装"
                        disabled={processingId === capId}
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleInstall(capId);
                        }}
                        className="inline-flex h-6 items-center justify-center rounded bg-primary px-2 text-[10px] font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
                      >
                        {processingId === capId ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : (
                          <>
                            <Download className="mr-0.5 h-3 w-3" />
                            安装
                          </>
                        )}
                      </button>
                    )}
                  </div>
                </div>
                <div className="text-[11px] text-muted-foreground truncate">
                  {KIND_LABEL[cap.kind] ?? cap.kind} · {STATUS_LABEL[status] ?? status}
                </div>
              </div>
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
  );
}
