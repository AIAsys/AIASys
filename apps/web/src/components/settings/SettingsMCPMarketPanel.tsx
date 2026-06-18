import { useState, useMemo, useCallback } from "react";

const DEFAULT_MCP_HOST = "http://localhost:8080";
import {
  Loader2,
  Package,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ServerCog,
  Store,
  Trash2,
  Wrench,
} from "lucide-react";
import { ExternalMCPMarketPanel } from "@/components/settings/ExternalMCPMarketPanel";
import { useSessionMCPManager, type MCPStoreItem } from "@/hooks/useSessionMCPManager";
import { testMCPConnection, updateMCPStoreEnv } from "@/lib/api/mcp";
import type { MCPToolInfo } from "@/lib/api/mcp";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";

type SettingsMCPTab = "builtin" | "external";

const TABS: Array<{
  id: SettingsMCPTab;
  label: string;
  description: string;
  icon: typeof ServerCog;
}> = [
  {
    id: "builtin",
    label: "连接器仓库",
    description: "系统预装和用户添加的连接器",
    icon: ServerCog,
  },
  {
    id: "external",
    label: "外部连接器市场",
    description: "从外部来源导入连接器",
    icon: Store,
  },
];

interface SettingsMCPMarketPanelProps {
  activeTab?: SettingsMCPTab;
  onActiveTabChange?: (tab: SettingsMCPTab) => void;
  hideTabBar?: boolean;
}

