import { useCallback, useEffect, useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  CloudDownload,
  Hexagon,
  Loader2,
  Package,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getWorkspaceNodeEnvironments,
  installNodeVersion,
  useNodeVersion as switchNodeVersion,
  setDefaultNodeVersion,
  uninstallNodeVersion,
  listRemoteNodeVersions,
} from "@/lib/api/workspaces";
import type { NodeRuntimeEnv, NodeRuntimeEnvRegistry } from "@/types/workspace";

type TabNotice = { type: "success" | "error" | "info"; message: string } | null;

interface NodeRuntimeTabProps {
  workspaceId?: string | null;
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

function statusLabel(status?: string) {
  return status ? statusLabels[status] ?? status : "未检测";
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

function EnvCard({
  env,
  workspaceId,
  busyEnvId,
  onUse,
  onDefault,
  onUninstall,
}: {
  env: NodeRuntimeEnv;
  workspaceId?: string | null;
  busyEnvId?: string | null;
  onUse: (env: NodeRuntimeEnv) => Promise<void>;
  onDefault: (env: NodeRuntimeEnv) => Promise<void>;
  onUninstall: (env: NodeRuntimeEnv) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(false);
  const isBusy = env.env_id === busyEnvId;

  const visiblePackages = env.packages.slice(0, 24);
  const hasMore = env.packages.length > 24;

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
            <div
              className="truncate text-sm font-medium text-foreground"
              title={env.display_name}
            >
              {env.display_name}
            </div>
            <div
              className="truncate text-xs text-muted-foreground"
              title={`Node ${env.node_version || "未锁定"} · npm ${env.npm_version || "未探测"} · ${statusLabel(env.status)}`}
            >
              Node {env.node_version || "未锁定"} · npm {env.npm_version || "未探测"} ·{" "}
              {statusLabel(env.status)}
            </div>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-2">
          {env.active ? <Badge variant="success">Node 环境</Badge> : null}
          {!env.active ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!workspaceId || isBusy}
              onClick={() => void onUse(env)}
            >
              {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              设为 Node 环境
            </Button>
          ) : null}
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!workspaceId || isBusy || !env.node_version}
            onClick={() => void onDefault(env)}
          >
            设为全局默认
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={!workspaceId || isBusy || !env.node_version}
            onClick={() => void onUninstall(env)}
          >
            {isBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4 text-muted-foreground" />}
            卸载
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
        </div>
      ) : null}
    </div>
  );
}

