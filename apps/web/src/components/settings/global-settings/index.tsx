import { useState, useEffect, useCallback, lazy, Suspense, useMemo, useRef } from "react";
import {
  ChevronDown,
  ChevronRight,
  Server,
  Braces,
  FolderCog,
  Globe,
  Puzzle,
  Zap,
  Terminal,
  Blocks,
  FlaskConical,
  LayoutTemplate,
  Store,
  Search,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";
import type { LLMModelConfig } from "@/lib/api/llm";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

export type SettingsSection =
  | "llm"
  | "env-vars"
  | "storage"
  | "uv-mirror"
  | "capabilities"
  | "tool-strategy"
  | "execution-resources"
  | "auto-tasks"
  | "monitor-tasks"
  | "template-management"
  | "template-market";

interface NavGroup {
  id: string;
  label: string;
  children: Array<{
    id: SettingsSection;
    label: string;
    icon: React.ReactNode;
  }>;
}

const NAV_GROUPS: NavGroup[] = [
  {
    id: "market",
    label: "能力市场",
    children: [
      { id: "capabilities", label: "能力管理", icon: <Puzzle className="h-4 w-4" /> },
      { id: "tool-strategy", label: "我的默认配置", icon: <Zap className="h-4 w-4" /> },
    ],
  },
  {
    id: "env",
    label: "环境与配置",
    children: [
      { id: "llm", label: "模型配置", icon: <Server className="h-4 w-4" /> },
      { id: "env-vars", label: "全局环境变量", icon: <Braces className="h-4 w-4" /> },
      { id: "uv-mirror", label: "uv 包管理器镜像", icon: <Globe className="h-4 w-4" /> },
      { id: "storage", label: "存储位置", icon: <FolderCog className="h-4 w-4" /> },
      { id: "execution-resources", label: "Python 与执行资源", icon: <FlaskConical className="h-4 w-4" /> },
    ],
  },
  {
    id: "tasks",
    label: "全局任务管理",
    children: [
      { id: "auto-tasks", label: "自动化任务", icon: <Zap className="h-4 w-4" /> },
      { id: "monitor-tasks", label: "监控任务", icon: <Terminal className="h-4 w-4" /> },
    ],
  },
  {
    id: "templates",
    label: "模板",
    children: [
      { id: "template-market", label: "模板市场", icon: <Store className="h-4 w-4" /> },
      { id: "template-management", label: "模板管理", icon: <LayoutTemplate className="h-4 w-4" /> },
    ],
  },
];

const SECTION_META: Record<
  SettingsSection,
  { title: string; description: string; icon: typeof Server }
> = {
  llm: {
    title: "模型配置",
    description: "配置 LLM 服务商连接信息和模型参数",
    icon: Server,
  },
  "env-vars": {
    title: "全局环境变量",
    description: "对所有工作区生效的环境变量配置",
    icon: Braces,
  },
  storage: {
    title: "存储位置",
    description: "配置新建工作区、全局资源和日志的默认落盘位置",
    icon: FolderCog,
  },
  "uv-mirror": {
    title: "uv 包管理器镜像",
    description: "配置 PyPI、Python 二进制和 uv 安装器的国内镜像源",
    icon: Globe,
  },
  capabilities: {
    title: "能力管理",
    description: "统一管理技能、连接器和协作专家的安装、启用与禁用",
    icon: Puzzle,
  },
  "tool-strategy": {
    title: "我的默认配置",
    description: "配置跨工作区共享的个人基线：工作说明、工具选择、加载策略、运行时参数和任务模型路由",
    icon: Zap,
  },
  "execution-resources": {
    title: "Python 与执行资源",
    description: "管理 Python 环境、Docker 容器和注入变量",
    icon: FlaskConical,
  },
  "auto-tasks": {
    title: "全局自动化任务",
    description: "查看和管理跨工作区的自动化任务",
    icon: Zap,
  },
  "monitor-tasks": {
    title: "全局监控任务",
    description: "查看和管理后台监控任务执行状态",
    icon: Terminal,
  },
  "template-management": {
    title: "模板管理",
    description: "浏览和管理工作区模板",
    icon: LayoutTemplate,
  },
  "template-market": {
    title: "模板市场",
    description: "浏览和安装系统内置模板",
    icon: Store,
  },
};

const LAST_SECTION_KEY = "aiasys:last-settings-section";

interface GlobalSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialSection?: SettingsSection;
  workspaceId?: string | null;
  workspaceTitle?: string | null;
  userId?: string;
  workspaces?: TaskWorkspaceSummary[];
  availableModels?: LLMModelConfig[];
}