export function SettingsMCPMarketPanel({
  activeTab: controlledActiveTab,
  onActiveTabChange,
  hideTabBar = false,
}: SettingsMCPMarketPanelProps = {}) {
  const [internalActiveTab, setInternalActiveTab] = useState<SettingsMCPTab>("builtin");
  const activeTab = controlledActiveTab !== undefined ? controlledActiveTab : internalActiveTab;
  const setActiveTab = (tab: SettingsMCPTab) => {
    if (onActiveTabChange) {
      onActiveTabChange(tab);
    } else {
      setInternalActiveTab(tab);
    }
  };
  const [searchQuery, setSearchQuery] = useState("");
  const [testingName, setTestingName] = useState<string | null>(null);
  const [testMessages, setTestMessages] = useState<Record<string, string>>({});
  const [testToolCounts, setTestToolCounts] = useState<Record<string, number>>({});
  const [detailServer, setDetailServer] = useState<string | null>(null);
  const [detailTestingName, setDetailTestingName] = useState<string | null>(null);
  const [detailTestMessages, setDetailTestMessages] = useState<Record<string, string>>({});
  const [detailToolsMap, setDetailToolsMap] = useState<Record<string, MCPToolInfo[]>>({});
  const [detailEditingEnv, setDetailEditingEnv] = useState<Record<string, string>>({});
  const [detailEnvSaving, setDetailEnvSaving] = useState(false);
  const [processingName, setProcessingName] = useState<string | null>(null);
  const [addDialogOpen, setAddDialogOpen] = useState(false);
  const [editingServerName, setEditingServerName] = useState<string | null>(null);
  const [addForm, setAddForm] = useState({
    name: "",
    type: "streamable-http" as "streamable-http" | "stdio" | "sse",
    url: "",
    command: "",
    args: "",
    description: "",
  });
  const [addSubmitting, setAddSubmitting] = useState(false);

  const {
    storeServers,
    storeLoading,
    error,
    refreshStore,
    addStoreServer,
    updateStoreServer,
    removeStoreServer,
  } = useSessionMCPManager({ enabled: true });

  const filteredStoreServers = useMemo(() => {
    if (!searchQuery.trim()) return storeServers;
    const q = searchQuery.toLowerCase();
    return storeServers.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        (s.display_name || "").toLowerCase().includes(q) ||
        (s.description || "").toLowerCase().includes(q)
    );
  }, [storeServers, searchQuery]);

  const systemDefaultServers = useMemo(
    () => filteredStoreServers.filter((s) => s.is_system_default),
    [filteredStoreServers]
  );
  const userServers = useMemo(
    () => filteredStoreServers.filter((s) => !s.is_system_default),
    [filteredStoreServers]
  );

  const handleRemove = async (name: string) => {
    setProcessingName(name);
    await removeStoreServer(name);
    setProcessingName(null);
  };

  const handleTest = async (name: string) => {
    setTestingName(name);
    try {
      const result = await testMCPConnection(name);
      const message =
        result.status === "connected"
          ? `连接成功，发现 ${result.tools_count} 个工具`
          : result.error_message || "连接失败";
      setTestMessages((prev) => ({ ...prev, [name]: message }));
      setTestToolCounts((prev) => ({ ...prev, [name]: result.tools_count || 0 }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "连接失败";
      setTestMessages((prev) => ({ ...prev, [name]: message }));
    } finally {
      setTestingName(null);
    }
  };

  const handleTestInDialog = useCallback(async (name: string) => {
    setDetailTestingName(name);
    try {
      const result = await testMCPConnection(name);
      const message =
        result.status === "connected"
          ? `连接成功，发现 ${result.tools_count} 个工具`
          : result.error_message || "连接失败";
      setDetailTestMessages((prev) => ({ ...prev, [name]: message }));
      if (result.tools && result.tools.length > 0) {
        setDetailToolsMap((prev) => ({ ...prev, [name]: result.tools! }));
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "连接失败";
      setDetailTestMessages((prev) => ({ ...prev, [name]: message }));
    } finally {
      setDetailTestingName(null);
    }
  }, []);

  const handleSaveEnv = useCallback(async (serverName: string) => {
    setDetailEnvSaving(true);
    try {
      await updateMCPStoreEnv(serverName, detailEditingEnv);
      await refreshStore();
      setDetailTestMessages((prev) => ({ ...prev, [serverName]: "环境变量已保存" }));
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存失败";
      setDetailTestMessages((prev) => ({ ...prev, [serverName]: `保存失败：${message}` }));
    } finally {
      setDetailEnvSaving(false);
    }
  }, [detailEditingEnv, refreshStore]);

  const handleAddSubmit = async () => {
    if (!addForm.name.trim()) return;
    setAddSubmitting(true);
    try {
      const config: Record<string, unknown> = {
        name: addForm.name.trim(),
        type: addForm.type,
        description: addForm.description.trim() || undefined,
      };
      if (addForm.type === "streamable-http" || addForm.type === "sse") {
        config.url = addForm.url.trim() || undefined;
      }
      if (addForm.type === "stdio") {
        config.command = addForm.command.trim() || undefined;
        config.args = addForm.args.trim()
          ? addForm.args.trim().split(/\s+/)
          : undefined;
      }
      const isEditing = editingServerName !== null;
      const success = isEditing
        ? await updateStoreServer(config as Parameters<typeof updateStoreServer>[0])
        : await addStoreServer(config as Parameters<typeof addStoreServer>[0]);
      if (success) {
        setAddDialogOpen(false);
        setEditingServerName(null);
        void refreshStore();
      }
    } finally {
      setAddSubmitting(false);
    }
  };

  const openEditDialog = (server: MCPStoreItem) => {
    setEditingServerName(server.name);
    setAddForm({
      name: server.name,
      type: (server.type as "streamable-http" | "stdio" | "sse") || "streamable-http",
      url: server.url || "",
      command: server.command || "",
      args: server.args?.join(" ") || "",
      description: server.description || "",
    });
    setAddDialogOpen(true);
  };

  const openAddDialog = () => {
    setEditingServerName(null);
    setAddForm({
      name: "",
      type: "streamable-http",
      url: "",
      command: "",
      args: "",
      description: "",
    });
    setAddDialogOpen(true);
  };

  const detailItem = storeServers.find((s) => s.name === detailServer) || null;

  const renderServerCard = (server: MCPStoreItem) => {
    const isProcessing = processingName === server.name;
    const isTesting = testingName === server.name;
    const testMsg = testMessages[server.name];
    const toolCount = testToolCounts[server.name];

    return (
      <div
        key={server.name}
        className={`flex flex-col rounded-xl border border-border p-4 transition-all duration-200 hover:border-tertiary/30 hover:bg-card ${
          server.is_system_default ? "bg-muted/30" : "bg-muted/50"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <div className="truncate text-sm font-semibold text-foreground">
                {server.display_name || server.name}
              </div>
              {typeof toolCount === "number" && toolCount > 0 && (
                <Badge variant="secondary" className="text-[10px] gap-0.5">
                  <Wrench className="h-2.5 w-2.5" />
                  {toolCount}
                </Badge>
              )}
            </div>
            <div className="mt-1 flex flex-wrap gap-1.5">
              <Badge variant="outline" className="text-[10px]">{server.type}</Badge>
              {server.is_system_default && (
                <Badge variant="outline" className="text-[10px]">系统</Badge>
              )}
            </div>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-1.5">
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => void handleTest(server.name)}
            disabled={isTesting}
          >
            {isTesting ? (
              <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
            ) : null}
            检查
          </Button>

          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="h-8 text-xs"
            onClick={() => setDetailServer(server.name)}
          >
            详情
          </Button>

          {!server.is_system_default && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground"
              onClick={() => openEditDialog(server)}
              disabled={isProcessing}
              title="编辑"
            >
              <Pencil className="h-4 w-4" />
            </Button>
          )}

          {!server.is_system_default && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0 text-muted-foreground hover:text-destructive"
              onClick={() => void handleRemove(server.name)}
              disabled={isProcessing}
              title="删除"
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>

      <p className="mt-2 line-clamp-3 text-xs leading-5 text-muted-foreground">
        {(server as MCPStoreItem).description || "暂无说明"}
      </p>

      {testMsg && (
        <div
          className={`mt-2 rounded-lg border p-2 text-xs ${
            testMsg.includes("成功")
              ? "border-success/20 bg-success-container text-on-success-container"
              : "border-warning/20 bg-warning-container text-on-warning-container"
          }`}
        >
          {testMsg}
        </div>
      )}
      </div>
    );
  };

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {!hideTabBar && (
        <div className="shrink-0 px-1 pt-1 pb-2">
          <div className="flex rounded-md bg-muted p-0.5">
            {TABS.map((tab) => {
              const active = tab.id === activeTab;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex-1 px-3 py-1.5 text-xs text-center rounded transition-colors",
                    active
                      ? "bg-background text-foreground shadow-sm font-medium"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-hidden">
        {activeTab === "builtin" && (
          <div className="flex h-full flex-col overflow-hidden">
            {/* Toolbar */}
            <div className="flex items-center gap-3 border-b border-border px-5 py-3">
              <div className="relative max-w-sm min-w-[180px] flex-1">
                <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="搜索连接器..."
                  className="pl-9 h-9"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </div>
              {searchQuery && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSearchQuery("")}
                >
                  清除
                </Button>
              )}
              <div className="flex-1" />
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-9 gap-1 text-xs"
                onClick={() => openAddDialog()}
              >
                <Plus className="h-3.5 w-3.5" />
                添加
              </Button>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void refreshStore()}
                disabled={storeLoading}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
            </div>

            <ScrollArea className="flex-1">
              <div className="p-5 space-y-6">
                {error && (
                  <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                    {error}
                  </div>
                )}

                {storeLoading && filteredStoreServers.length === 0 && (
                  <div className="flex h-48 items-center justify-center">
                    <Loader2 className="h-8 w-8 animate-spin text-tertiary" />
                    <span className="ml-3 text-muted-foreground">
                      加载中...
                    </span>
                  </div>
                )}

                {/* System defaults */}
                {systemDefaultServers.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        系统默认
                      </div>
                      <div className="h-px flex-1 bg-border" />
                      <span className="text-[11px] text-muted-foreground">
                        {systemDefaultServers.length} 个
                      </span>
                    </div>
                    <div
                      className="grid gap-3"
                      style={{
                        gridTemplateColumns:
                          "repeat(auto-fill, minmax(260px, 1fr))",
                      }}
                    >
                      {systemDefaultServers.map(renderServerCard)}
                    </div>
                  </div>
                )}

                {/* User-added */}
                {userServers.length > 0 && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2">
                      <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        用户添加
                      </div>
                      <div className="h-px flex-1 bg-border" />
                      <span className="text-[11px] text-muted-foreground">
                        {userServers.length} 个
                      </span>
                    </div>
                    <div
                      className="grid gap-3"
                      style={{
                        gridTemplateColumns:
                          "repeat(auto-fill, minmax(260px, 1fr))",
                      }}
                    >
                      {userServers.map(renderServerCard)}
                    </div>
                  </div>
                )}

                {!storeLoading && filteredStoreServers.length === 0 && (
                  <div className="py-16 text-center">
                    <Package className="mx-auto mb-4 h-10 w-10 text-muted-foreground/30" />
                    <p className="text-sm text-muted-foreground">
                      {searchQuery
                        ? "没有找到匹配的连接器"
                        : "暂无可用连接器"}
                    </p>
                  </div>
                )}
              </div>
            </ScrollArea>
          </div>
        )}

        {activeTab === "external" && (
          <div className="flex h-full flex-col overflow-hidden p-5">
            <ExternalMCPMarketPanel
              onImported={() => {
                void refreshStore();
              }}
            />
          </div>
        )}
      </div>

      {/* Detail Dialog */}
      <Dialog
        open={Boolean(detailServer)}
        onOpenChange={(open) => {
          if (!open) {
            setDetailServer(null);
            setDetailEditingEnv({});
          } else {
            const item = storeServers.find((s) => s.name === detailServer);
            if (item) {
              const base = { ...(item.env || {}) };
              // 如果有 env_fields，把未填的字段用默认值初始化
              for (const field of item.env_fields || []) {
                if (!(field.name in base) && field.default_value !== undefined) {
                  base[field.name] = field.default_value;
                }
              }
              setDetailEditingEnv(base);
            }
          }
        }}
      >
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-hidden flex flex-col bg-background">
          {detailItem ? (
            <>
              <DialogHeader className="shrink-0">
                <DialogTitle>{detailItem.display_name || detailItem.name}</DialogTitle>
                <DialogDescription>连接器详情</DialogDescription>
              </DialogHeader>

              <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4">
                {/* Tags + Description */}
                <div className="rounded-xl border border-border bg-muted/50 p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {detailItem.is_system_default ? "系统默认" : "我的默认"}
                    </Badge>
                    <Badge variant="outline" className="text-[10px]">
                      {detailItem.type}
                    </Badge>
                    {detailItem.enabled_tools && detailItem.enabled_tools.length > 0 && (
                      <Badge variant="secondary" className="text-[10px]">
                        {detailItem.enabled_tools.length} 个工具已启用
                      </Badge>
                    )}
                  </div>
                  <p className="mt-2 text-sm leading-6 text-muted-foreground">
                    {detailItem.description || "暂无说明"}
                  </p>
                </div>

                {/* Connection / Import Template */}
                <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                  <div className="text-sm font-medium text-foreground">
                    {detailItem.type === "stdio" ? "导入模板" : "连接信息"}
                  </div>
                  {detailItem.type === "stdio" ? (
                    <div className="rounded-lg border border-border bg-muted/50 p-3 space-y-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">{detailItem.name}</Badge>
                        <Badge variant="secondary" className="text-[10px]">stdio</Badge>
                      </div>
                      <div className="font-mono text-xs text-muted-foreground break-all">
                        {detailItem.command || "未配置"} {detailItem.args?.join(" ") || ""}
                      </div>
                      {detailItem.env_fields && detailItem.env_fields.length > 0 && (
                        <div className="text-[11px] text-muted-foreground">
                          env: {detailItem.env_fields.map(f => f.name).join(", ")}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div>
                      <div className="text-[11px] text-muted-foreground">URL</div>
                      <div className="mt-0.5 font-mono text-xs break-all">
                        {detailItem.url || "未配置"}
                      </div>
                    </div>
                  )}
                  {detailItem.headers && Object.keys(detailItem.headers).length > 0 && (
                    <div>
                      <div className="text-[11px] text-muted-foreground">Headers</div>
                      <div className="mt-1 space-y-1">
                        {Object.entries(detailItem.headers).map(([k, v]) => (
                          <div key={k} className="font-mono text-xs break-all text-muted-foreground">
                            {k}: {v}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>

                {/* Environment Variables */}
                {(detailItem.env_fields && detailItem.env_fields.length > 0) ||
                  (detailItem.env && Object.keys(detailItem.env).length > 0) ||
                  (detailItem.env_schema && Object.keys(detailItem.env_schema).length > 0) ||
                  !detailItem.is_system_default ? (
                  <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-medium text-foreground">环境变量</div>
                      {!detailItem.is_system_default && (
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-7 text-xs"
                          onClick={() => void handleSaveEnv(detailItem.name)}
                          disabled={detailEnvSaving}
                        >
                          {detailEnvSaving ? (
                            <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                          ) : null}
                          保存
                        </Button>
                      )}
                    </div>
                    {detailItem.is_system_default ? (
                      <div className="space-y-2">
                        {Object.entries(detailItem.env || {}).map(([k, v]) => (
                          <div key={k} className="flex items-center gap-2">
                            <span className="font-mono text-xs text-foreground">{k}</span>
                            <span className="text-xs text-muted-foreground">=</span>
                            <span className="font-mono text-xs text-muted-foreground break-all">{v}</span>
                          </div>
                        ))}
                      </div>
                    ) : detailItem.env_fields && detailItem.env_fields.length > 0 ? (
                      <div className="space-y-3">
                        {detailItem.env_fields.map((field) => (
                          <div key={field.name} className="space-y-1">
                            <div className="flex items-center gap-1.5">
                              <span className="font-mono text-xs text-foreground">{field.name}</span>
                              {field.required && (
                                <Badge variant="error" className="text-[10px] h-4 px-1">必填</Badge>
                              )}
                            </div>
                            {field.description && (
                              <div className="text-[11px] text-muted-foreground leading-4">
                                {field.description}
                              </div>
                            )}
                            <Input
                              type="text"
                              value={detailEditingEnv[field.name] || ""}
                              onChange={(e) =>
                                setDetailEditingEnv((prev) => ({ ...prev, [field.name]: e.target.value }))
                              }
                              className="h-8 text-xs"
                              placeholder={field.default_value || `填写 ${field.name}`}
                            />
                          </div>
                        ))}
                        {/* 额外自定义变量（不在 env_fields 中） */}
                        {Object.entries(detailEditingEnv)
                          .filter(([k]) => !detailItem.env_fields?.some((f) => f.name === k))
                          .map(([k, v]) => (
                            <div key={k} className="flex items-center gap-2">
                              <span className="font-mono text-xs text-foreground w-28 shrink-0 truncate">{k}</span>
                              <Input
                                type="text"
                                value={v}
                                onChange={(e) =>
                                  setDetailEditingEnv((prev) => ({ ...prev, [k]: e.target.value }))
                                }
                                className="h-7 text-xs flex-1"
                                placeholder="值"
                              />
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className="h-7 w-7 p-0 shrink-0"
                                onClick={() =>
                                  setDetailEditingEnv((prev) => {
                                    const next = { ...prev };
                                    delete next[k];
                                    return next;
                                  })
                                }
                              >
                                <Trash2 className="h-3 w-3 text-muted-foreground" />
                              </Button>
                            </div>
                          ))}
                        <div className="flex items-center gap-2 pt-1">
                          <Input
                            type="text"
                            id={`env-key-${detailItem.name}`}
                            className="h-7 text-xs w-28 shrink-0"
                            placeholder="变量名"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                const keyInput = document.getElementById(`env-key-${detailItem.name}`) as HTMLInputElement;
                                const valInput = document.getElementById(`env-val-${detailItem.name}`) as HTMLInputElement;
                                const key = keyInput.value.trim();
                                const val = valInput.value;
                                if (key) {
                                  setDetailEditingEnv((prev) => ({ ...prev, [key]: val }));
                                  keyInput.value = "";
                                  valInput.value = "";
                                  keyInput.focus();
                                }
                              }
                            }}
                          />
                          <Input
                            type="text"
                            id={`env-val-${detailItem.name}`}
                            className="h-7 text-xs flex-1"
                            placeholder="值"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                const keyInput = document.getElementById(`env-key-${detailItem.name}`) as HTMLInputElement;
                                const valInput = document.getElementById(`env-val-${detailItem.name}`) as HTMLInputElement;
                                const key = keyInput.value.trim();
                                const val = valInput.value;
                                if (key) {
                                  setDetailEditingEnv((prev) => ({ ...prev, [key]: val }));
                                  keyInput.value = "";
                                  valInput.value = "";
                                  keyInput.focus();
                                }
                              }
                            }}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 shrink-0"
                            onClick={() => {
                              const keyInput = document.getElementById(`env-key-${detailItem.name}`) as HTMLInputElement;
                              const valInput = document.getElementById(`env-val-${detailItem.name}`) as HTMLInputElement;
                              const key = keyInput.value.trim();
                              const val = valInput.value;
                              if (key) {
                                setDetailEditingEnv((prev) => ({ ...prev, [key]: val }));
                                keyInput.value = "";
                                valInput.value = "";
                                keyInput.focus();
                              }
                            }}
                          >
                            <Plus className="h-3 w-3 text-muted-foreground" />
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {Object.entries(detailEditingEnv).map(([k, v]) => (
                          <div key={k} className="flex items-center gap-2">
                            <span className="font-mono text-xs text-foreground w-28 shrink-0 truncate">{k}</span>
                            <Input
                              type="text"
                              value={v}
                              onChange={(e) =>
                                setDetailEditingEnv((prev) => ({ ...prev, [k]: e.target.value }))
                              }
                              className="h-7 text-xs flex-1"
                              placeholder="值"
                            />
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              className="h-7 w-7 p-0 shrink-0"
                              onClick={() =>
                                setDetailEditingEnv((prev) => {
                                  const next = { ...prev };
                                  delete next[k];
                                  return next;
                                })
                              }
                            >
                              <Trash2 className="h-3 w-3 text-muted-foreground" />
                            </Button>
                          </div>
                        ))}
                        <div className="flex items-center gap-2 pt-1">
                          <Input
                            type="text"
                            id={`env-key-${detailItem.name}`}
                            className="h-7 text-xs w-28 shrink-0"
                            placeholder="变量名"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                const keyInput = document.getElementById(`env-key-${detailItem.name}`) as HTMLInputElement;
                                const valInput = document.getElementById(`env-val-${detailItem.name}`) as HTMLInputElement;
                                const key = keyInput.value.trim();
                                const val = valInput.value;
                                if (key) {
                                  setDetailEditingEnv((prev) => ({ ...prev, [key]: val }));
                                  keyInput.value = "";
                                  valInput.value = "";
                                  keyInput.focus();
                                }
                              }
                            }}
                          />
                          <Input
                            type="text"
                            id={`env-val-${detailItem.name}`}
                            className="h-7 text-xs flex-1"
                            placeholder="值"
                            onKeyDown={(e) => {
                              if (e.key === "Enter") {
                                e.preventDefault();
                                const keyInput = document.getElementById(`env-key-${detailItem.name}`) as HTMLInputElement;
                                const valInput = document.getElementById(`env-val-${detailItem.name}`) as HTMLInputElement;
                                const key = keyInput.value.trim();
                                const val = valInput.value;
                                if (key) {
                                  setDetailEditingEnv((prev) => ({ ...prev, [key]: val }));
                                  keyInput.value = "";
                                  valInput.value = "";
                                  keyInput.focus();
                                }
                              }
                            }}
                          />
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 shrink-0"
                            onClick={() => {
                              const keyInput = document.getElementById(`env-key-${detailItem.name}`) as HTMLInputElement;
                              const valInput = document.getElementById(`env-val-${detailItem.name}`) as HTMLInputElement;
                              const key = keyInput.value.trim();
                              const val = valInput.value;
                              if (key) {
                                setDetailEditingEnv((prev) => ({ ...prev, [key]: val }));
                                keyInput.value = "";
                                valInput.value = "";
                                keyInput.focus();
                              }
                            }}
                          >
                            <Plus className="h-3 w-3 text-muted-foreground" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                ) : null}

                {/* Tools List */}
                <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-foreground">工具列表</div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      onClick={() => void handleTestInDialog(detailItem.name)}
                      disabled={detailTestingName === detailItem.name}
                    >
                      {detailTestingName === detailItem.name ? (
                        <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                      ) : null}
                      测试连接
                    </Button>
                  </div>
                  {detailTestMessages[detailItem.name] && (
                    <div
                      className={`rounded-lg border p-2 text-xs ${
                        detailTestMessages[detailItem.name].includes("成功")
                          ? "border-success/20 bg-success-container text-on-success-container"
                          : "border-warning/20 bg-warning-container text-on-warning-container"
                      }`}
                    >
                      {detailTestMessages[detailItem.name]}
                    </div>
                  )}
                  {detailToolsMap[detailItem.name] && detailToolsMap[detailItem.name].length > 0 && (
                    <div className="space-y-2">
                      {detailToolsMap[detailItem.name].map((tool) => (
                        <div
                          key={tool.name}
                          className="rounded-lg border border-border bg-muted/30 p-3"
                        >
                          <div className="text-sm font-medium text-foreground">
                            {tool.name}
                          </div>
                          {tool.description && (
                            <div className="mt-1 text-[11px] text-muted-foreground leading-4">
                              {tool.description}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Settings */}
                <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                  <div className="text-sm font-medium text-foreground">设置</div>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <div className="text-[11px] text-muted-foreground">超时</div>
                      <div className="mt-0.5 text-foreground">{detailItem.timeout_ms || 30000}ms</div>
                    </div>
                    {detailItem.auto_attach_modes && detailItem.auto_attach_modes.length > 0 && (
                      <div>
                        <div className="text-[11px] text-muted-foreground">自动附加模式</div>
                        <div className="mt-0.5 text-foreground">{detailItem.auto_attach_modes.join(", ")}</div>
                      </div>
                    )}
                  </div>
                </div>

                {/* Readme Excerpt */}
                {detailItem.readme_excerpt && (
                  <div className="rounded-xl border border-border bg-card p-4 space-y-3">
                    <div className="text-sm font-medium text-foreground">说明摘录</div>
                    <div className="max-h-48 overflow-y-auto rounded-lg border border-border bg-muted/50 p-3">
                      <pre className="whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground font-mono">
                        {detailItem.readme_excerpt}
                      </pre>
                    </div>
                  </div>
                )}
              </div>

              {/* Footer Actions */}
              <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
                {!detailItem.is_system_default && (
                  <Button
                    type="button"
                    variant="destructive"
                    size="sm"
                    className="h-8 text-xs"
                    onClick={() => {
                      setDetailServer(null);
                      void handleRemove(detailItem.name);
                    }}
                  >
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                    删除
                  </Button>
                )}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="h-8 text-xs"
                  onClick={() => setDetailServer(null)}
                >
                  关闭
                </Button>
              </div>
            </>
          ) : (
            <div className="flex-1 overflow-y-auto min-h-0">
              <div className="rounded-xl border border-dashed border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                无法读取该连接器详情。
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Add / Edit MCP Server Dialog */}
      <Dialog
        open={addDialogOpen}
        onOpenChange={(open) => {
          setAddDialogOpen(open);
          if (!open) setEditingServerName(null);
        }}
      >
        <DialogContent className="max-w-lg max-h-[90vh] overflow-hidden flex flex-col bg-background">
          <DialogHeader className="shrink-0">
            <DialogTitle>
              {editingServerName !== null ? "编辑连接器" : "添加连接器"}
            </DialogTitle>
            <DialogDescription>
              {editingServerName !== null
                ? "修改连接器配置，保存后即时生效。"
                : "将连接器添加到我的默认。"}
            </DialogDescription>
          </DialogHeader>
          <form
            className="flex flex-col flex-1 min-h-0"
            onSubmit={(e) => {
              e.preventDefault();
              void handleAddSubmit();
            }}
          >
            <div className="flex-1 overflow-y-auto min-h-0 pr-1 space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="add-mcp-name">名称 *</Label>
                <Input
                  id="add-mcp-name"
                  placeholder="例如：my-filesystem-server"
                  value={addForm.name}
                  onChange={(e) =>
                    setAddForm((prev) => ({ ...prev, name: e.target.value }))
                  }
                  disabled={editingServerName !== null}
                />
                {editingServerName !== null ? (
                  <p className="text-[11px] text-muted-foreground">
                    名称创建后不可修改。
                  </p>
                ) : null}
              </div>

              <div className="space-y-1.5">
                <Label htmlFor="add-mcp-type">传输类型</Label>
                <Select
                  value={addForm.type}
                  onValueChange={(v) =>
                    setAddForm((prev) => ({
                      ...prev,
                      type: v as "streamable-http" | "stdio" | "sse",
                    }))
                  }
                >
                  <SelectTrigger id="add-mcp-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="streamable-http">streamable-http</SelectItem>
                    <SelectItem value="stdio">stdio</SelectItem>
                    <SelectItem value="sse">sse</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {(addForm.type === "streamable-http" || addForm.type === "sse") && (
                <div className="space-y-1.5">
                  <Label htmlFor="add-mcp-url">URL</Label>
                  <Input
                    id="add-mcp-url"
                    placeholder={addForm.type === "sse" ? `${DEFAULT_MCP_HOST}/sse` : `${DEFAULT_MCP_HOST}/mcp`}
                    value={addForm.url}
                    onChange={(e) =>
                      setAddForm((prev) => ({ ...prev, url: e.target.value }))
                    }
                  />
                </div>
              )}

              {addForm.type === "stdio" && (
                <>
                  <div className="space-y-1.5">
                    <Label htmlFor="add-mcp-command">命令</Label>
                    <Input
                      id="add-mcp-command"
                      placeholder="例如：npx 或 uvx"
                      value={addForm.command}
                      onChange={(e) =>
                        setAddForm((prev) => ({ ...prev, command: e.target.value }))
                      }
                    />
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="add-mcp-args">参数（空格分隔）</Label>
                    <Input
                      id="add-mcp-args"
                      placeholder="例如：-y @anthropic/mcp-server"
                      value={addForm.args}
                      onChange={(e) =>
                        setAddForm((prev) => ({ ...prev, args: e.target.value }))
                      }
                    />
                  </div>
                </>
              )}

              <div className="space-y-1.5">
                <Label htmlFor="add-mcp-desc">说明</Label>
                <Textarea
                  id="add-mcp-desc"
                  placeholder="简要描述此连接器的用途"
                  className="h-16 resize-none"
                  value={addForm.description}
                  onChange={(e) =>
                    setAddForm((prev) => ({ ...prev, description: e.target.value }))
                  }
                />
              </div>

              {/* 配置说明 */}
              <div className="rounded-lg border border-border bg-muted/40 p-3 space-y-2 text-xs text-muted-foreground">
                <div className="font-medium text-foreground">配置说明</div>
                <ul className="space-y-1.5 leading-5">
                  <li>
                    <strong>streamable-http</strong>：通过 HTTP 连接远程 MCP 服务器，需填写可访问的 URL（如 <code>http://host:port/mcp</code>）。
                  </li>
                  <li>
                    <strong>stdio</strong>：通过子进程运行本地 MCP 服务器，需填写可执行命令（如 <code>npx</code>）和启动参数。
                  </li>
                  <li>
                    <strong>sse</strong>：通过 Server-Sent Events 连接，需填写 SSE 端点 URL。
                  </li>
                  <li>
                    <strong>环境变量</strong>：在卡片"详情"中配置，用于填写 API Key、Token 等凭据。
                  </li>
                  <li>
                    <strong>高级选项</strong>：Headers、超时等可编辑配置文件 <code>global_workspace/.aiasys/mcp_config.json</code>。
                  </li>
                </ul>
              </div>
            </div>

            <div className="shrink-0 flex items-center justify-end gap-2 pt-4 border-t border-border">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setAddDialogOpen(false);
                  setEditingServerName(null);
                }}
                disabled={addSubmitting}
              >
                取消
              </Button>
              <Button
                type="submit"
                size="sm"
                disabled={!addForm.name.trim() || addSubmitting}
              >
                {addSubmitting ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : null}
                {editingServerName !== null ? "保存" : "添加"}
              </Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