export function NodeRuntimeTab({ workspaceId }: NodeRuntimeTabProps) {
  const [registry, setRegistry] = useState<NodeRuntimeEnvRegistry | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<TabNotice>(null);
  const [versionInput, setVersionInput] = useState("");
  const [isInstalling, setIsInstalling] = useState(false);
  const [busyEnvId, setBusyEnvId] = useState<string | null>(null);
  const [remoteVersions, setRemoteVersions] = useState<string[]>([]);
  const [isLoadingRemote, setIsLoadingRemote] = useState(false);

  const activeEnv =
    registry?.envs.find((env) => env.active) ??
    registry?.envs.find((env) => env.env_id === registry?.active_env_id) ??
    null;

  const loadRegistry = useCallback(async () => {
    if (!workspaceId) {
      setRegistry(null);
      setError(null);
      return;
    }
    setIsLoading(true);
    try {
      setError(null);
      const data = await getWorkspaceNodeEnvironments(workspaceId);
      setRegistry(data);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "加载 Node.js 环境失败";
      setError(msg);
    } finally {
      setIsLoading(false);
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

  const handleInstall = useCallback(async () => {
    if (!workspaceId) return;
    const version = versionInput.trim();
    if (!version) {
      setNotice({ type: "error", message: "请输入 Node.js 版本号，例如 20 或 20.11.0。" });
      return;
    }
    setIsInstalling(true);
    setNotice(null);
    try {
      await installNodeVersion(workspaceId, version);
      setNotice({ type: "success", message: `Node.js ${version} 安装请求已提交。` });
      setVersionInput("");
      await loadRegistry();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "安装失败";
      setNotice({ type: "error", message: msg });
    } finally {
      setIsInstalling(false);
    }
  }, [loadRegistry, versionInput, workspaceId]);

  const handleUse = useCallback(
    async (env: NodeRuntimeEnv) => {
      if (!workspaceId || !env.node_version) return;
      setBusyEnvId(env.env_id);
      setNotice(null);
      try {
        await switchNodeVersion(workspaceId, {
          envId: env.env_id,
          nodeVersion: env.node_version,
        });
        setNotice({ type: "success", message: `已切换到 Node.js ${env.node_version}。` });
        await loadRegistry();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "切换失败";
        setNotice({ type: "error", message: msg });
      } finally {
        setBusyEnvId(null);
      }
    },
    [loadRegistry, workspaceId],
  );

  const handleDefault = useCallback(
    async (env: NodeRuntimeEnv) => {
      if (!workspaceId || !env.node_version) return;
      setBusyEnvId(env.env_id);
      setNotice(null);
      try {
        await setDefaultNodeVersion(workspaceId, env.node_version);
        setNotice({ type: "success", message: `已将 Node.js ${env.node_version} 设为 fnm 全局默认。` });
        await loadRegistry();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "设置默认版本失败";
        setNotice({ type: "error", message: msg });
      } finally {
        setBusyEnvId(null);
      }
    },
    [loadRegistry, workspaceId],
  );

  const handleUninstall = useCallback(
    async (env: NodeRuntimeEnv) => {
      if (!workspaceId || !env.node_version) return;
      setBusyEnvId(env.env_id);
      setNotice(null);
      try {
        await uninstallNodeVersion(workspaceId, env.node_version);
        setNotice({ type: "success", message: `Node.js ${env.node_version} 已卸载。` });
        await loadRegistry();
      } catch (err) {
        const msg = err instanceof Error ? err.message : "卸载失败";
        setNotice({ type: "error", message: msg });
      } finally {
        setBusyEnvId(null);
      }
    },
    [loadRegistry, workspaceId],
  );

  const handleLoadRemote = useCallback(async () => {
    if (!workspaceId) return;
    setIsLoadingRemote(true);
    setNotice(null);
    try {
      const result = await listRemoteNodeVersions(workspaceId);
      const versions = Array.isArray(result.result.versions)
        ? (result.result.versions as string[])
        : [];
      setRemoteVersions(versions.slice(0, 30));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "加载远程版本失败";
      setNotice({ type: "error", message: msg });
    } finally {
      setIsLoadingRemote(false);
    }
  }, [workspaceId]);

  const fnmBadge = registry?.fnm_available ? (
    <Badge variant="success">fnm 可使用</Badge>
  ) : (
    <Badge variant="error">fnm 不可用</Badge>
  );

  return (
    <div className="space-y-6">
      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Hexagon className="h-4 w-4 text-tertiary" />
              工作区 Node.js 环境
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              通过 fnm 管理当前工作区的 Node.js 版本。安装、切换和卸载都在工作区 .env 目录下完成。
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => void loadRegistry()}
            >
              <RefreshCw className="h-4 w-4" />
              刷新
            </Button>
          </div>
        </div>

        <div className="mt-4 grid gap-3 md:grid-cols-[260px_minmax(0,1fr)]">
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="text-xs font-semibold text-muted-foreground">当前 Node 环境</div>
            <div className="mt-2 text-sm font-semibold text-foreground">
              {activeEnv?.display_name || "未设置"}
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              {activeEnv
                ? `Node ${activeEnv.node_version || "未锁定"}，${statusLabel(activeEnv.status)}`
                : "安装或激活一个 Node.js 版本后可用。"}
            </div>
          </div>
          <div className="rounded-xl border border-border bg-background p-4">
            <div className="flex flex-wrap items-center gap-2">
              {fnmBadge}
              {isLoading ? <Badge variant="secondary">检查中</Badge> : null}
              <Badge variant="outline">{registry?.envs.length ?? 0} 个已安装版本</Badge>
              <Badge variant="outline">
                {activeEnv?.npm_version ? `npm ${activeEnv.npm_version}` : "npm 未探测"}
              </Badge>
            </div>
            <div className="mt-2 text-xs leading-5 text-muted-foreground">
              {registry?.fnm_available
                ? "fnm 已就绪，可直接安装或切换 Node.js 版本。"
                : "未检测到 fnm。桌面版会自动携带，Web 版需要本机已安装 fnm 并位于 PATH 中。"}
            </div>
          </div>
        </div>

        {error ? (
          <div className="mt-4 rounded-lg border border-error/30 bg-error-container px-3 py-2 text-sm text-on-error-container">
            {error}
          </div>
        ) : null}

        <div className="mt-4 space-y-2">
          {registry?.envs.map((env) => (
            <EnvCard
              key={env.env_id}
              env={env}
              workspaceId={workspaceId}
              busyEnvId={busyEnvId}
              onUse={handleUse}
              onDefault={handleDefault}
              onUninstall={handleUninstall}
            />
          ))}
          {!isLoading && (registry?.envs.length ?? 0) === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-background px-3 py-6 text-center text-sm text-muted-foreground">
              暂无已安装的 Node.js 版本。
            </div>
          ) : null}
          {isLoading && (registry?.envs.length ?? 0) === 0 ? (
            <div className="flex items-center py-2 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              加载中...
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-2xl border border-border bg-card p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <CloudDownload className="h-4 w-4 text-info" />
              安装新版本
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              输入版本号（如 20、20.11、20.11.0、lts/iron），fnm 会下载并安装到本地。
            </p>
          </div>
        </div>

        <div className="mt-4">
          <Notice notice={notice} />
        </div>

        <div className="mt-4 flex items-center gap-2">
          <Input
            type="text"
            value={versionInput}
            onChange={(e) => setVersionInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void handleInstall();
              }
            }}
            placeholder="例如 20 或 lts/iron"
            disabled={isInstalling || !workspaceId || !registry?.fnm_available}
            className="h-8 text-sm"
          />
          <Button
            type="button"
            size="sm"
            disabled={isInstalling || !versionInput.trim() || !workspaceId || !registry?.fnm_available}
            onClick={() => void handleInstall()}
          >
            {isInstalling ? (
              <Loader2 className="mr-1 h-4 w-4 animate-spin" />
            ) : (
              <Plus className="mr-1 h-4 w-4" />
            )}
            安装
          </Button>
        </div>

        <div className="mt-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isLoadingRemote || !workspaceId || !registry?.fnm_available}
            onClick={() => void handleLoadRemote()}
          >
            {isLoadingRemote ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CloudDownload className="mr-1 h-4 w-4" />}
            查看可用版本
          </Button>
          {remoteVersions.length > 0 ? (
            <div className="mt-3 flex max-h-40 flex-wrap gap-2 overflow-y-auto rounded-lg border border-border bg-muted/20 p-3">
              {remoteVersions.map((version) => (
                <Badge
                  key={version}
                  variant="outline"
                  className="cursor-pointer hover:bg-muted"
                  onClick={() => setVersionInput(version)}
                >
                  {version}
                </Badge>
              ))}
            </div>
          ) : null}
        </div>
      </section>
    </div>
  );
}
