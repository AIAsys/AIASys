import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Container,
  KeyRound,
  Loader2,
  RefreshCw,
  SquareTerminal,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import type { KernelEnvItem } from "@/lib/api/kernelEnvs";
import {
  bindWorkspaceRuntimeEnvironment,
  ensureWorkspaceUvEnvironment,
  getWorkspaceRuntimeEnvironments,
  installWorkspaceRuntimePackages,
  registerWorkspacePythonEnvironment,
  updateTaskWorkspace,
  unregisterWorkspaceRuntimeEnvironment,
} from "@/lib/api/workspaces";
import type {
  WorkspaceContainerResource,
  WorkspaceRuntimeEnvironment,
  WorkspaceRuntimeEnvironmentRegistry,
} from "@/types/workspace";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";
import { cn } from "@/lib/utils";
import { EnvVarsPanel } from "@/components/workspace/EnvVarsPanel";
import { PythonRuntimeTab } from "./PythonRuntimeTab";
import { ContainerResourcesPanel } from "@/components/container-resources/ContainerResourcesPanel";

type RuntimePanelSection = "overview" | "python" | "docker" | "env";
type PanelNotice = { type: "success" | "error" | "info"; message: string } | null;

interface ExecutionResourcesPanelProps {
  workspaceId?: string | null;
  workspaceTitle?: string | null;
  workspaceSummary?: TaskWorkspaceSummary | null;
  onWorkspaceUpdated?: () => void | Promise<void>;
}

const statusLabels: Record<string, string> = {
  registered: "已登记",
  ready: "可使用",
  running: "运行中",
  stopped: "已停止",
  missing: "缺失",
  unavailable: "不可用",
  error: "异常",
};

function runtimeStatusVariant(status?: string) {
  if (status === "ready" || status === "running") return "success";
  if (status === "registered" || status === "stopped") return "info";
  if (status === "missing" || status === "unavailable" || status === "error") {
    return "error";
  }
  return "secondary";
}

function runtimeStatusLabel(status?: string) {
  return status ? statusLabels[status] ?? status : "未检测";
}