export function GlobalSettingsDialog({
  open,
  onOpenChange,
  initialSection = "llm",
  workspaceId,
  workspaceTitle,
  userId,
  workspaces,
  availableModels,
}: GlobalSettingsDialogProps) {
  const [activeSection, setActiveSection] = useState<SettingsSection>(initialSection);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(
    () => new Set(["env", "market", "tasks", "templates"])
  );
  const [searchQuery, setSearchQuery] = useState("");
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (open && initialSection) {
      setActiveSection(initialSection);
    }
  }, [open, initialSection]);

  useEffect(() => {
    try {
      localStorage.setItem(LAST_SECTION_KEY, activeSection);
    } catch {
      // 存储不可用时静默忽略（如隐私模式或配额已满）
    }
  }, [activeSection]);

  useEffect(() => {
    if (!open) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = original;
    };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      // Don't close if focus is inside a child dialog/sheet/alert-dialog
      const target = e.target as Element | null;
      if (target?.closest('[role="dialog"], [role="alertdialog"]')) {
        return;
      }
      onOpenChange(false);
    };
    // Use capture phase so this runs before Radix dialog handlers
    document.addEventListener("keydown", handleEscape, true);
    return () => document.removeEventListener("keydown", handleEscape, true);
  }, [open, onOpenChange]);

  const toggleGroup = useCallback((groupId: string) => {
    setExpandedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(groupId)) next.delete(groupId);
      else next.add(groupId);
      return next;
    });
  }, []);

  const handleSelectSection = (section: SettingsSection) => {
    setActiveSection(section);
  };

  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return NAV_GROUPS;
    const q = searchQuery.toLowerCase();
    return NAV_GROUPS.map((group) => ({
      ...group,
      children: group.children.filter((child) => {
        const desc = SECTION_META[child.id]?.description ?? "";
        return (
          child.label.toLowerCase().includes(q) ||
          desc.toLowerCase().includes(q)
        );
      }),
    })).filter((group) => group.children.length > 0);
  }, [searchQuery]);

  const isSearching = searchQuery.trim().length > 0;
  const displayGroups = isSearching ? filteredGroups : NAV_GROUPS;

  const getFocusableNavItems = useCallback(() => {
    if (!navRef.current) return [];
    return Array.from(
      navRef.current.querySelectorAll<HTMLElement>("button:not([disabled])")
    );
  }, []);

  const handleNavKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      const items = getFocusableNavItems();
      const currentIndex = items.findIndex(
        (item) => item === document.activeElement
      );
      if (currentIndex === -1) return;

      switch (e.key) {
        case "ArrowDown": {
          e.preventDefault();
          const nextIndex =
            currentIndex < items.length - 1 ? currentIndex + 1 : 0;
          items[nextIndex]?.focus();
          break;
        }
        case "ArrowUp": {
          e.preventDefault();
          const prevIndex =
            currentIndex > 0 ? currentIndex - 1 : items.length - 1;
          items[prevIndex]?.focus();
          break;
        }
        case "Home": {
          e.preventDefault();
          items[0]?.focus();
          break;
        }
        case "End": {
          e.preventDefault();
          items[items.length - 1]?.focus();
          break;
        }
        case "ArrowLeft": {
          const currentItem = items[currentIndex];
          const groupId = currentItem?.dataset.groupId;
          if (groupId && expandedGroups.has(groupId)) {
            e.preventDefault();
            toggleGroup(groupId);
          }
          break;
        }
        case "ArrowRight": {
          const currentItem = items[currentIndex];
          const groupId = currentItem?.dataset.groupId;
          if (groupId && !expandedGroups.has(groupId)) {
            e.preventDefault();
            toggleGroup(groupId);
          }
          break;
        }
      }
    },
    [getFocusableNavItems, expandedGroups, toggleGroup]
  );

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={() => onOpenChange(false)}
      />
      {/* Panel */}
      <div
        className="relative z-10 w-full max-w-5xl h-[92vh] overflow-hidden flex flex-col bg-background border border-border rounded-lg shadow-xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby="global-settings-title"
        aria-describedby="global-settings-desc"
      >
        <span id="global-settings-title" className="sr-only">
          全局控制面板
        </span>
        <span id="global-settings-desc" className="sr-only">
          管理模型、环境变量、存储、能力市场、协作专家和全局任务。
        </span>
        <button
          type="button"
          onClick={() => onOpenChange(false)}
          className="absolute top-3 right-3 z-20 rounded-md p-1.5 text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-hidden"
        >
          <X className="h-4 w-4" />
          <span className="sr-only">关闭</span>
        </button>
        <div className="flex h-full">
          {/* 左侧导航 */}
          <aside className="w-56 shrink-0 border-r border-border bg-sidebar flex flex-col">
            <div className="p-3 border-b border-border">
              <div className="flex items-center gap-2 px-2.5 py-2">
                <Blocks className="h-4 w-4 text-foreground" />
                <span className="text-sm font-medium text-foreground">全局控制面板</span>
              </div>
              <div className="relative mt-1">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  placeholder="搜索设置..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
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
            <nav
              ref={navRef}
              className="flex-1 overflow-y-auto py-2"
              onKeyDown={handleNavKeyDown}
            >
              {displayGroups.map((group) => {
                const groupExpanded = isSearching || expandedGroups.has(group.id);
                return (
                  <div key={group.id} className="px-2 mb-1">
                    <button
                      type="button"
                      onClick={() => toggleGroup(group.id)}
                      data-group-id={group.id}
                      className="flex w-full items-center gap-1 px-2 py-1 text-xs text-muted-fg hover:text-foreground transition-colors cursor-pointer rounded focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-hidden"
                    >
                      {groupExpanded ? (
                        <ChevronDown className="w-3 h-3" />
                      ) : (
                        <ChevronRight className="w-3 h-3" />
                      )}
                      <span>{group.label}</span>
                    </button>
                    {groupExpanded && (
                      <div className="mt-0.5 space-y-0.5">
                        {group.children.map((child) => {
                          const isDisabled = child.id === "env-vars" && !userId;
                          const button = (
                            <button
                              key={child.id}
                              type="button"
                              onClick={() => !isDisabled && handleSelectSection(child.id)}
                              disabled={isDisabled}
                              aria-current={activeSection === child.id ? "page" : undefined}
                              className={cn(
                                "relative flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors pl-6 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-hidden",
                                activeSection === child.id
                                  ? "bg-primary/10 text-primary"
                                  : "text-muted-fg hover:bg-accent hover:text-accent-fg",
                                isDisabled && "opacity-50 cursor-not-allowed"
                              )}
                            >
                              {activeSection === child.id && (
                                <span className="absolute left-0 top-1.5 bottom-1.5 w-0.5 rounded-full bg-tertiary" />
                              )}
                              {child.icon}
                              <span>{child.label}</span>
                            </button>
                          );
                          return isDisabled ? (
                            <Tooltip key={child.id}>
                              <TooltipTrigger asChild>
                                <span className="block">{button}</span>
                              </TooltipTrigger>
                              <TooltipContent>需要登录</TooltipContent>
                            </Tooltip>
                          ) : (
                            button
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
              {isSearching && displayGroups.length === 0 && (
                <div className="px-4 py-8 text-center text-xs text-muted-foreground">
                  未找到匹配设置
                </div>
              )}
            </nav>
          </aside>

          {/* 右侧内容 */}
          <main className="flex-1 flex flex-col min-w-0 bg-background">
            <div className="h-14 border-b border-border flex items-center px-5 shrink-0 gap-3">
              {(() => {
                const meta = SECTION_META[activeSection];
                const Icon = meta.icon;
                return (
                  <>
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-tertiary-container text-on-tertiary-container">
                      <Icon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <h2 className="text-sm font-semibold text-foreground">{meta.title}</h2>
                      <p className="truncate text-xs text-muted-foreground">{meta.description}</p>
                    </div>
                  </>
                );
              })()}
            </div>
            <div className="flex-1 overflow-y-auto min-h-0">
              <GlobalSettingsContent
                section={activeSection}
                workspaceId={workspaceId}
                workspaceTitle={workspaceTitle}
                userId={userId}
                workspaces={workspaces}
                availableModels={availableModels}
              />
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

const LazyCapabilityPanel = lazy(() =>
  import("@/components/CapabilityPanel").then((m) => ({
    default: m.CapabilityPanel,
  }))
);
const LazyGlobalEnvVarsDialog = lazy(() =>
  import("@/components/workspace/GlobalEnvVarsDialog").then((m) => ({
    default: m.GlobalEnvVarsDialog,
  }))
);
const LazyLLMConfigPanel = lazy(() =>
  import("@/components/settings/llm-config").then((m) => ({
    default: m.default,
  }))
);
const LazyExecutionResourcesPanel = lazy(() =>
  import("@/components/execution-resources/ExecutionResourcesPanel").then((m) => ({
    default: m.ExecutionResourcesPanel,
  }))
);
const LazyStorageSettingsDialog = lazy(() =>
  import("@/components/settings/StorageSettingsDialog").then((m) => ({
    default: m.StorageSettingsDialog,
  }))
);
const LazyGlobalAutoTaskDialog = lazy(() =>
  import("@/components/workspace/dialogs/GlobalAutoTaskDialog").then((m) => ({
    default: m.default,
  }))
);
const LazyGlobalMonitorDialog = lazy(() =>
  import("@/components/workspace/dialogs/GlobalMonitorDialog").then((m) => ({
    default: m.default,
  }))
);

const LazyAgentConfigPanel = lazy(() =>
  import("@/components/agent-config/AgentConfigPanel").then((m) => ({
    default: m.default,
  }))
);
const LazyTemplateManagementPanel = lazy(() =>
  import("@/components/settings/TemplateManagementPanel").then((m) => ({
    default: m.TemplateManagementPanel,
  }))
);
const LazyTemplateMarketPanel = lazy(() =>
  import("@/components/settings/TemplateMarketPanel").then((m) => ({
    default: m.TemplateMarketPanel,
  }))
);
const LazyUvMirrorSettings = lazy(() =>
  import("@/components/settings/UvMirrorSettings").then((m) => ({
    default: m.UvMirrorSettings,
  }))
);

function ContentFallback() {
  return (
    <div className="flex flex-col h-full p-6 gap-6">
      <div className="flex items-center gap-3">
        <Skeleton className="h-8 w-8 rounded-lg shrink-0" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-3 w-48" />
        </div>
      </div>
      <div className="space-y-4">
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <Skeleton className="h-24 w-full rounded-lg" />
      </div>
    </div>
  );
}

interface GlobalSettingsContentProps {
  section: SettingsSection;
  workspaceId?: string | null;
  workspaceTitle?: string | null;
  userId?: string;
  workspaces?: TaskWorkspaceSummary[];
  availableModels?: LLMModelConfig[];
}

function GlobalSettingsContent({ section, workspaceId, workspaceTitle, userId, workspaces, availableModels }: GlobalSettingsContentProps) {
  switch (section) {
    case "capabilities":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyCapabilityPanel workspaceId={workspaceId ?? ""} scope="global" />
          </Suspense>
        </div>
      );
    case "env-vars":
      return (
        <div className="h-full p-6">
          <Suspense fallback={<ContentFallback />}>
            <LazyGlobalEnvVarsDialog userId={userId!} />
          </Suspense>
        </div>
      );
    case "llm":
      return (
        <div className="h-full p-6 overflow-y-auto">
          <Suspense fallback={<ContentFallback />}>
            <LazyLLMConfigPanel />
          </Suspense>
        </div>
      );
    case "execution-resources":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyExecutionResourcesPanel
              workspaceId={workspaceId}
              workspaceTitle={workspaceTitle}
              workspaceSummary={
                workspaces?.find((w) => w.workspace_id === workspaceId) ?? null
              }
            />
          </Suspense>
        </div>
      );
    case "storage":
      return (
        <div className="h-full p-6">
          <Suspense fallback={<ContentFallback />}>
            <LazyStorageSettingsDialog />
          </Suspense>
        </div>
      );
    case "uv-mirror":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyUvMirrorSettings />
          </Suspense>
        </div>
      );
    case "auto-tasks":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyGlobalAutoTaskDialog
              currentWorkspaceId={workspaceId}
              workspaces={workspaces ?? []}
              availableModels={availableModels}
            />
          </Suspense>
        </div>
      );
    case "monitor-tasks":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyGlobalMonitorDialog
              currentWorkspaceId={workspaceId}
              workspaces={workspaces ?? []}
            />
          </Suspense>
        </div>
      );

    case "tool-strategy":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyAgentConfigPanel workspaceId={workspaceId} />
          </Suspense>
        </div>
      );
    case "template-management":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyTemplateManagementPanel />
          </Suspense>
        </div>
      );
    case "template-market":
      return (
        <div className="h-full">
          <Suspense fallback={<ContentFallback />}>
            <LazyTemplateMarketPanel />
          </Suspense>
        </div>
      );
    default:
      return (
        <div className="flex h-full flex-col items-center justify-center text-muted-fg">
          <Blocks className="w-10 h-10 mb-3 opacity-40" />
          <p className="text-sm">未知设置</p>
          <p className="text-xs mt-1 opacity-60">此处为示意内容</p>
        </div>
      );
  }
}
