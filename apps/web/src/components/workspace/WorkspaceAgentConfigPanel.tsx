import { useCallback, useEffect, useState } from "react";
import {
  Loader2,
  Save,
  RotateCcw,
  MessageSquare,
  Wrench,
  Settings,
  AlertTriangle,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import {
  getMergedConfig,
  getUserConfig,
  getWorkspaceEditorConfig,
  updatePrompt,
  updateRuntimeConfig,
  updateTools,
  resetAgentConfigToDefault,
} from "@/lib/api/agentConfig";
import type {
  UserConfigResponse,
  EditableConfigResponse,
  MergedConfigResponse,
} from "@/types/agentConfig";
import { cn } from "@/lib/utils";

interface WorkspaceAgentConfigPanelProps {
  workspaceId: string;
  scope?: "user" | "workspace";
}

const TOOL_STRATEGY_OPTIONS = [
  { value: "auto", label: "自动", description: "按模型和协议选择合适的加载方式" },
  { value: "search", label: "搜索加载", description: "保留核心工具，其余通过 tool_search 按需发现" },
  { value: "deferred", label: "延迟加载", description: "使用支持 defer_loading 的模型原生协议" },
  { value: "passthrough", label: "全量加载", description: "直接发送当前启用的全部工具" },
] as const;

function sourceBadge(source: string) {
  switch (source) {
    case "system_default":
      return <Badge variant="secondary">系统基线</Badge>;
    case "user_default":
      return <Badge variant="outline" className="text-muted-foreground">用户默认</Badge>;
    case "workspace_override":
      return <Badge variant="default">工作区覆盖</Badge>;
    case "session_override":
      return <Badge variant="default">会话覆盖</Badge>;
    default:
      return <Badge variant="secondary">{source}</Badge>;
  }
}

function getSourceLabel(source: string): string {
  switch (source) {
    case "system_default":
      return "继承系统基线";
    case "user_default":
      return "继承用户默认";
    case "workspace_override":
      return "工作区已覆盖";
    case "session_override":
      return "会话已覆盖";
    default:
      return source;
  }
}

export function WorkspaceAgentConfigPanel({
  workspaceId,
  scope = "workspace",
}: WorkspaceAgentConfigPanelProps) {
  const isUserScope = scope === "user";

  const [userConfig, setUserConfig] = useState<UserConfigResponse | null>(null);
  const [workspaceConfig, setWorkspaceConfig] = useState<EditableConfigResponse | null>(null);
  const [mergedConfig, setMergedConfig] = useState<MergedConfigResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Collapsible states
  const [promptOpen, setPromptOpen] = useState(true);
  const [toolsOpen, setToolsOpen] = useState(false);
  const [runtimeOpen, setRuntimeOpen] = useState(false);

  // Draft states
  const [promptDraft, setPromptDraft] = useState("");
  const [toolStrategyDraft, setToolStrategyDraft] = useState<string>("auto");
  const [reservedContextDraft, setReservedContextDraft] = useState("50000");
  const [compactionRatioDraft, setCompactionRatioDraft] = useState("0.85");

  const hasWorkspacePrompt = workspaceConfig?.has_local_override ?? false;
  const hasWorkspaceRuntime = workspaceConfig?.has_local_runtime_override ?? false;

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      if (isUserScope) {
        const user = await getUserConfig("analysis");
        setUserConfig(user);
        setWorkspaceConfig(null);
        setMergedConfig(null);
        setPromptDraft(user.prompt_content ?? "");
        setToolStrategyDraft(user.tool_strategy ?? "auto");
        setReservedContextDraft(String(user.reserved_context_size ?? 50000));
        setCompactionRatioDraft(String(user.compaction_trigger_ratio ?? 0.85));
      } else {
        const [user, ws, merged] = await Promise.all([
          getUserConfig("analysis"),
          getWorkspaceEditorConfig("analysis", workspaceId),
          getMergedConfig("analysis", undefined, workspaceId),
        ]);
        setUserConfig(user);
        setWorkspaceConfig(ws);
        setMergedConfig(merged);
        setPromptDraft(ws.prompt_content ?? "");
        setToolStrategyDraft(ws.tool_strategy ?? "auto");
        setReservedContextDraft(String(ws.reserved_context_size ?? 50000));
        setCompactionRatioDraft(String(ws.compaction_trigger_ratio ?? 0.85));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载配置失败");
    } finally {
      setLoading(false);
    }
  }, [workspaceId, isUserScope]);

  useEffect(() => {
    void load();
  }, [load]);

  const savePrompt = async () => {
    setSaving(true);
    try {
      await updatePrompt("analysis", promptDraft, undefined, isUserScope ? undefined : workspaceId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存提示词失败");
    } finally {
      setSaving(false);
    }
  };

  const saveTools = async () => {
    setSaving(true);
    try {
      await updateTools(
        "analysis",
        { toolStrategy: toolStrategyDraft as "auto" | "search" | "deferred" | "passthrough" },
        undefined,
        isUserScope ? undefined : workspaceId,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存工具策略失败");
    } finally {
      setSaving(false);
    }
  };

  const saveRuntime = async () => {
    setSaving(true);
    try {
      await updateRuntimeConfig(
        "analysis",
        {
          reserved_context_size: Number.parseInt(reservedContextDraft, 10) || undefined,
          compaction_trigger_ratio: Number.parseFloat(compactionRatioDraft) || undefined,
        },
        undefined,
        isUserScope ? undefined : workspaceId,
      );
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存运行时配置失败");
    } finally {
      setSaving(false);
    }
  };

  const saveAll = async () => {
    setSaving(true);
    try {
      await Promise.all([
        updatePrompt("analysis", promptDraft, undefined, isUserScope ? undefined : workspaceId),
        updateTools(
          "analysis",
          { toolStrategy: toolStrategyDraft as "auto" | "search" | "deferred" | "passthrough" },
          undefined,
          isUserScope ? undefined : workspaceId,
        ),
        updateRuntimeConfig(
          "analysis",
          {
            reserved_context_size: Number.parseInt(reservedContextDraft, 10) || undefined,
            compaction_trigger_ratio: Number.parseFloat(compactionRatioDraft) || undefined,
          },
          undefined,
          isUserScope ? undefined : workspaceId,
        ),
      ]);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存配置失败");
    } finally {
      setSaving(false);
    }
  };

  const handleReset = async () => {
    setSaving(true);
    try {
      if (isUserScope) {
        await resetAgentConfigToDefault("analysis");
      } else {
        await resetAgentConfigToDefault("analysis", undefined, workspaceId);
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "重置配置失败");
    } finally {
      setSaving(false);
    }
  };

  const promptSource = workspaceConfig?.source ?? "system_default";
  const runtimeSource = workspaceConfig?.runtime_source ?? "system_default";

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="border-b px-4 py-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-medium">{isUserScope ? "用户默认配置" : "工作区设置"}</h3>
          </div>
          <div className="flex items-center gap-1.5">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-[11px]"
              onClick={handleReset}
              disabled={saving}
            >
              <RotateCcw className="mr-1 h-3 w-3" />
              重置
            </Button>
          </div>
        </div>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {isUserScope
            ? "用户默认配置会作为所有工作区的基线。未在工作区覆盖的项将继承这里的设置。"
            : "覆盖用户默认配置，仅对当前工作区生效。未覆盖的项继承自用户默认。"}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-1">
        {error ? (
          <div className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5" />
            {error}
          </div>
        ) : null}

        {/* Prompt Section */}
        <Collapsible open={promptOpen} onOpenChange={setPromptOpen}>
          <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-xs font-medium transition-colors hover:bg-muted/60">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
              工作说明
              {!isUserScope && sourceBadge(promptSource)}
            </div>
            <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", promptOpen && "rotate-180")} />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="px-2 pb-3 pt-1 space-y-2">
              {!isUserScope && userConfig?.prompt_content ? (
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
                  <div className="mb-1 font-medium">继承的用户默认工作说明：</div>
                  <div className="line-clamp-3">{userConfig.prompt_content}</div>
                </div>
              ) : null}

              <Textarea
                value={promptDraft}
                onChange={(e) => setPromptDraft(e.target.value)}
                placeholder={
                  isUserScope
                    ? "输入用户默认工作说明，会作为所有工作区的基线..."
                    : userConfig?.prompt_content
                      ? "输入工作区覆盖的工作说明，留空则继承用户默认..."
                      : "用户未设置默认工作说明。输入后将在工作区级覆盖系统基线..."
                }
                className="min-h-[100px] text-xs"
              />
              <div className="flex items-center justify-between">
                <div className="text-[10px] text-muted-foreground">
                  {!isUserScope && (
                    <>
                      {getSourceLabel(promptSource)}
                      {hasWorkspacePrompt ? "（编辑上方内容可修改工作区覆盖）" : "（编辑上方内容可添加工作区覆盖）"}
                    </>
                  )}
                </div>
                <Button
                  size="sm"
                  className="h-7 text-[11px]"
                  onClick={savePrompt}
                  disabled={saving}
                >
                  {saving ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Save className="mr-1 h-3 w-3" />}
                  保存
                </Button>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>

        <Separator />

        {/* Tool Strategy Section */}
        <Collapsible open={toolsOpen} onOpenChange={setToolsOpen}>
          <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-xs font-medium transition-colors hover:bg-muted/60">
            <div className="flex items-center gap-2">
              <Wrench className="h-3.5 w-3.5 text-muted-foreground" />
              工具策略
            </div>
            <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", toolsOpen && "rotate-180")} />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="px-2 pb-3 pt-1 space-y-2">
              {!isUserScope && (
                <div className="text-[11px] text-muted-foreground">
                  用户默认策略：{TOOL_STRATEGY_OPTIONS.find(o => o.value === userConfig?.tool_strategy)?.label ?? "自动（系统基线）"}
                </div>
              )}

              <Select
                value={toolStrategyDraft}
                onValueChange={(v) => setToolStrategyDraft(v)}
              >
                <SelectTrigger className="h-8 text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TOOL_STRATEGY_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value} className="text-xs">
                      <div>
                        <div>{opt.label}</div>
                        <div className="text-[10px] text-muted-foreground">{opt.description}</div>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              {!isUserScope && mergedConfig ? (
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2 text-[11px]">
                  <div className="font-medium text-muted-foreground">当前生效的工具策略</div>
                  <div className="mt-1">
                    {TOOL_STRATEGY_OPTIONS.find(o => o.value === mergedConfig.tool_strategy)?.label ?? mergedConfig.tool_strategy}
                    <span className="ml-2 text-muted-foreground">({sourceBadge(mergedConfig.prompt_source)})</span>
                  </div>
                </div>
              ) : null}

              <div className="flex justify-end">
                <Button
                  size="sm"
                  className="h-7 text-[11px]"
                  onClick={saveTools}
                  disabled={saving}
                >
                  {saving ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Save className="mr-1 h-3 w-3" />}
                  保存
                </Button>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>

        <Separator />

        {/* Runtime Section */}
        <Collapsible open={runtimeOpen} onOpenChange={setRuntimeOpen}>
          <CollapsibleTrigger className="flex w-full items-center justify-between rounded-md px-2 py-2 text-left text-xs font-medium transition-colors hover:bg-muted/60">
            <div className="flex items-center gap-2">
              <Settings className="h-3.5 w-3.5 text-muted-foreground" />
              运行时参数
            </div>
            <ChevronDown className={cn("h-3.5 w-3.5 text-muted-foreground transition-transform", runtimeOpen && "rotate-180")} />
          </CollapsibleTrigger>
          <CollapsibleContent>
            <div className="px-2 pb-3 pt-1 space-y-3">
              <div className="space-y-1">
                <Label className="text-[11px]">保留上下文空间</Label>
                <Input
                  type="number"
                  min={1000}
                  value={reservedContextDraft}
                  onChange={(e) => setReservedContextDraft(e.target.value)}
                  className="h-8 text-xs"
                />
                {!isUserScope && (
                  <div className="text-[10px] text-muted-foreground">
                    用户默认：{userConfig?.reserved_context_size ?? "系统基线"}
                  </div>
                )}
              </div>
              <div className="space-y-1">
                <Label className="text-[11px]">自动压缩触发比例</Label>
                <Input
                  type="number"
                  min={0.5}
                  max={0.99}
                  step={0.01}
                  value={compactionRatioDraft}
                  onChange={(e) => setCompactionRatioDraft(e.target.value)}
                  className="h-8 text-xs"
                />
                {!isUserScope && (
                  <div className="text-[10px] text-muted-foreground">
                    用户默认：{userConfig?.compaction_trigger_ratio ?? "系统基线"}
                  </div>
                )}
              </div>

              <div className="flex items-center justify-between">
                <div className="text-[10px] text-muted-foreground">
                  {!isUserScope && (
                    <>
                      {getSourceLabel(runtimeSource)}
                      {hasWorkspaceRuntime ? "（已覆盖）" : "（继承用户默认）"}
                    </>
                  )}
                </div>
                <Button
                  size="sm"
                  className="h-7 text-[11px]"
                  onClick={saveRuntime}
                  disabled={saving}
                >
                  {saving ? <Loader2 className="mr-1 h-3 w-3 animate-spin" /> : <Save className="mr-1 h-3 w-3" />}
                  保存
                </Button>
              </div>
            </div>
          </CollapsibleContent>
        </Collapsible>

        <Separator />

        {/* Global Save */}
        <div className="px-2 py-2">
          <Button
            className="w-full h-8 text-[11px]"
            onClick={saveAll}
            disabled={saving}
          >
            {saving ? <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" /> : <Save className="mr-1.5 h-3.5 w-3.5" />}
            保存全部配置
          </Button>
        </div>
      </div>
    </div>
  );
}
