import { useState, useCallback, useEffect } from "react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Loader2,
  Package,
  Plus,
  RefreshCw,
  SquareTerminal,
  TestTube,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  canBindKernelEnvToWorkspace,
  isAbsoluteExecutablePath,
  listBindableKernelEnvs,
  listKernelEnvs,
  registerKernelEnv,
  removeKernelEnv,
  type KernelEnvItem,
} from "@/lib/api/kernelEnvs";
import type { WorkspaceRuntimeEnvironment, WorkspaceRuntimeEnvironmentRegistry } from "@/types/workspace";

type TabNotice = { type: "success" | "error" | "info"; message: string } | null;

interface PythonRuntimeTabProps {
  workspaceId?: string | null;
  registry: WorkspaceRuntimeEnvironmentRegistry | null;
  isRegistryLoading: boolean;
  isEnsuringUv: boolean;
  bindingEnvId: string | null;
  unregisteringEnvId: string | null;
  installingEnvId: string | null;
  onRefreshRegistry: () => Promise<void>;
  onEnsureUv: () => Promise<void>;
  onRegisterPython: (env: KernelEnvItem) => Promise<void>;
  onBindDefault: (envId: string) => Promise<void>;
  onUnregister: (envId: string) => Promise<void>;
  onInstallPackages: (envId: string, packages: string[]) => Promise<void>;
}

const runtimeStatusLabels: Record<string, string> = {
  registered: "已登记",
  ready: "可使用",
  running: "运行中",
  stopped: "已停止",
  missing: "缺失",
  unavailable: "不可用",
  error: "异常",
};

function runtimeStatusLabel(status?: string) {
  return status ? runtimeStatusLabels[status] ?? status : "未检测";
}

function Notice({ notice }: { notice: TabNotice }) {
  if (!notice) return null;
  const className =
    notice.type === "success"
      ? "border-success/30 bg-success-container text-on-success-container"
      : notice.type === "error"
        ? "border-error/30 bg-error-container text-on-error-container"
        : "border-info/30 bg-info-container text-on-info-container";
  return (
    <div className={`rounded-lg border px-3 py-2 text-sm ${className}`}>
      {notice.message}
    </div>
  );
}