function envKindLabel(_kind: WorkspaceRuntimeEnvironment["kind"]) {
  return _kind === "registered_python" ? "已登记 Python" : "UV";
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

function getActiveRuntimeEnv(
  registry: WorkspaceRuntimeEnvironmentRegistry | null,
) {
  const envs = registry?.envs ?? [];
  return (
    envs.find((env) => env.active) ??
    envs.find((env) => env.env_id === registry?.active_env_id) ??
    null
  );
}

type BadgeVariant =
  | "default"
  | "secondary"
  | "outline"
  | "success"
  | "warning"
  | "error"
  | "info";

function NoticeBanner({ notice }: { notice: PanelNotice }) {
  if (!notice) return null;
  const tone =
    notice.type === "success"
      ? "border-success/30 bg-success-container text-on-success-container"
      : notice.type === "error"
        ? "border-error/30 bg-error-container text-on-error-container"
        : "border-info/30 bg-info-container text-on-info-container";

  return (
    <div className={cn("rounded-lg border px-3 py-2 text-sm", tone)}>
      {notice.message}
    </div>
  );
}

function OverviewMetric({
  label,
  value,
  description,
  variant = "outline",
}: {
  label: string;
  value: string;
  description: string;
  variant?: BadgeVariant;
}) {
  return (
    <div className="rounded-xl border border-border bg-background px-3 py-3">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-semibold text-muted-foreground">
          {label}
        </div>
        <Badge variant={variant} className="shrink-0 whitespace-nowrap">
          {value}
        </Badge>
      </div>
      <div className="mt-2 text-xs leading-5 text-muted-foreground">
        {description}
      </div>
    </div>
  );
}

function OverviewAction({
  icon,
  title,
  description,
  badge,
  onClick,
}: {
  icon: ReactNode;
  title: string;
  description: string;
  badge?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-w-0 items-start gap-3 rounded-xl border border-border bg-background px-3 py-3 text-left transition-colors hover:border-tertiary/40 hover:bg-muted/30"
    >
      <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center gap-2">
          <span className="truncate text-sm font-semibold text-foreground">
            {title}
          </span>
          {badge ? <Badge variant="secondary">{badge}</Badge> : null}
        </span>
        <span className="mt-1 block text-xs leading-5 text-muted-foreground">
          {description}
        </span>
      </span>
    </button>
  );
}

function ExecutionResourcesOverview({
  workspaceId,
  workspaceTitle,
  registry,
  isLoading,
  error,
  notice,
  isEnsuringUv,
  onRefresh,
  onEnsureUv,
  onOpenSection,
  activeSandboxMode,
  activeSandboxResourceId,
  containerResources,
  envVarsCount,
}: {
  workspaceId?: string | null;
  workspaceTitle?: string | null;
  registry: WorkspaceRuntimeEnvironmentRegistry | null;
  isLoading: boolean;
  error: string | null;
  notice: PanelNotice;
  isEnsuringUv: boolean;
  onRefresh: () => void;
  onEnsureUv: () => void;
  onOpenSection: (section: RuntimePanelSection) => void;
  activeSandboxMode: string | null;
  activeSandboxResourceId: string | null;
  containerResources: WorkspaceContainerResource[];
  envVarsCount: number;
}) {
  const envs = registry?.envs ?? [];
  const uvEnvs = envs.filter((env) => env.kind === "uv");
  const registeredPythonEnvs = envs.filter((env) => env.kind === "registered_python");
  const activeEnv = getActiveRuntimeEnv(registry);
  const envLabel = activeEnv
    ? activeEnv.display_name
    : "未设置";
  const activeUpdatedAt = formatDate(activeEnv?.updated_at);
  const isDockerActive = activeSandboxMode === "docker";
  const executionLabel = isDockerActive ? "Docker 沙盒" : "本地 Python";
  const dockerLabel = activeSandboxResourceId || "未选中";
  const pythonStatusVariant = activeEnv
    ? runtimeStatusVariant(activeEnv.status)
    : "warning";
  const dockerStatusVariant = isDockerActive ? "success" : "secondary";
  const loadedDockerCount = containerResources.length;

  return (
    <div className="space-y-4">
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-xs font-semibold text-muted-foreground">
              当前执行入口
            </div>
            <h3 className="mt-1 truncate text-xl font-semibold text-foreground">
              {executionLabel}
            </h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
              {workspaceTitle || "当前工作区"} 的代码执行资源集中在这里查看。Python、Docker 和注入变量分别进入独立分组管理。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!workspaceId || isEnsuringUv}
              onClick={onEnsureUv}
            >
              {isEnsuringUv ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              启用 Python
            </Button>
          </div>
        </div>

        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <OverviewMetric
            label="Python"
            value={activeEnv ? runtimeStatusLabel(activeEnv.status) : "未设置"}
            variant={pythonStatusVariant}
            description={
              activeEnv
                ? `${envKindLabel(activeEnv.kind)} · ${envLabel}`
                : "启用 UV 或登记已有解释器"
            }
          />
          <OverviewMetric
            label="Docker"
            value={isDockerActive ? "当前" : "未启用"}
            variant={dockerStatusVariant}
            description={
              isDockerActive
                ? dockerLabel
                : loadedDockerCount
                  ? `${loadedDockerCount} 个沙盒可选`
                  : "需要容器执行时单独启用"
            }
          />
          <OverviewMetric
            label="工作区变量"
            value={`${envVarsCount} 个`}
            description="随 Shell、Python 和 Notebook 执行注入"
          />
          <OverviewMetric
            label="工作区登记"
            value={`${registry?.total ?? envs.length} 个`}
            description={`UV ${uvEnvs.length} 个，已登记 ${registeredPythonEnvs.length} 个`}
          />
        </div>

        <NoticeBanner notice={notice} />

        {error ? (
          <div className="mt-4 rounded-lg border border-error/30 bg-error-container px-3 py-2 text-sm text-on-error-container">
            {error}
          </div>
        ) : null}

        {isLoading && envs.length === 0 ? (
          <div className="mt-4 flex items-center rounded-xl border border-dashed border-border bg-background px-4 py-4 text-sm text-muted-foreground">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在检查执行资源...
          </div>
        ) : null}
      </section>

      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="text-sm font-semibold text-foreground">资源管理</div>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          概览页只放当前状态。需要修改配置时，从下面进入对应分组。
        </p>
        <div className="mt-4 grid gap-3 md:grid-cols-3">
          <OverviewAction
            icon={<SquareTerminal className="h-4 w-4 text-tertiary" />}
            title="Python 环境"
            description={
              activeEnv
                ? `${envLabel} · ${activeUpdatedAt || "等待检测"}`
                : "创建工作区 UV，或绑定本机解释器"
            }
            badge={envs.length ? `${envs.length}` : undefined}
            onClick={() => onOpenSection("python")}
          />
          <OverviewAction
            icon={<Container className="h-4 w-4 text-info" />}
            title="Docker 沙盒"
            description={
              activeSandboxResourceId
                ? `当前沙盒 ${activeSandboxResourceId}`
                : "登记容器，并按需设为当前 Docker 沙盒"
            }
            badge={isDockerActive ? "当前" : undefined}
            onClick={() => onOpenSection("docker")}
          />
          <OverviewAction
            icon={<KeyRound className="h-4 w-4 text-tertiary" />}
            title="工作区变量"
            description="管理当前工作区注入执行环境的变量"
            badge={envVarsCount ? `${envVarsCount}` : undefined}
            onClick={() => onOpenSection("env")}
          />
        </div>
      </section>

      {!activeEnv ? (
        <div className="rounded-xl border border-warning/30 bg-warning-container/60 px-4 py-3 text-sm text-on-warning-container">
          当前工作区还没有绑定 Python。普通对话可以继续，代码执行前建议先启用 Python 或登记解释器。
        </div>
      ) : null}
    </div>
  );
}

export function ExecutionResourcesPanel({
  workspaceId,
  workspaceTitle,
  workspaceSummary,
  onWorkspaceUpdated,
}: ExecutionResourcesPanelProps) {
  const [activeSection, setActiveSection] =
    useState<RuntimePanelSection>("overview");
  const [registry, setRegistry] =
    useState<WorkspaceRuntimeEnvironmentRegistry | null>(null);
  const [isLoadingRegistry, setIsLoadingRegistry] = useState(false);
  const [registryError, setRegistryError] = useState<string | null>(null);
  const [notice, setNotice] = useState<PanelNotice>(null);
  const [isEnsuringUv, setIsEnsuringUv] = useState(false);
  const [bindingEnvId, setBindingEnvId] = useState<string | null>(null);
  const [unregisteringEnvId, setUnregisteringEnvId] = useState<string | null>(null);
  const [installingEnvId, setInstallingEnvId] = useState<string | null>(null);
  const [containerResources, setContainerResources] = useState<WorkspaceContainerResource[]>([]);
  const [selectingSandboxId, setSelectingSandboxId] = useState<string | null>(null);
  const [showUvConfirmDialog, setShowUvConfirmDialog] = useState(false);

  const loadRegistry = useCallback(async () => {
    if (!workspaceId) {
      setRegistry(null);
      setRegistryError(null);
      return;
    }
    setIsLoadingRegistry(true);
    try {
      setRegistryError(null);
      const data = await getWorkspaceRuntimeEnvironments(workspaceId, {
        inspect: true,
      });
      setRegistry(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载 Python 环境失败";
      setRegistryError(message);
    } finally {
      setIsLoadingRegistry(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    void loadRegistry();
  }, [loadRegistry]);

  useEffect(() => {
    if (!workspaceId) return;
    const timer = window.setInterval(() => {
      void loadRegistry();
    }, 30000);
    return () => window.clearInterval(timer);
  }, [loadRegistry, workspaceId]);

  const handleEnsureUv = useCallback(async () => {
    if (!workspaceId) return;
    setIsEnsuringUv(true);
    setNotice(null);
    try {
      await ensureWorkspaceUvEnvironment(workspaceId, {
        envId: "workspace-default",
        displayName: "工作区 UV",
        createVenv: true,
        sync: false,
      });
      setNotice({ type: "success", message: "工作区 UV 环境已初始化。" });
      await loadRegistry();
    } catch (err) {
      const message = err instanceof Error ? err.message : "启用 Python 失败";
      setNotice({ type: "error", message });
    } finally {
      setIsEnsuringUv(false);
    }
  }, [loadRegistry, workspaceId]);

  const handleEnsureUvWithConfirm = useCallback(() => {
    if (registry?.uv_available === false) {
      setShowUvConfirmDialog(true);
      return;
    }
    void handleEnsureUv();
  }, [registry?.uv_available, handleEnsureUv]);

  const handleBindDefault = useCallback(
    async (envId: string) => {
      if (!workspaceId) return;
      setBindingEnvId(envId);
      setNotice(null);
      try {
        await bindWorkspaceRuntimeEnvironment(workspaceId, { envId });
        setNotice({ type: "success", message: "Python 环境已更新。" });
        await loadRegistry();
      } catch (err) {
        const message = err instanceof Error ? err.message : "设置 Python 环境失败";
        setNotice({ type: "error", message });
      } finally {
        setBindingEnvId(null);
      }
    },
    [loadRegistry, workspaceId],
  );

  const handleRegisterPython = useCallback(
    async (env: KernelEnvItem) => {
      if (!workspaceId || !env.executable) return;
      setBindingEnvId(env.name);
      setNotice(null);
      try {
        await registerWorkspacePythonEnvironment(workspaceId, {
          envId: `python-${env.name}`,
          displayName: env.display_name || `Python (${env.name})`,
          pythonExecutable: env.executable,
          sourceKernelName: env.name,
          activate: true,
        });
        setNotice({ type: "success", message: "已把解释器设为当前工作区 Python。" });
        await loadRegistry();
        await onWorkspaceUpdated?.();
      } catch (err) {
        const message = err instanceof Error ? err.message : "登记 Python 解释器失败";
        setNotice({ type: "error", message });
      } finally {
        setBindingEnvId(null);
      }
    },
    [loadRegistry, onWorkspaceUpdated, workspaceId],
  );

  const handleUnregisterEnv = useCallback(
    async (envId: string) => {
      if (!workspaceId) return;
      setUnregisteringEnvId(envId);
      setNotice(null);
      try {
        await unregisterWorkspaceRuntimeEnvironment(workspaceId, envId);
        setNotice({
          type: "success",
          message: "已从当前工作区取消登记。本机环境模板和运行实例没有删除。",
        });
        await loadRegistry();
      } catch (err) {
        const message = err instanceof Error ? err.message : "取消登记失败";
        setNotice({ type: "error", message });
      } finally {
        setUnregisteringEnvId(null);
      }
    },
    [loadRegistry, workspaceId],
  );

  const handleInstallPackages = useCallback(
    async (envId: string, packages: string[]) => {
      if (!workspaceId) return;
      setInstallingEnvId(envId);
      setNotice(null);
      try {
        await installWorkspaceRuntimePackages(workspaceId, envId, { packages });
        setNotice({ type: "success", message: `已安装 ${packages.join(", ")}。` });
        await loadRegistry();
      } catch (err) {
        const message = err instanceof Error ? err.message : "安装依赖失败";
        setNotice({ type: "error", message });
        throw err;
      } finally {
        setInstallingEnvId(null);
      }
    },
    [loadRegistry, workspaceId],
  );

  const handleSelectDockerSandbox = useCallback(
    async (resource: WorkspaceContainerResource) => {
      if (!workspaceId) return;
      setSelectingSandboxId(resource.container_id);
      setNotice(null);
      try {
        await updateTaskWorkspace(workspaceId, {
          runtimeBinding: {
            sandbox_mode: "docker",
            env_id: resource.container_id,
            env_vars: workspaceSummary?.runtime_binding?.env_vars ?? undefined,
          },
        });
        setNotice({ type: "success", message: "当前工作区已切换到 Docker 沙盒。" });
        await onWorkspaceUpdated?.();
      } catch (err) {
        const message = err instanceof Error ? err.message : "切换 Docker 沙盒失败";
        setNotice({ type: "error", message });
      } finally {
        setSelectingSandboxId(null);
      }
    },
    [onWorkspaceUpdated, workspaceId, workspaceSummary?.runtime_binding?.env_vars],
  );



  const activeSandboxMode = workspaceSummary?.runtime_binding?.sandbox_mode ?? null;
  const activeSandboxResourceId = activeSandboxMode === "docker"
    ? workspaceSummary?.runtime_binding?.env_id ?? null
    : null;
  const envVarsCount = workspaceSummary?.runtime_binding?.env_vars
    ? Object.keys(workspaceSummary.runtime_binding.env_vars).length
    : 0;

  const sectionTabs: Array<{ id: RuntimePanelSection; label: string }> = [
    { id: "overview", label: "概览" },
    { id: "python", label: "Python 环境" },
    { id: "docker", label: "Docker 沙盒" },
    { id: "env", label: "工作区变量" },
  ];

  return (
    <div className="h-full overflow-hidden rounded-2xl border border-border bg-background">
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        {/* 顶部分段控制器 */}
        <div className="shrink-0 border-b border-border px-4 py-3">
          <div className="flex rounded-md bg-muted p-0.5">
            {sectionTabs.map((tab) => {
              const active = tab.id === activeSection;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveSection(tab.id)}
                  className={cn(
                    "flex-1 rounded px-3 py-1.5 text-center text-xs transition-colors",
                    active
                      ? "bg-background font-medium text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        <main className="min-h-0 flex-1 overflow-y-auto p-5">
            {activeSection === "overview" ? (
              <ExecutionResourcesOverview
                workspaceId={workspaceId}
                workspaceTitle={workspaceTitle}
                registry={registry}
                isLoading={isLoadingRegistry}
                error={registryError}
                notice={notice}
                isEnsuringUv={isEnsuringUv}
                onRefresh={() => void loadRegistry()}
                onEnsureUv={handleEnsureUvWithConfirm}
                onOpenSection={setActiveSection}
                activeSandboxMode={activeSandboxMode}
                activeSandboxResourceId={activeSandboxResourceId}
                containerResources={containerResources}
                envVarsCount={envVarsCount}
              />
            ) : null}

            {activeSection === "docker" ? (
              <div className="space-y-4">
                <NoticeBanner notice={notice} />
                <ContainerResourcesPanel
                  workspaceId={workspaceId}
                  activeSandboxResourceId={activeSandboxResourceId}
                  selectingSandboxId={selectingSandboxId}
                  onSelectSandbox={(resource) => void handleSelectDockerSandbox(resource)}
                  onResourcesLoaded={setContainerResources}
                />
              </div>
            ) : null}

            {activeSection === "env" ? (
              <section className="rounded-2xl border border-border bg-card">
                <div className="border-b border-border px-5 py-4">
                  <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                    <KeyRound className="h-4 w-4 text-tertiary" />
                    工作区变量
                  </div>
                  <p className="mt-1 text-sm leading-6 text-muted-foreground">
                    这些变量会合并全局环境变量后注入 Shell、Python kernel 和 Notebook。当前工作区同名变量优先。
                  </p>
                </div>
                <EnvVarsPanel
                  workspaceSummary={workspaceSummary ?? undefined}
                  onSaved={onWorkspaceUpdated}
                  variant="runtime-dialog"
                />
              </section>
            ) : null}

            {activeSection === "python" ? (
              <PythonRuntimeTab
                workspaceId={workspaceId}
                registry={registry}
                isRegistryLoading={isLoadingRegistry}
                isEnsuringUv={isEnsuringUv}
                bindingEnvId={bindingEnvId}
                unregisteringEnvId={unregisteringEnvId}
                installingEnvId={installingEnvId}
                onRefreshRegistry={loadRegistry}
                onEnsureUv={handleEnsureUvWithConfirm}
                onRegisterPython={handleRegisterPython}
                onBindDefault={handleBindDefault}
                onUnregister={handleUnregisterEnv}
                onInstallPackages={handleInstallPackages}
              />
            ) : null}


        </main>
      </div>

      <AlertDialog open={showUvConfirmDialog} onOpenChange={setShowUvConfirmDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>安装 uv 包管理器</AlertDialogTitle>
            <AlertDialogDescription>
              需要安装 Python 包管理器 uv（Astral 开发）才能创建 Python 运行环境。安装后 uv 会写入 ~/.cargo/bin/ 目录。是否继续？
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isEnsuringUv}>取消</AlertDialogCancel>
            <AlertDialogAction
              disabled={isEnsuringUv}
              onClick={() => {
                setShowUvConfirmDialog(false);
                void handleEnsureUv();
              }}
            >
              {isEnsuringUv ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
              安装
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
