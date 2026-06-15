import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowLeft,
  Braces,
  FlaskConical,
  LayoutTemplate,
  Puzzle,
  Settings,
  Terminal,
  X,
  Zap,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";
import type { LLMModelConfig } from "@/lib/api/llm";
import type { WorkspaceConversationSummary } from "@/pages/WorkspacePage/types";
import type { TaskExecutionPolicySummary } from "@/types/autoTask";

export type WorkspaceConfigSection =
  | "env-vars"
  | "capabilities"
  | "agent-config"
  | "auto-tasks"
  | "monitor-tasks";

interface NavItem {
  id: WorkspaceConfigSection;
  label: string;
  icon: React.ReactNode;
  description: string;
}

const NAV_ITEMS: NavItem[] = [
  {
    id: "env-vars",
    label: "环境变量",
    icon: <Braces className="h-4 w-4" />,
    description: "管理全局、工作区和会话级环境变量",
  },
  {
    id: "capabilities",
    label: "能力管理",
    icon: <Puzzle className="h-4 w-4" />,
    description: "管理当前工作区已安装的能力",
  },
  {
    id: "agent-config",
    label: "工作区设置",
    icon: <Settings className="h-4 w-4" />,
    description: "配置工作说明、工具策略和运行时参数",
  },
  {
    id: "auto-tasks",
    label: "自动化任务",
    icon: <Zap className="h-4 w-4" />,
    description: "管理当前工作区的自动化任务",
  },
  {
    id: "monitor-tasks",
    label: "监控任务",
    icon: <Terminal className="h-4 w-4" />,
    description: "管理当前工作区的后台监听任务",
  },
];

interface WorkspaceConfigDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  workspaceSummary?: TaskWorkspaceSummary;
  sessionId?: string | null;
  userId?: string;
  initialSection?: WorkspaceConfigSection;
  // auto-tasks
  executionPolicy?: TaskExecutionPolicySummary | null;
  availableModels?: LLMModelConfig[];
  currentSessionId?: string | null;
  currentSessionTitle?: string | null;
  conversations?: WorkspaceConversationSummary[];
  currentConversation?: WorkspaceConversationSummary | null;
  // callbacks
  onWorkspaceUpdated?: () => void;
}

export function WorkspaceConfigDialog({
  open,
  onOpenChange,
  workspaceSummary,
  sessionId,
  userId,
  initialSection = "env-vars",
  executionPolicy,
  availableModels,
  currentSessionId,
  currentSessionTitle,
  conversations,
  currentConversation,
  onWorkspaceUpdated,
}: WorkspaceConfigDialogProps) {
  const [activeSection, setActiveSection] = useState<WorkspaceConfigSection>(initialSection);
  const [envScope, setEnvScope] = useState<"global" | "workspace">("workspace");
  const [capScope, setCapScope] = useState<"global" | "workspace">("workspace");
  const [agentScope, setAgentScope] = useState<"user" | "workspace">("workspace");

  useEffect(() => {
    if (open) {
      setActiveSection(initialSection);
    }
  }, [open, initialSection]);

  const workspaceId = workspaceSummary?.workspace_id;

  const handleClose = useCallback(() => {
    onOpenChange(false);
  }, [onOpenChange]);

  const activeNav = useMemo(
    () => NAV_ITEMS.find((item) => item.id === activeSection) ?? NAV_ITEMS[0],
    [activeSection],
  );

  const scopeSwitchBar = useMemo(() => {
    switch (activeSection) {
      case "env-vars":
        return (
          <ScopeSwitcher
            value={envScope}
            options={[
              { value: "global", label: "全局" },
              { value: "workspace", label: "当前工作区" },
            ]}
            onChange={setEnvScope}
          />
        );
      case "capabilities":
        return (
          <ScopeSwitcher
            value={capScope}
            options={[
              { value: "global", label: "全局工作区" },
              { value: "workspace", label: "当前工作区" },
            ]}
            onChange={setCapScope}
          />
        );
      case "agent-config":
        return (
          <ScopeSwitcher
            value={agentScope}
            options={[
              { value: "user", label: "用户默认" },
              { value: "workspace", label: "当前工作区" },
            ]}
            onChange={setAgentScope}
          />
        );
      default:
        return null;
    }
  }, [activeSection, envScope, capScope, agentScope]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        className="flex h-[min(720px,calc(100vh-48px))] w-[min(1100px,calc(100vw-48px))] overflow-hidden rounded-2xl border border-border bg-background shadow-2xl"
        role="dialog"
        aria-modal="true"
        aria-label="工作区配置"
      >
        {/* 左侧导航 */}
        <div className="flex w-56 shrink-0 flex-col border-r border-border bg-muted/30">
          <div className="flex h-14 items-center border-b border-border px-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <LayoutTemplate className="h-4 w-4" />
              工作区配置
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            <div className="space-y-1">
              {NAV_ITEMS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveSection(item.id)}
                  className={cn(
                    "flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                    activeSection === item.id
                      ? "bg-accent text-accent-foreground"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground",
                  )}
                >
                  <div className="flex items-center gap-2">
                    {item.icon}
                    <span className="font-medium">{item.label}</span>
                  </div>
                  <span className="line-clamp-1 text-[11px] opacity-70">
                    {item.description}
                  </span>
                </button>
              ))}
            </div>
          </div>
          {workspaceSummary ? (
            <div className="border-t border-border p-3">
              <div className="text-xs font-medium text-foreground">
                {workspaceSummary.title || "未命名工作区"}
              </div>
              <div className="mt-0.5 truncate text-[10px] text-muted-foreground">
                {workspaceSummary.workspace_id}
              </div>
            </div>
          ) : null}
        </div>

        {/* 右侧内容 */}
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex h-14 shrink-0 items-center justify-between gap-3 border-b border-border px-5">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-tertiary-container text-on-tertiary-container">
                {activeNav.icon}
              </div>
              <div className="min-w-0">
                <div className="text-sm font-semibold text-foreground">
                  {activeNav.label}
                </div>
                <div className="text-xs text-muted-foreground">
                  {activeNav.description}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={handleClose}
              className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              aria-label="关闭"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          {scopeSwitchBar}
          <div className="min-h-0 flex-1 overflow-hidden">
            <WorkspaceConfigContent
              activeSection={activeSection}
              workspaceSummary={workspaceSummary}
              workspaceId={workspaceId}
              sessionId={sessionId}
              userId={userId}
              executionPolicy={executionPolicy}
              availableModels={availableModels}
              currentSessionId={currentSessionId}
              currentSessionTitle={currentSessionTitle}
              conversations={conversations}
              currentConversation={currentConversation}
              onWorkspaceUpdated={onWorkspaceUpdated}
              envScope={envScope}
              capScope={capScope}
              agentScope={agentScope}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