function UvEnvCard({
  env,
  workspaceId,
  bindingEnvId,
  unregisteringEnvId,
  installingEnvId,
  onBindDefault,
  onUnregister,
  onInstallPackages,
}: {
  env: WorkspaceRuntimeEnvironment;
  workspaceId?: string | null;
  bindingEnvId: string | null;
  unregisteringEnvId: string | null;
  installingEnvId: string | null;
  onBindDefault: (envId: string) => Promise<void>;
  onUnregister: (envId: string) => Promise<void>;
  onInstallPackages: (envId: string, packages: string[]) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const [packageInput, setPackageInput] = useState("");
  const [localInstalling, setLocalInstalling] = useState(false);
  const [localNotice, setLocalNotice] = useState<TabNotice>(null);

  const visiblePackages = env.packages.slice(0, 24);
  const hasMore = env.packages.length > 24;

  const handleInstall = useCallback(async () => {
    const raw = packageInput.trim();
    if (!raw) return;
    const packages = raw
      .split(/\s+/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (packages.length === 0) return;
    setLocalInstalling(true);
    setLocalNotice(null);
    try {
      await onInstallPackages(env.env_id, packages);
      setPackageInput("");
      setLocalNotice({ type: "success", message: `已安装 ${packages.join(", ")}。` });
    } catch (err) {
      const msg = err instanceof Error ? err.message : "安装失败";
      setLocalNotice({ type: "error", message: msg });
    } finally {
      setLocalInstalling(false);
    }
  }, [packageInput, env.env_id, onInstallPackages]);

  return (
    <div className="rounded-lg border border-border bg-muted/20">
      <div className="flex items-center justify-between gap-3 px-3 py-2">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {expanded ? (
            <ChevronUp className="h-4 w-4 shrink-0 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
          )}
          <div className="min-w-0 overflow-hidden">
            <div className="truncate text-sm font-medium text-foreground" title={env.display_name}>
              {env.display_name}
            </div>
            <div
              className="truncate text-xs text-muted-foreground"
              title={`Python ${env.python_version || "未锁定"} · ${env.package_count} 个包 · ${runtimeStatusLabel(env.status)}`}
            >
              Python {env.python_version || "未锁定"} · {env.package_count} 个包 · {runtimeStatusLabel(env.status)}
            </div>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-2">
          {env.active ? <Badge variant="success">Python 环境</Badge> : null}
          {!env.active ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={bindingEnvId === env.env_id}
              onClick={() => void onBindDefault(env.env_id)}
            >
              {bindingEnvId === env.env_id ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : null}
              设为 Python 环境
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={unregisteringEnvId === env.env_id}
            onClick={() => void onUnregister(env.env_id)}
          >
            {unregisteringEnvId === env.env_id ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : null}
            取消登记
          </Button>
        </div>
      </div>

      {expanded ? (
        <div className="border-t border-border px-3 py-3">
          {env.packages.length > 0 ? (
            <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 sm:grid-cols-3 md:grid-cols-4">
              {visiblePackages.map((pkg) => (
                <div key={pkg.name} className="flex items-center gap-1.5 text-xs text-foreground">
                  <Package className="h-3 w-3 shrink-0 text-muted-foreground" />
                  <span className="truncate" title={`${pkg.name} ${pkg.version}`}>
                    {pkg.name}
                  </span>
                  <span className="shrink-0 text-muted-foreground">{pkg.version}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="mb-3 text-xs text-muted-foreground">暂无已安装包。</div>
          )}
          {hasMore ? (
            <div className="mb-3 text-xs text-muted-foreground">
              还有 {env.packages.length - 24} 个包未显示。
            </div>
          ) : null}

          <div className="flex items-center gap-2">
            <Input
              type="text"
              value={packageInput}
              onChange={(e) => setPackageInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  void handleInstall();
                }
              }}
              placeholder="空格分隔多个包，如 numpy pandas==2.0"
              disabled={localInstalling || !workspaceId}
              className="h-8 text-sm"
            />
            <Button
              type="button"
              size="sm"
              disabled={localInstalling || !packageInput.trim() || !workspaceId}
              onClick={() => void handleInstall()}
            >
              {localInstalling || installingEnvId === env.env_id ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-1 h-4 w-4" />
              )}
              安装
            </Button>
          </div>

          {localNotice ? (
            <div
              className={`mt-2 rounded-lg border px-3 py-1.5 text-xs ${
                localNotice.type === "success"
                  ? "border-success/30 bg-success-container text-on-success-container"
                  : "border-error/30 bg-error-container text-on-error-container"
              }`}
            >
              {localNotice.message}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function PythonRuntimeTab({
  workspaceId,
  registry,
  isRegistryLoading,
  isEnsuringUv,
  bindingEnvId,
  unregisteringEnvId,
  installingEnvId,
  onRefreshRegistry,
  onEnsureUv,
  onRegisterPython,
  onBindDefault,
  onUnregister,
  onInstallPackages,
}: PythonRuntimeTabProps) {
  const [interpreterPath, setInterpreterPath] = useState("");
  const [interpreterName, setInterpreterName] = useState("");
  const [isRegistering, setIsRegistering] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [removingName, setRemovingName] = useState<string | null>(null);
  const [interpreters, setInterpreters] = useState<KernelEnvItem[]>([]);
  const [kernelError, setKernelError] = useState<string | null>(null);
  const [notice, setNotice] = useState<TabNotice>(null);
  const [isLoading, setIsLoading] = useState(true);

  const workspaceUvEnvs = (registry?.envs ?? []).filter((env) => env.kind === "uv");
  const workspaceRegisteredPythonEnvs = (registry?.envs ?? []).filter(
    (env) => env.kind === "registered_python",
  );
  const workspaceEnvSourceNames = new Set(
    workspaceRegisteredPythonEnvs
      .map((env) => String(env.metadata?.source_kernel_name ?? ""))
      .filter(Boolean),
  );
  const workspaceBindableInterpreters = listBindableKernelEnvs(interpreters);
  const activeUvEnv =
    (registry?.envs ?? []).find((env) => env.active)
    ?? (registry?.envs ?? []).find((env) => env.env_id === registry?.active_env_id)
    ?? null;
  const workspaceEnvironmentCount =
    workspaceUvEnvs.length + workspaceRegisteredPythonEnvs.length;

  const loadKernels = useCallback(async () => {
    try {
      setKernelError(null);
      const data = await listKernelEnvs();
      setInterpreters(data.kernels ?? []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "加载失败";
      setKernelError(msg);
    }
  }, []);

  useEffect(() => {
    setIsLoading(true);
    loadKernels().finally(() => setIsLoading(false));
    const interval = window.setInterval(loadKernels, 30000);
    return () => window.clearInterval(interval);
  }, [loadKernels]);

  const handleRegister = useCallback(async () => {
    const path = interpreterPath.trim();
    const name = interpreterName.trim() || path.split("/").pop()?.split("\\").pop() || "custom";
    if (!path) {
      setNotice({ type: "error", message: "请输入 Python 可执行文件路径。" });
      return;
    }
    if (!isAbsoluteExecutablePath(path)) {
      setNotice({ type: "error", message: "Python 可执行文件路径必须是完整绝对路径。" });
      return;
    }
    setIsRegistering(true);
    setNotice(null);
    try {
      const result = await registerKernelEnv(name, path);
      setNotice({ type: "success", message: `已注册 ${result.name}。` });
      setInterpreterPath("");
      setInterpreterName("");
      await loadKernels();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "注册失败";
      setNotice({ type: "error", message: msg });
    } finally {
      setIsRegistering(false);
    }
  }, [interpreterPath, interpreterName, loadKernels]);

  const handleTest = useCallback(async () => {
    const path = interpreterPath.trim();
    if (!path) {
      setNotice({ type: "error", message: "请先输入 Python 可执行文件路径。" });
      return;
    }
    if (!isAbsoluteExecutablePath(path)) {
      setNotice({ type: "error", message: "Python 可执行文件路径必须是完整绝对路径。" });
      return;
    }
    const testName = `__test_${Date.now()}`;
    setIsTesting(true);
    setNotice(null);
    try {
      await registerKernelEnv(testName, path);
      try {
        await removeKernelEnv(testName);
      } catch {
        // 测试 kernel 清理失败不影响解释器可用性结论。
      }
      setNotice({ type: "success", message: "检测通过，该解释器可用。" });
      await loadKernels();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "检测失败";
      setNotice({ type: "error", message: msg });
    } finally {
      setIsTesting(false);
    }
  }, [interpreterPath, loadKernels]);

  const handleRemove = useCallback(
    async (name: string) => {
      setRemovingName(name);
      setNotice(null);
      try {
        await removeKernelEnv(name);
        setNotice({ type: "success", message: "解释器已删除。" });
        await loadKernels();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "删除失败";
        setNotice({ type: "error", message: msg });
      } finally {
        setRemovingName(null);
      }
    },
    [loadKernels],
  );

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <SquareTerminal className="h-4 w-4 text-tertiary" />
              工作区 Python 环境
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              这里的 UV 环境属于当前工作区，用来隔离任务依赖，可设为当前 Python 环境。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void onRefreshRegistry()}
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!workspaceId || isEnsuringUv || registry?.uv_available === false}
              onClick={() => void onEnsureUv()}
            >
              {isEnsuringUv ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              启用 Python
            </Button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-[260px_minmax(0,1fr)]">
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="text-xs font-semibold text-muted-foreground">
              当前 Python 环境
            </div>
            <div className="mt-2 text-sm font-semibold text-foreground">
              {activeUvEnv?.display_name || "未设置"}
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              {activeUvEnv
                ? `Python ${activeUvEnv.python_version || "未锁定"}，${runtimeStatusLabel(activeUvEnv.status)}`
                : "启用后可以绑定为当前 Python 环境。"}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={registry?.uv_available ? "success" : "error"}>
                {registry?.uv_available ? "UV 可使用" : "UV 不可用"}
              </Badge>
              {isRegistryLoading ? <Badge variant="secondary">检查中</Badge> : null}
              <Badge variant="outline">{workspaceEnvironmentCount} 个工作区环境</Badge>
              <Badge variant="outline">{workspaceRegisteredPythonEnvs.length} 个已登记解释器</Badge>
            </div>
            <div className="mt-2 text-xs leading-5 text-muted-foreground">
              UV 环境跟随工作区；已登记解释器会引用本机已有 Python 路径。
            </div>
          </div>
        </div>

        <div className="mt-4 space-y-2">
          {workspaceUvEnvs.length > 0 ? (
            workspaceUvEnvs.map((env) => (
              <UvEnvCard
                key={env.env_id}
                env={env}
                workspaceId={workspaceId}
                bindingEnvId={bindingEnvId}
                unregisteringEnvId={unregisteringEnvId}
                installingEnvId={installingEnvId}
                onBindDefault={onBindDefault}
                onUnregister={onUnregister}
                onInstallPackages={onInstallPackages}
              />
            ))
          ) : null}
          {workspaceRegisteredPythonEnvs.length > 0 ? (
            workspaceRegisteredPythonEnvs.map((env) => (
              <div
                key={env.env_id}
                className="rounded-lg border border-border bg-muted/20 px-3 py-2"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0 overflow-hidden">
                    <div className="truncate text-sm font-medium text-foreground" title={env.display_name}>
                      {env.display_name}
                    </div>
                    <div
                      className="truncate text-xs text-muted-foreground"
                      title={`Python ${env.python_version || "未探测"} · ${runtimeStatusLabel(env.status)}`}
                    >
                      Python {env.python_version || "未探测"} · {runtimeStatusLabel(env.status)}
                    </div>
                    <div
                      className="truncate font-mono text-[11px] text-muted-foreground"
                      title={env.python_executable || env.material_path || env.env_id}
                    >
                      {env.python_executable || env.material_path || env.env_id}
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    {env.active ? <Badge variant="success">Python 环境</Badge> : null}
                    {!env.active ? (
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={bindingEnvId === env.env_id}
                        onClick={() => void onBindDefault(env.env_id)}
                      >
                        {bindingEnvId === env.env_id ? (
                          <Loader2 className="h-4 w-4 animate-spin" />
                        ) : null}
                        设为 Python 环境
                      </Button>
                    ) : null}
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={unregisteringEnvId === env.env_id}
                      onClick={() => void onUnregister(env.env_id)}
                    >
                      {unregisteringEnvId === env.env_id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : null}
                      取消登记
                    </Button>
                  </div>
                </div>
              </div>
            ))
          ) : null}
          {workspaceEnvironmentCount === 0 ? (
            <div className="text-sm text-muted-foreground">
              暂无工作区 Python 环境。
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <SquareTerminal className="h-4 w-4 text-tertiary" />
              Notebook 解释器目录
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              这里登记的是本机可用解释器，供 Notebook kernel 选择；可解析为绝对路径的解释器也可以设为当前工作区 Python。
            </p>
          </div>
          <Button type="button" variant="outline" size="sm" onClick={() => void loadKernels()}>
            <RefreshCw className="h-4 w-4" />
            刷新
          </Button>
        </div>

        <div className="mt-4">
          <Notice notice={notice} />
        </div>

        {kernelError ? (
          <div className="mt-3 rounded-lg border border-error/30 bg-error-container px-3 py-2 text-sm text-on-error-container">
            加载失败：{kernelError}
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {isLoading && !kernelError ? (
            <div className="flex items-center py-2 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              加载中...
            </div>
          ) : null}
          {!isLoading && interpreters.length === 0 && !kernelError ? (
            <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
              暂无注册的解释器
            </div>
          ) : null}
          {interpreters.map((interp) => (
            <div
              key={interp.name}
              className={`flex items-center justify-between gap-3 rounded-xl border p-3 ${
                interp.forbidden
                  ? "border-error/30 bg-error-container/40"
                  : "border-border bg-background"
              }`}
            >
              <div className="flex min-w-0 flex-1 items-center gap-3 overflow-hidden">
                {interp.forbidden ? (
                  <Ban className="h-4 w-4 shrink-0 text-error" />
                ) : (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-success" />
                )}
                <div className="min-w-0 overflow-hidden">
                  <div className="truncate text-sm font-medium text-foreground" title={interp.display_name}>
                    {interp.display_name}
                  </div>
                  <div
                    className="truncate font-mono text-xs text-muted-foreground"
                    title={interp.executable ?? undefined}
                  >
                    {interp.executable ?? "未返回路径"}
                  </div>
                  {interp.forbidden && interp.forbidden_reason ? (
                    <div className="mt-1 flex items-start gap-1 text-xs text-error">
                      <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0" />
                      <span>{interp.forbidden_reason}</span>
                    </div>
                  ) : null}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {interp.forbidden ? (
                  <Badge variant="outline" className="border-error/30 text-error">
                    禁止使用
                  </Badge>
                ) : !isAbsoluteExecutablePath(interp.executable) ? (
                  <Badge variant="secondary">仅 Notebook</Badge>
                ) : interp.executable_exists === false ? (
                  <Badge variant="secondary">路径失效</Badge>
                ) : !canBindKernelEnvToWorkspace(interp) ? (
                  <Badge variant="secondary">仅 Notebook</Badge>
                ) : workspaceEnvSourceNames.has(interp.name) ? (
                  <Badge variant="secondary">已加入工作区</Badge>
                ) : (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => void onRegisterPython(interp)}
                  >
                    设为工作区 Python
                  </Button>
                )}
                {!interp.forbidden && !interp.protected ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon-sm"
                    disabled={removingName === interp.name}
                    onClick={() => void handleRemove(interp.name)}
                    aria-label="删除解释器"
                  >
                    {removingName === interp.name ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4 text-muted-foreground" />
                    )}
                  </Button>
                ) : interp.protected && !interp.forbidden ? (
                  <Badge variant="secondary">受保护</Badge>
                ) : null}
              </div>
            </div>
          ))}
          {!isLoading && interpreters.length > 0 && workspaceBindableInterpreters.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border px-3 py-3 text-sm text-muted-foreground">
              当前解释器目录里没有可直接绑定到工作区的绝对路径。可以在下方登记一个 Python 可执行文件完整路径。
            </div>
          ) : null}
        </div>

        <div className="mt-4 grid gap-2 md:grid-cols-[160px_minmax(0,1fr)_auto_auto]">
          <Input
            type="text"
            value={interpreterName}
            onChange={(e) => setInterpreterName(e.target.value)}
            placeholder="名称"
          />
          <Input
            type="text"
            value={interpreterPath}
            onChange={(e) => setInterpreterPath(e.target.value)}
            placeholder="Python 可执行文件路径，例如 /usr/bin/python3"
          />
          <Button
            type="button"
            variant="secondary"
            disabled={isRegistering}
            onClick={() => void handleRegister()}
          >
            {isRegistering ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
            注册
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={isTesting}
            onClick={() => void handleTest()}
          >
            {isTesting ? <Loader2 className="h-4 w-4 animate-spin" /> : <TestTube className="h-4 w-4" />}
            测试
          </Button>
        </div>
      </section>
    </div>
  );
}
