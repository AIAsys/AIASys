import { useState, useEffect, useCallback, useMemo } from "react";
import { useAuthState } from "@/contexts/AuthContext";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCapabilityRegistry } from "@/hooks/useCapabilityRegistry";
import { FileUploadToast, useFileUploadToast } from "@/components/file/FileUploadToast";
import {
  getMergedConfig,
  getSessionEditorConfig,
  getSystemConfig,
  getUserConfig,
  getTaskModels,
  resetAgentConfigToDefault,
  updatePrompt,
  updateRuntimeConfig,
  updateSystemPrompt,
  updateTaskModels,
  updateTools,
} from "@/lib/api/agentConfig";
import type { AgentMode } from "@/types/agentConfig";
import type { SessionStatusInfo } from "@/pages/DataAnalysisPage/types";
import type { CapabilityDescriptor } from "@/types/capability";
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Loader2,
  RotateCcw,
  Save,
  Search,
  Settings,
  X,
} from "lucide-react";


interface RuntimeAwareToolOption {
  name: string;
  label: string;
  category: string;
  categoryLabel: string;
  capabilityId: string;
  provider: string;
  kind: string;
  description: string;
  runtimeAvailable: boolean;
  runtimeReason: string | null;
}

const TOOL_STRATEGY_OPTIONS = [
  {
    value: "auto",
    label: "自动",
    description: "按模型和协议选择合适的加载方式",
  },
  {
    value: "search",
    label: "搜索加载",
    description: "保留核心工具，其余工具通过 tool_search 按需发现",
  },
  {
    value: "deferred",
    label: "延迟加载",
    description: "使用支持 defer_loading 的模型原生协议",
  },
  {
    value: "passthrough",
    label: "全量加载",
    description: "直接发送当前启用的全部工具",
  },
] as const;

function getToolNameFromCapability(capability: CapabilityDescriptor): string | null {
  const rawToolName = capability.config_schema?.tool_name;
  return typeof rawToolName === "string" && rawToolName.trim()
    ? rawToolName
    : null;
}

function isRuntimeAvailable(capability?: CapabilityDescriptor): boolean {
  const raw = capability?.config_schema?.runtime_available;
  if (typeof raw === "boolean") {
    return raw;
  }
  return capability?.status !== "disabled";
}

function getRuntimeReason(capability?: CapabilityDescriptor): string | null {
  const raw = capability?.config_schema?.runtime_reason;
  return typeof raw === "string" && raw.trim() ? raw : null;
}

function formatRuntimeReason(reason: string | null): string {
  switch (reason) {
    case "module_import_error":
      return "当前运行时缺少对应模块或依赖，系统不会把它当作可用工具。";
    case "lookup_error":
      return "当前运行时无法解析这个工具入口。";
    case "unknown_error":
      return "当前运行时在探测这个工具时发生异常。";
    default:
      return reason ? `当前运行时不可用：${reason}` : "当前运行时不可用。";
  }
}

type AgentConfigSection =
  | "prompt"
  | "tools"
  | "runtime"
  | "taskModels"
  | "preview";

const DEFAULT_AGENT_CONFIG_SECTIONS: readonly AgentConfigSection[] = [
  "prompt",
  "tools",
  "runtime",
  "taskModels",
  "preview",
];

interface AgentConfigPanelProps {
  hideHeader?: boolean;
  forcedMode?: AgentMode;
  sessionId?: string;
  workspaceId?: string | null;
  sessionTitle?: string | null;
  sessionStatus?: SessionStatusInfo | null;
  isSessionRunning?: boolean;
  visibleSections?: readonly AgentConfigSection[];
}

interface PreviewConfigState {
  isCustomized: boolean;
  promptSource: string;
  enabledTools: string[];
  toolStrategy: "auto" | "search" | "deferred" | "passthrough";
  systemPromptPreview: string;
  reservedContextSize: number;
  compactionTriggerRatio: number;
  runtimeSource: string;
}

interface EditorScopeState {
  source: string;
  hasLocalOverride: boolean;
  runtimeSource: string;
  hasLocalRuntimeOverride: boolean;
}

interface RuntimeConfigFormState {
  reserved_context_size: string;
  compaction_trigger_ratio: string;
}

function getScopeTitle(sessionId?: string): string {
  return sessionId ? "当前会话配置" : "我的默认配置";
}

function getScopeDescription(sessionId?: string): string {
  return sessionId
    ? "当前会话保存后才会形成私有配置覆盖；未保存时继续继承“我的默认配置”或系统基线。"
    : "配置跨工作区共享的个人基线。工作区可以在此基础上进行覆盖。";
}