function WorkspaceConfigContent({
  activeSection,
  workspaceSummary,
  workspaceId,
  sessionId,
  userId,
  executionPolicy,
  availableModels,
  currentSessionId,
  currentSessionTitle,
  conversations,
  currentConversation,
  onWorkspaceUpdated,
  envScope,
  capScope,
  agentScope,
}: {
  activeSection: WorkspaceConfigSection;
  workspaceId?: string;
  envScope: "global" | "workspace";
  capScope: "global" | "workspace";
  agentScope: "user" | "workspace";
} & Omit<WorkspaceConfigDialogProps, "open" | "onOpenChange" | "initialSection">) {
  switch (activeSection) {
    case "env-vars":
      return (
        <EnvVarsPanelWrapper
          workspaceSummary={workspaceSummary}
          onSaved={onWorkspaceUpdated}
          scope={envScope}
        />
      );
    case "capabilities":
      return (
        <CapabilityPanelWrapper
          workspaceId={workspaceId}
          scope={capScope}
        />
      );
    case "agent-config":
      return <AgentConfigPanelWrapper workspaceId={workspaceId} scope={agentScope} />;
    case "auto-tasks":
      return (
        <AutoTaskPanelWrapper
          workspaceId={workspaceId}
          executionPolicy={executionPolicy}
          availableModels={availableModels}
          currentSessionId={currentSessionId}
          currentSessionTitle={currentSessionTitle}
          conversations={conversations}
          currentConversation={currentConversation}
        />
      );
    case "monitor-tasks":
      return <MonitorPanelWrapper userId={userId} sessionId={sessionId} />;
    default:
      return null;
  }
}

// ---- lazy wrappers to keep bundle size reasonable ----

import { lazy, Suspense } from "react";

const LazyEnvVarsPanel = lazy(() =>
  import("./EnvVarsPanel").then((module) => ({ default: module.EnvVarsPanel })),
);

function EnvVarsPanelWrapper({
  workspaceSummary,
  onSaved,
  scope,
}: {
  workspaceSummary?: TaskWorkspaceSummary;
  onSaved?: () => void;
  scope: "global" | "workspace";
}) {
  return (
    <Suspense fallback={<ConfigPanelFallback label="正在加载环境变量..." />}>
      <LazyEnvVarsPanel
        key={scope}
        workspaceSummary={workspaceSummary}
        onSaved={onSaved}
        variant="runtime-dialog"
        scope={scope}
      />
    </Suspense>
  );
}

const LazyCapabilityListPanel = lazy(() =>
  import("@/components/CapabilityPanel/CapabilityListPanel").then((module) => ({
    default: module.CapabilityListPanel,
  })),
);

const LazyCapabilityDetailPanel = lazy(() =>
  import("@/components/CapabilityPanel/CapabilityDetailPanel").then((module) => ({
    default: module.CapabilityDetailPanel,
  })),
);