function getSourceLabel(source: string): string {
  switch (source) {
    case "system_default":
      return "系统基线";
    case "user_default":
    case "user_override":
      return "我的默认配置";
    case "session_override":
      return "当前会话覆盖";
    default:
      return source;
  }
}

export default function AgentConfigPanel({
  hideHeader = false,
  forcedMode,
  sessionId,
  workspaceId,
  sessionTitle,
  sessionStatus,
  isSessionRunning = false,
  visibleSections = DEFAULT_AGENT_CONFIG_SECTIONS,
}: AgentConfigPanelProps = {}) {
  const { isAdmin } = useAuthState();
  const activeTab: AgentMode = forcedMode || "analysis";
  const activeSections = useMemo(
    () => new Set<AgentConfigSection>(visibleSections),
    [visibleSections],
  );
  const showPromptSection = activeSections.has("prompt");
  const showToolsSection = activeSections.has("tools");
  const showRuntimeSection = activeSections.has("runtime");
  const showTaskModelsSection = activeSections.has("taskModels");
  const showPreviewSection = activeSections.has("preview");
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [promptContent, setPromptContent] = useState("");
  const [enabledTools, setEnabledTools] = useState<string[]>([]);
  const [toolStrategy, setToolStrategy] = useState<
    "auto" | "search" | "deferred" | "passthrough"
  >("auto");
  const [toolSearchQuery, setToolSearchQuery] = useState("");
  const [toolCategoryFilter, setToolCategoryFilter] = useState("all");
  const [runtimeConfig, setRuntimeConfig] = useState<RuntimeConfigFormState>({
    reserved_context_size: "50000",
    compaction_trigger_ratio: "0.85",
  });
  const [taskModels, setTaskModels] = useState<Record<string, string>>({});
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [isSavingTaskModels, setIsSavingTaskModels] = useState(false);
  const [previewConfig, setPreviewConfig] = useState<PreviewConfigState | null>(null);
  const [editorScope, setEditorScope] = useState<EditorScopeState>({
    source: "system_default",
    hasLocalOverride: false,
    runtimeSource: "system_default",
    hasLocalRuntimeOverride: false,
  });
  const [systemPrompt, setSystemPrompt] = useState("");
  const [collapsedCards, setCollapsedCards] = useState<Set<string>>(() => new Set(["preview"]));
  const toggleCard = (cardId: string) => {
    setCollapsedCards((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) {
        next.delete(cardId);
      } else {
        next.add(cardId);
      }
      return next;
    });
  };
  const [showSystemConfig, setShowSystemConfig] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const {
    registry: capabilityRegistry,
    loading: capabilityRegistryLoading,
    error: capabilityRegistryError,
  } = useCapabilityRegistry();
  const { toasts, showSuccess, showError } = useFileUploadToast();

  const isSessionScope = Boolean(sessionId);
  const pageTitle = getScopeTitle(sessionId);
  const pageDescription = getScopeDescription(sessionId);

  const loadConfig = useCallback(async () => {
    setIsLoading(true);
    try {
      if (showTaskModelsSection) {
        const taskModelsRes = await getTaskModels();
        setTaskModels(taskModelsRes.task_models || {});
        setAvailableModels(taskModelsRes.available_models || []);
      }

      if (sessionId) {
        const [editorConfig, mergedConfig] = await Promise.all([
          getSessionEditorConfig(activeTab, sessionId),
          getMergedConfig(activeTab, sessionId, workspaceId || undefined),
        ]);

        setPromptContent(editorConfig.prompt_content || "");
        setEnabledTools(editorConfig.enabled_tools || []);
        setToolStrategy(editorConfig.tool_strategy || "auto");
        setRuntimeConfig({
          reserved_context_size: String(editorConfig.reserved_context_size),
          compaction_trigger_ratio: String(editorConfig.compaction_trigger_ratio),
        });
        setEditorScope({
          source: editorConfig.source,
          hasLocalOverride: editorConfig.has_local_override,
          runtimeSource: editorConfig.runtime_source,
          hasLocalRuntimeOverride: editorConfig.has_local_runtime_override,
        });
        setPreviewConfig({
          isCustomized: mergedConfig.is_customized,
          promptSource: mergedConfig.prompt_source,
          enabledTools: mergedConfig.enabled_tools,
          toolStrategy: mergedConfig.tool_strategy,
          systemPromptPreview: mergedConfig.system_prompt_preview,
          reservedContextSize: mergedConfig.reserved_context_size,
          compactionTriggerRatio: mergedConfig.compaction_trigger_ratio,
          runtimeSource: mergedConfig.runtime_source,
        });
        return;
      }

      const [userConfig, mergedConfig] = await Promise.all([
        getUserConfig(activeTab),
        getMergedConfig(activeTab, undefined, workspaceId || undefined),
      ]);

      setPromptContent(userConfig.prompt_content || "");
      setEnabledTools(mergedConfig.enabled_tools || userConfig.enabled_tools || []);
      setToolStrategy(userConfig.tool_strategy || mergedConfig.tool_strategy || "auto");
      setRuntimeConfig({
        reserved_context_size: String(mergedConfig.reserved_context_size),
        compaction_trigger_ratio: String(mergedConfig.compaction_trigger_ratio),
      });
      setEditorScope({
        source: userConfig.enabled ? "user_default" : "system_default",
        hasLocalOverride: userConfig.enabled,
        runtimeSource:
          userConfig.reserved_context_size !== undefined ||
          userConfig.compaction_trigger_ratio !== undefined
            ? "user_default"
            : "system_default",
        hasLocalRuntimeOverride:
          userConfig.reserved_context_size !== undefined ||
          userConfig.compaction_trigger_ratio !== undefined,
      });
      setPreviewConfig({
        isCustomized: mergedConfig.is_customized,
        promptSource: mergedConfig.prompt_source,
        enabledTools: mergedConfig.enabled_tools,
        toolStrategy: mergedConfig.tool_strategy,
        systemPromptPreview: mergedConfig.system_prompt_preview,
        reservedContextSize: mergedConfig.reserved_context_size,
        compactionTriggerRatio: mergedConfig.compaction_trigger_ratio,
        runtimeSource: mergedConfig.runtime_source,
      });
    } catch (error) {
      showError("加载配置失败");
      console.error(error);
    } finally {
      setIsLoading(false);
    }
  }, [activeTab, sessionId, showTaskModelsSection, workspaceId]);

  const loadSystemConfig = useCallback(async () => {
    if (!isAdmin || isSessionScope) {
      return;
    }
    try {
      const config = await getSystemConfig(activeTab);
      setSystemPrompt(config.prompt_content);
    } catch (error) {
      showError("加载系统基线失败");
      console.error(error);
    }
  }, [activeTab, isAdmin, isSessionScope]);

  useEffect(() => {
    void loadConfig();
    if (showSystemConfig) {
      void loadSystemConfig();
    }
  }, [loadConfig, loadSystemConfig, showSystemConfig]);

  const handleSavePrompt = async () => {
    if (!promptContent.trim()) {
      showError("工作说明不能为空");
      return;
    }

    setIsSaving(true);
    try {
      await updatePrompt(activeTab, promptContent, sessionId);
      showSuccess(isSessionScope ? "当前会话工作说明已保存" : "默认工作说明已保存");
      await loadConfig();
    } catch (error) {
      showError("保存工作说明失败");
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveTools = async () => {
    setIsSaving(true);
    try {
      await updateTools(
        activeTab,
        {
          enabledTools,
          toolStrategy,
        },
        sessionId,
      );
      showSuccess(isSessionScope ? "当前会话工具选择已保存" : "默认工具选择已保存");
      await loadConfig();
    } catch (error) {
      showError("保存工具选择失败");
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveTaskModels = async () => {
    setIsSavingTaskModels(true);
    try {
      await updateTaskModels(taskModels);
      showSuccess("任务模型路由已保存");
    } catch (error) {
      showError(String(error));
      console.error(error);
    } finally {
      setIsSavingTaskModels(false);
    }
  };

  const handleSaveRuntime = async () => {
    const reservedContextSize = Number.parseInt(runtimeConfig.reserved_context_size, 10);
    const compactionTriggerRatio = Number.parseFloat(
      runtimeConfig.compaction_trigger_ratio,
    );

    if (!Number.isFinite(reservedContextSize) || reservedContextSize < 1000) {
      showError("保留回复空间必须是大于等于 1000 的整数");
      return;
    }
    if (
      !Number.isFinite(compactionTriggerRatio) ||
      compactionTriggerRatio < 0.5 ||
      compactionTriggerRatio > 0.99
    ) {
      showError("自动压缩触发比例必须介于 0.50 和 0.99 之间");
      return;
    }

    setIsSaving(true);
    try {
      await updateRuntimeConfig(
        activeTab,
        {
          reserved_context_size: reservedContextSize,
          compaction_trigger_ratio: compactionTriggerRatio,
        },
        sessionId,
      );
      showSuccess(
        isSessionScope
          ? "当前会话自动压缩策略已保存"
          : "默认自动压缩策略已保存",
      );
      await loadConfig();
    } catch (error) {
      showError("保存自动压缩策略失败");
      console.error(error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleReset = async () => {
    try {
      await resetAgentConfigToDefault(activeTab, sessionId);
      showSuccess(
        isSessionScope ? "当前会话配置覆盖已清空" : "默认配置已重置为系统基线",
      );
      setShowResetDialog(false);
      await loadConfig();
    } catch (error) {
      showError("重置配置失败");
      console.error(error);
    }
  };

  const toggleTool = (toolName: string) => {
    setEnabledTools((previous) =>
      previous.includes(toolName)
        ? previous.filter((item) => item !== toolName)
        : [...previous, toolName],
    );
  };

  const runtimeAwareTools = useMemo<RuntimeAwareToolOption[]>(
    () => {
      const deduped = new Map<string, RuntimeAwareToolOption>();
      for (const capability of capabilityRegistry?.capabilities || []) {
        const toolName = getToolNameFromCapability(capability);
        if (!toolName || deduped.has(toolName)) {
          continue;
        }
        const category = capability.category_id || "other";
        deduped.set(toolName, {
          name: toolName,
          label: capability.display_name || toolName.split(":").pop() || toolName,
          category,
          categoryLabel: capability.category_label || "其他工具",
          capabilityId: capability.capability_id,
          provider: capability.provider,
          kind: capability.kind,
          description: capability.description || "",
          runtimeAvailable: isRuntimeAvailable(capability),
          runtimeReason: getRuntimeReason(capability),
        });
      }
      return Array.from(deduped.values()).sort((left, right) =>
        `${left.categoryLabel}:${left.label}`.localeCompare(
          `${right.categoryLabel}:${right.label}`,
        ),
      );
    },
    [capabilityRegistry],
  );
  const filteredTools = useMemo(() => {
    const query = toolSearchQuery.trim().toLowerCase();
    return runtimeAwareTools.filter((tool) => {
      if (toolCategoryFilter !== "all" && tool.category !== toolCategoryFilter) {
        return false;
      }
      if (!query) {
        return true;
      }
      const searchable = [
        tool.label,
        tool.name,
        tool.capabilityId,
        tool.provider,
        tool.kind,
        tool.description,
      ]
        .join(" ")
        .toLowerCase();
      return searchable.includes(query);
    });
  }, [runtimeAwareTools, toolCategoryFilter, toolSearchQuery]);
  const groupedTools = useMemo(
    () =>
      filteredTools.reduce<Record<string, RuntimeAwareToolOption[]>>(
        (acc, tool) => {
          if (!acc[tool.category]) {
            acc[tool.category] = [];
          }
          acc[tool.category].push(tool);
          return acc;
        },
        {},
      ),
    [filteredTools],
  );
  const toolCategories = useMemo(
    () =>
      Array.from(new Set(runtimeAwareTools.map((tool) => tool.category))).sort(
        (left, right) => {
          const leftLabel =
            runtimeAwareTools.find((tool) => tool.category === left)?.categoryLabel ||
            left;
          const rightLabel =
            runtimeAwareTools.find((tool) => tool.category === right)?.categoryLabel ||
            right;
          return leftLabel.localeCompare(rightLabel);
        },
      ),
    [runtimeAwareTools],
  );
  const unavailableTools = runtimeAwareTools.filter((tool) => !tool.runtimeAvailable);
  const activeStrategyOption =
    TOOL_STRATEGY_OPTIONS.find((option) => option.value === toolStrategy) ||
    TOOL_STRATEGY_OPTIONS[0];

  const pendingVersion = sessionStatus?.pending_agent_config_version;
  const isSessionSaveLocked = isSessionScope && isSessionRunning;
  const effectLabel =
    sessionStatus?.agent_config_effect === "next_run_only"
      ? "保存后的配置会在下次执行启动时生效。"
      : "配置会在下一次使用该模式时按当前执行环境规则生效。";

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-background">
      <div className="flex-1 min-h-0 overflow-y-auto px-5 py-4">
      {!hideHeader ? (
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">
              {pageTitle}
            </h1>
            <p className="mt-1 text-muted-foreground">{pageDescription}</p>
          </div>
          <div className="flex gap-2">
            {isAdmin && !isSessionScope ? (
              <Button
                variant="outline"
                onClick={() => setShowSystemConfig((previous) => !previous)}
              >
                <Settings className="mr-2 h-4 w-4" />
                {showSystemConfig ? "隐藏系统基线" : "系统基线"}
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="mb-5 rounded-2xl border border-border bg-muted/15 p-4">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">AIASys 主控</Badge>
          <Badge
            variant={
              isSessionScope && editorScope.hasLocalOverride ? "secondary" : "outline"
            }
          >
            {isSessionScope
              ? editorScope.hasLocalOverride
                ? "当前会话覆盖"
                : "当前会话继承"
              : "我的默认配置"}
          </Badge>
          <Badge variant="outline">来源：{getSourceLabel(editorScope.source)}</Badge>
          {sessionId ? <Badge variant="outline">Session: {sessionId}</Badge> : null}
          {sessionTitle?.trim() ? <Badge variant="secondary">{sessionTitle.trim()}</Badge> : null}
          {isSessionRunning ? <Badge variant="secondary">当前运行中</Badge> : null}
          {pendingVersion ? <Badge variant="secondary">存在待生效配置</Badge> : null}
        </div>
        <div className="mt-2 text-sm text-muted-foreground">{effectLabel}</div>
      </div>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4">
          <div className="space-y-6">
            {isSessionSaveLocked ? (
              <Card className="border-warning/20 bg-warning-container/80">
                <CardContent className="pt-6 text-sm text-warning">
                  当前会话正在执行中。为了避免你误以为这轮会立即切换配置，当前会话的工作说明、工具策略和自动压缩策略都会在执行结束后才能保存。
                </CardContent>
              </Card>
            ) : null}
            {showPromptSection ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>工作说明</CardTitle>
                    <CardDescription>
                      {isSessionScope
                        ? "下方编辑器会先载入当前生效工作说明；只有点击保存后，才会写成当前会话的私有覆盖。"
                        : "配置你的长期默认工作说明。当前会话如未单独覆盖，会沿用这里。"}
                    </CardDescription>
                  </div>
                  <Badge variant={editorScope.hasLocalOverride ? "secondary" : "outline"}>
                    {editorScope.hasLocalOverride ? "当前层已覆盖" : "当前层继承上级"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {isSessionScope && !editorScope.hasLocalOverride ? (
                  <div className="rounded-lg border border-warning/20 bg-warning-container p-3 text-sm text-warning">
                    当前会话目前仍继承
                    {getSourceLabel(editorScope.source)}
                    。下方内容是当前实际生效的基线，只有保存后才会创建当前会话自己的工作说明覆盖。
                  </div>
                ) : null}
                <div className="space-y-2">
                  <Label>工作说明内容</Label>
                  <Textarea
                    value={promptContent}
                    onChange={(event) => setPromptContent(event.target.value)}
                    placeholder={
                      isSessionScope
                        ? "输入当前会话的完整工作说明覆盖..."
                        : "输入你的默认工作说明覆盖..."
                    }
                    className="min-h-[180px] font-mono text-sm"
                  />
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={handleSavePrompt}
                    disabled={isSaving || !promptContent.trim() || isSessionSaveLocked}
                  >
                    {isSaving ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Save className="mr-2 h-4 w-4" />
                    )}
                    保存工作说明
                  </Button>

                  {editorScope.hasLocalOverride ? (
                    <Button
                      variant="outline"
                      onClick={() => setShowResetDialog(true)}
                      disabled={isSessionSaveLocked}
                    >
                      <RotateCcw className="mr-2 h-4 w-4" />
                      清空当前层覆盖
                    </Button>
                  ) : null}
                </div>
              </CardContent>
            </Card>
            ) : null}

            {showToolsSection ? (
            <Card>
              <CardHeader>
                <CardTitle>工具选择</CardTitle>
                <CardDescription>
                  {isSessionScope
                    ? "选择当前会话下次执行时可用的工具。列表来自系统能力目录和运行时探测。"
                    : "选择你的默认工具集合。当前会话如未单独覆盖，会沿用这里。"}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {isSessionScope && !editorScope.hasLocalOverride ? (
                  <div className="rounded-lg border border-warning/20 bg-warning-container p-3 text-sm text-warning">
                    当前会话还没有保存自己的工具选择。你现在看到的是继承后的实际可用结果；点击保存后才会固定为当前会话选择。
                  </div>
                ) : null}
                {capabilityRegistryError ? (
                  <div className="rounded-lg border border-warning/20 bg-warning-container p-3 text-sm text-warning">
                    系统能力加载失败，暂时无法刷新工具目录。
                  </div>
                ) : null}
                {capabilityRegistryLoading ? (
                  <div className="rounded-lg border border-border bg-muted/15 p-3 text-sm text-muted-foreground">
                    正在同步当前运行时的工具可用性…
                  </div>
                ) : null}
                {unavailableTools.length > 0 ? (
                  <div className="rounded-lg border border-warning/20 bg-warning-container p-3 text-sm text-warning">
                    {unavailableTools.length} 个工具当前运行时不可用，保存时不会作为可生效工具启用。
                  </div>
                ) : null}

                <div className="grid gap-3 md:grid-cols-[1fr_220px]">
                  <div className="relative">
                    <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground" />
                    <Input
                      value={toolSearchQuery}
                      onChange={(event) => setToolSearchQuery(event.target.value)}
                      className="pl-9"
                      placeholder="搜索工具、能力 ID 或提供方"
                    />
                  </div>
                  <Select
                    value={toolCategoryFilter}
                    onValueChange={setToolCategoryFilter}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="全部分类" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">全部分类</SelectItem>
                      {toolCategories.map((category) => {
                        const categoryLabel =
                          runtimeAwareTools.find((tool) => tool.category === category)
                            ?.categoryLabel || category;
                        return (
                          <SelectItem key={category} value={category}>
                            {categoryLabel}
                          </SelectItem>
                        );
                      })}
                    </SelectContent>
                  </Select>
                </div>

                <div className="rounded-lg border border-border bg-muted/10 p-3">
                  <div className="grid gap-3 md:grid-cols-[180px_1fr]">
                    <div className="space-y-2">
                      <Label>工具加载策略</Label>
                      <Select value={toolStrategy} onValueChange={(value) => setToolStrategy(value as typeof toolStrategy)}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {TOOL_STRATEGY_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div className="self-end text-xs leading-5 text-muted-foreground">
                      {activeStrategyOption.description}
                    </div>
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                  <Badge variant="secondary">已启用 {enabledTools.length}</Badge>
                  <Badge variant="outline">目录 {runtimeAwareTools.length}</Badge>
                  <Badge variant="outline">当前显示 {filteredTools.length}</Badge>
                </div>

                <div className="h-[240px] overflow-y-auto pr-2">
                  <div className="space-y-4">
                    {Object.entries(groupedTools).map(([category, tools]) => (
                      <div key={category}>
                        <h4 className="mb-2 text-sm font-medium">
                          {tools[0]?.categoryLabel || category}
                        </h4>
                        <div className="space-y-2">
                          {tools.map((tool) => {
                            const isEnabled =
                              tool.runtimeAvailable &&
                              enabledTools.includes(tool.name);
                            return (
                              <div
                                key={tool.name}
                                className="flex items-center justify-between gap-3 rounded-lg border p-3"
                              >
                                <div className="flex min-w-0 flex-1 items-start gap-3">
                                  {isEnabled ? (
                                    <Check className="h-4 w-4 text-success" />
                                  ) : (
                                    <X className="h-4 w-4 text-destructive" />
                                  )}
                                  <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <span className="text-sm font-medium">{tool.label}</span>
                                      <Badge
                                        variant={
                                          tool.runtimeAvailable ? "outline" : "secondary"
                                        }
                                      >
                                        {tool.runtimeAvailable
                                          ? "运行时可用"
                                          : "运行时缺失"}
                                      </Badge>
                                      <Badge variant="outline">{tool.provider}</Badge>
                                    </div>
                                    <div className="mt-1 break-all text-xs text-muted-foreground">
                                      {tool.name}
                                    </div>
                                    {tool.description ? (
                                      <div className="mt-1 text-xs leading-5 text-muted-foreground">
                                        {tool.description}
                                      </div>
                                    ) : null}
                                    {!tool.runtimeAvailable ? (
                                      <div className="mt-1 text-xs leading-5 text-muted-foreground">
                                        {formatRuntimeReason(tool.runtimeReason)}
                                      </div>
                                    ) : null}
                                  </div>
                                </div>
                                <Switch
                                  checked={isEnabled}
                                  disabled={!tool.runtimeAvailable}
                                  onCheckedChange={() => toggleTool(tool.name)}
                                />
                              </div>
                            );
                          })}
                        </div>
                        <Separator className="my-3" />
                      </div>
                    ))}
                    {filteredTools.length === 0 ? (
                      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
                        没有匹配的工具
                      </div>
                    ) : null}
                  </div>
                </div>

                <Button
                  onClick={handleSaveTools}
                  disabled={isSaving || isSessionSaveLocked}
                  className="mt-4"
                >
                  {isSaving ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  保存工具选择
                </Button>
              </CardContent>
            </Card>
            ) : null}

            {showRuntimeSection ? (
            <Card data-testid="agent-runtime-card">
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <CardTitle>自动压缩策略</CardTitle>
                    <CardDescription>
                      {isSessionScope
                        ? "这里配置当前会话下次执行时使用的自动压缩阈值。它不改变模型最大上下文窗口，只控制什么时候更早开始压缩历史。"
                        : "这里配置你的默认自动压缩策略。没有会话级覆盖时，新会话会继承这里的策略。"}
                    </CardDescription>
                  </div>
                  <Badge
                    variant={editorScope.hasLocalRuntimeOverride ? "secondary" : "outline"}
                  >
                    {editorScope.hasLocalRuntimeOverride ? "当前层已覆盖" : "当前层继承上级"}
                  </Badge>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                {isSessionScope && !editorScope.hasLocalRuntimeOverride ? (
                  <div className="rounded-lg border border-warning/20 bg-warning-container p-3 text-sm text-warning">
                    当前会话仍继承 {getSourceLabel(editorScope.runtimeSource)} 的自动压缩策略。保存后才会生成当前会话自己的运行时覆盖。
                  </div>
                ) : null}
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="agent-runtime-reserved-context-size">
                      保留回复空间
                    </Label>
                    <Input
                      id="agent-runtime-reserved-context-size"
                      data-testid="agent-runtime-reserved-context-size"
                      type="number"
                      min={1000}
                      value={runtimeConfig.reserved_context_size}
                      onChange={(event) =>
                        setRuntimeConfig((previous) => ({
                          ...previous,
                          reserved_context_size: event.target.value,
                        }))
                      }
                    />
                    <p className="text-xs leading-5 text-muted-foreground">
                      为模型最终回复预留的 token 空间。值越大，系统越倾向于更早开始压缩历史。
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="agent-runtime-compaction-trigger-ratio">
                      自动压缩触发比例
                    </Label>
                    <Input
                      id="agent-runtime-compaction-trigger-ratio"
                      data-testid="agent-runtime-compaction-trigger-ratio"
                      type="number"
                      min={0.5}
                      max={0.99}
                      step={0.01}
                      value={runtimeConfig.compaction_trigger_ratio}
                      onChange={(event) =>
                        setRuntimeConfig((previous) => ({
                          ...previous,
                          compaction_trigger_ratio: event.target.value,
                        }))
                      }
                    />
                    <p className="text-xs leading-5 text-muted-foreground">
                      当上下文使用比例达到这个阈值时，系统会尝试自动压缩较早历史。想更早压缩，就把它调低一些。
                    </p>
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-muted/15 p-3 text-sm text-muted-foreground">
                  当前生效来源：{getSourceLabel(editorScope.runtimeSource)}。如果仍然遇到上下文超限，可以先手动点击输入框旁的“压缩上下文”，再调整这里的阈值。
                </div>
                <Button
                  data-testid="agent-runtime-save"
                  onClick={handleSaveRuntime}
                  disabled={isSaving || isSessionSaveLocked}
                >
                  {isSaving ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  保存自动压缩策略
                </Button>
              </CardContent>
            </Card>
            ) : null}

            {showTaskModelsSection ? (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <CardTitle>任务模型路由</CardTitle>
                    <CardDescription>
                      为特定任务指定独立模型。未配置的任务使用主模型。
                    </CardDescription>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="task-model-compaction">压缩总结模型</Label>
                    <select
                      id="task-model-compaction"
                      value={taskModels.compaction || ""}
                      onChange={(e) =>
                        setTaskModels((prev) => ({
                          ...prev,
                          compaction: e.target.value,
                        }))
                      }
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      <option value="">使用主模型</option>
                      {availableModels.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs leading-5 text-muted-foreground">
                      上下文压缩总结时使用的模型。建议选轻量模型省钱。
                    </p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="task-model-subagent">专家模型</Label>
                    <select
                      id="task-model-subagent"
                      value={taskModels.subagent || ""}
                      onChange={(e) =>
                        setTaskModels((prev) => ({
                          ...prev,
                          subagent: e.target.value,
                        }))
                      }
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      <option value="">使用主模型</option>
                      {availableModels.map((id) => (
                        <option key={id} value={id}>
                          {id}
                        </option>
                      ))}
                    </select>
                    <p className="text-xs leading-5 text-muted-foreground">
                      专家默认使用的模型。Manifest 中已指定时优先用 Manifest 的。
                    </p>
                  </div>
                </div>
                <Button
                  onClick={handleSaveTaskModels}
                  disabled={isSavingTaskModels}
                >
                  {isSavingTaskModels ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Save className="mr-2 h-4 w-4" />
                  )}
                  保存任务模型路由
                </Button>
              </CardContent>
            </Card>
            ) : null}

          </div>

          {showPreviewSection ? (
          <div className="space-y-6">
            <Card>
              <CardHeader
                className="cursor-pointer hover:bg-muted/40 transition-colors"
                onClick={() => toggleCard("preview")}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <CardTitle>配置预览</CardTitle>
                    <CardDescription>查看当前模式下真正会生效的合并结果</CardDescription>
                  </div>
                  <ChevronDown className={cn("h-4 w-4 text-muted-foreground transition-transform", !collapsedCards.has("preview") && "rotate-180")} />
                </div>
              </CardHeader>
              {!collapsedCards.has("preview") && (
              <CardContent className="space-y-4">
                {previewConfig ? (
                  <>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">当前编辑器装载来源:</span>
                      <Badge variant="outline">{getSourceLabel(editorScope.source)}</Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">实际生效来源:</span>
                      <Badge variant="outline">
                        {getSourceLabel(previewConfig.promptSource)}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">覆盖状态:</span>
                      <Badge variant={editorScope.hasLocalOverride ? "secondary" : "outline"}>
                        {editorScope.hasLocalOverride ? "当前层已保存覆盖" : "当前层未保存覆盖"}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">链路中存在自定义:</span>
                      <Badge variant={previewConfig.isCustomized ? "secondary" : "outline"}>
                        {previewConfig.isCustomized ? "是" : "否"}
                      </Badge>
                    </div>

                    <div className="space-y-2">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-muted-foreground">启用工具:</span>
                        <span className="text-sm font-medium">
                          {previewConfig.enabledTools.length} 个
                        </span>
                      </div>
                      {previewConfig.enabledTools.length > 0 ? (
                        <div className="flex flex-wrap gap-1.5">
                          {previewConfig.enabledTools.slice(0, 12).map((tool) => (
                            <Badge key={tool} variant="outline" className="text-[10px]">
                              {tool}
                            </Badge>
                          ))}
                          {previewConfig.enabledTools.length > 12 ? (
                            <Badge variant="secondary" className="text-[10px]">
                              +{previewConfig.enabledTools.length - 12}
                            </Badge>
                          ) : null}
                        </div>
                      ) : (
                        <div className="text-xs text-muted-foreground">无启用工具</div>
                      )}
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">工具加载策略:</span>
                      <Badge variant="outline">
                        {TOOL_STRATEGY_OPTIONS.find((o) => o.value === previewConfig.toolStrategy)?.label ?? previewConfig.toolStrategy}
                      </Badge>
                    </div>

                    <div className="flex items-center gap-2">
                      <span className="text-sm text-muted-foreground">自动压缩来源:</span>
                      <Badge variant="outline">
                        {getSourceLabel(previewConfig.runtimeSource)}
                      </Badge>
                    </div>

                    <div className="grid gap-3 md:grid-cols-2">
                      <div className="rounded-lg border border-border bg-muted/20 p-3">
                        <div className="text-xs text-muted-foreground">保留回复空间</div>
                        <div className="mt-2 text-sm font-medium text-foreground">
                          {previewConfig.reservedContextSize.toLocaleString()} tokens
                        </div>
                      </div>
                      <div className="rounded-lg border border-border bg-muted/20 p-3">
                        <div className="text-xs text-muted-foreground">
                          自动压缩触发比例
                        </div>
                        <div className="mt-2 text-sm font-medium text-foreground">
                          {previewConfig.compactionTriggerRatio.toFixed(2)}
                        </div>
                      </div>
                    </div>

                    <div className="space-y-2">
                      <span className="text-sm text-muted-foreground">工作说明预览:</span>
                      <div className="max-h-[200px] overflow-auto rounded-lg bg-muted p-3">
                        <pre className="whitespace-pre-wrap text-xs">
                          {previewConfig.systemPromptPreview}
                        </pre>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">加载预览中...</div>
                )}
              </CardContent>
              )}
            </Card>

            {isAdmin && showSystemConfig && !isSessionScope ? (
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-warning">
                    <AlertTriangle className="h-5 w-5" />
                    系统配置基线（仅管理员）
                  </CardTitle>
                  <CardDescription>修改此基线将影响所有用户</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <Textarea
                    value={systemPrompt}
                    onChange={(event) => setSystemPrompt(event.target.value)}
                    className="min-h-[300px] font-mono text-sm"
                  />
                  <Button
                    onClick={async () => {
                      try {
                        await updateSystemPrompt(activeTab, systemPrompt);
                        showSuccess("系统配置基线已更新");
                      } catch (error) {
                        showError("更新系统配置基线失败");
                        console.error(error);
                      }
                    }}
                    variant="destructive"
                  >
                    <Save className="mr-2 h-4 w-4" />
                    更新系统基线
                  </Button>
                </CardContent>
              </Card>
            ) : null}
          </div>
          ) : null}
        </div>
      )}

      </div>
      <Dialog open={showResetDialog} onOpenChange={setShowResetDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              确认重置配置
            </DialogTitle>
            <DialogDescription>
              {isSessionScope
                ? "这会删除当前会话的配置覆盖，回退到“我的默认配置”或系统基线。此操作不可撤销。"
                : "这会删除你的默认配置，恢复使用系统基线。此操作不可撤销。"}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowResetDialog(false)}>
              取消
            </Button>
            <Button variant="destructive" onClick={handleReset}>
              确认重置
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
        />
      ))}
    </div>
  );

}