function CapabilityPanelWrapper({
  workspaceId,
  scope,
}: {
  workspaceId?: string;
  scope: "global" | "workspace";
}) {
  const [selectedCapId, setSelectedCapId] = useState<string | null>(null);
  const [selectedCapName, setSelectedCapName] = useState<string>("");

  if (!workspaceId) {
    return <ConfigPanelEmpty label="请先打开一个工作区" />;
  }

  if (selectedCapId) {
    return (
      <Suspense fallback={<ConfigPanelFallback label="正在加载能力详情..." />}>
        <div className="flex h-full flex-col">
          <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-muted/20 px-4">
            <button
              type="button"
              onClick={() => setSelectedCapId(null)}
              className="inline-flex h-7 w-7 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              title="返回列表"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <span className="text-sm font-medium text-muted-foreground">
              返回能力列表
            </span>
            {selectedCapName && (
              <>
                <span className="text-muted-foreground/50">/</span>
                <span className="truncate text-sm font-medium">{selectedCapName}</span>
              </>
            )}
          </div>
          <div className="min-h-0 flex-1">
            <LazyCapabilityDetailPanel
              workspaceId={workspaceId}
              capabilityId={selectedCapId}
              scope={scope}
            />
          </div>
        </div>
      </Suspense>
    );
  }

  return (
    <Suspense fallback={<ConfigPanelFallback label="正在加载能力管理..." />}>
      <LazyCapabilityListPanel
        key={scope}
        workspaceId={workspaceId}
        scope={scope}
        mode="workspace-config"
        onSelectCap={(capId, displayName) => {
          setSelectedCapId(capId);
          setSelectedCapName(displayName);
        }}
      />
    </Suspense>
  );
}

const LazyWorkspaceAgentConfigPanel = lazy(() =>
  import("./WorkspaceAgentConfigPanel").then((module) => ({
    default: module.WorkspaceAgentConfigPanel,
  })),
);

function AgentConfigPanelWrapper({
  workspaceId,
  scope,
}: {
  workspaceId?: string;
  scope: "user" | "workspace";
}) {
  if (!workspaceId && scope === "workspace") {
    return <ConfigPanelEmpty label="请先打开一个工作区" />;
  }
  return (
    <Suspense fallback={<ConfigPanelFallback label="正在加载工作区设置..." />}>
      <LazyWorkspaceAgentConfigPanel
        key={scope}
        workspaceId={workspaceId || ""}
        scope={scope}
      />
    </Suspense>
  );
}

const LazyWorkspaceAutoTaskPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/WorkspaceAutoTaskPanel").then((module) => ({
    default: module.WorkspaceAutoTaskPanel,
  })),
);

function AutoTaskPanelWrapper({
  workspaceId,
  executionPolicy,
  availableModels,
  currentSessionId,
  currentSessionTitle,
  conversations,
  currentConversation,
}: Omit<WorkspaceConfigDialogProps, "open" | "onOpenChange" | "initialSection" | "workspaceSummary" | "sessionId" | "userId"> & {
  workspaceId?: string;
}) {
  if (!workspaceId) {
    return <ConfigPanelEmpty label="请先打开一个工作区" />;
  }
  return (
    <Suspense fallback={<ConfigPanelFallback label="正在加载自动化任务..." />}>
      <LazyWorkspaceAutoTaskPanel
        workspaceId={workspaceId}
        executionPolicy={executionPolicy}
        availableModels={availableModels}
        currentSessionId={currentSessionId}
        currentSessionTitle={currentSessionTitle}
        conversations={conversations}
        currentConversation={currentConversation}
      />
    </Suspense>
  );
}

const LazyWorkspaceMonitorPanel = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/WorkspaceMonitorPanel").then((module) => ({
    default: module.WorkspaceMonitorPanel,
  })),
);

function MonitorPanelWrapper({
  userId,
  sessionId,
}: {
  userId?: string;
  sessionId?: string | null;
}) {
  if (!userId || !sessionId) {
    return <ConfigPanelEmpty label="当前没有活跃会话" />;
  }
  return (
    <Suspense fallback={<ConfigPanelFallback label="正在加载监控任务..." />}>
      <LazyWorkspaceMonitorPanel userId={userId} sessionId={sessionId} />
    </Suspense>
  );
}

function ConfigPanelFallback({ label }: { label: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-sm text-muted-foreground">
      <FlaskConical className="h-6 w-6 animate-pulse" />
      {label}
    </div>
  );
}

function ConfigPanelEmpty({ label }: { label: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center text-sm text-muted-foreground">
      <LayoutTemplate className="h-6 w-6 opacity-40" />
      {label}
    </div>
  );
}

function ScopeSwitcher<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 border-b bg-muted/20 px-5">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
            value === opt.value
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
