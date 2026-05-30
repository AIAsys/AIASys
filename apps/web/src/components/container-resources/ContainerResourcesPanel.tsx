import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Container,
  Loader2,
  PackagePlus,
  Play,
  Plus,
  RefreshCw,
  Square,
  Terminal,
  Trash2,

} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import type {
  RegisterWorkspaceContainerResourcePayload,
  WorkspaceContainerResource,
} from "@/types/workspace";

import {
  getWorkspaceContainerResources,
  registerWorkspaceContainerResource,
  startWorkspaceContainerResource,
  stopWorkspaceContainerResource,
  deleteWorkspaceContainerResource,
  getWorkspaceContainerResourceLogs,
} from "@/lib/api/workspaces";

type ContainerStatus = "running" | "stopped" | "error" | string;
type RegisterMode = "existing" | "create";

interface RegisterFormState {
  mode: RegisterMode;
  containerIdOrName: string;
  image: string;
  name: string;
  containerId: string;
  workspaceMountPath: string;
  command: string;
  autoStart: boolean;
}

const DEFAULT_REGISTER_FORM: RegisterFormState = {
  mode: "existing",
  containerIdOrName: "",
  image: "",
  name: "",
  containerId: "",
  workspaceMountPath: "/workspace",
  command: "",
  autoStart: false,
};

interface ContainerResourcesPanelProps {
  workspaceId?: string | null;
  activeSandboxResourceId?: string | null;
  selectingSandboxId?: string | null;
  onSelectSandbox?: (resource: WorkspaceContainerResource) => void;
  onResourcesLoaded?: (resources: WorkspaceContainerResource[]) => void;
}

function containerStatusVariant(status?: ContainerStatus) {
  if (status === "running") return "success";
  if (status === "stopped") return "info";
  if (status === "error") return "error";
  return "secondary";
}

function containerStatusLabel(status?: ContainerStatus) {
  if (status === "running") return "运行中";
  if (status === "stopped") return "已停止";
  if (status === "error") return "异常";
  return status || "未知";
}

function formatDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

function optionalText(value: string) {
  const text = value.trim();
  return text || undefined;
}

function buildRegisterPayload(
  form: RegisterFormState,
): RegisterWorkspaceContainerResourcePayload | string {
  const mountPath = optionalText(form.workspaceMountPath) ?? "/workspace";
  if (form.mode === "existing") {
    const containerIdOrName = optionalText(form.containerIdOrName);
    if (!containerIdOrName) {
      return "请输入容器 ID 或名称。";
    }
    return {
      containerId: optionalText(form.containerId),
      name: optionalText(form.name),
      image: optionalText(form.image),
      containerIdOrName,
      workspaceMountPath: mountPath,
      createContainer: false,
      autoStart: false,
    };
  }

  const image = optionalText(form.image);
  if (!image) {
    return "请输入镜像名称。";
  }
  return {
    containerId: optionalText(form.containerId),
    name: optionalText(form.name),
    image,
    workspaceMountPath: mountPath,
    createContainer: true,
    autoStart: form.autoStart,
    command: optionalText(form.command),
  };
}

function ContainerResourceCard({
  resource,
  isActing,
  onStart,
  onStop,
  onViewLogs,
  onDelete,
  isActiveSandbox,
  isSelectingSandbox,
  onSelectSandbox,
}: {
  resource: WorkspaceContainerResource;
  isActing: boolean;
  onStart: (id: string) => void;
  onStop: (id: string) => void;
  onViewLogs: (id: string) => void;
  onDelete: (id: string) => void;
  isActiveSandbox: boolean;
  isSelectingSandbox: boolean;
  onSelectSandbox?: (resource: WorkspaceContainerResource) => void;
}) {
  const updatedAt = formatDate(resource.updated_at);

  return (
    <div className="rounded-xl border border-border bg-background p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-muted">
            <Container className="h-4 w-4 text-info" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <div className="truncate text-sm font-semibold text-foreground">
                {resource.name}
              </div>
              <Badge variant="outline">Docker</Badge>
              <Badge variant={containerStatusVariant(resource.status)}>
                {containerStatusLabel(resource.status)}
              </Badge>
              {isActiveSandbox ? <Badge variant="success">当前 Docker 沙盒</Badge> : null}
            </div>
            <div className="mt-1 truncate font-mono text-xs text-muted-foreground">
              {resource.container_id}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              任务可使用的 Docker 沙盒材料
            </div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {onSelectSandbox ? (
            <Button
              type="button"
              variant={isActiveSandbox ? "secondary" : "outline"}
              size="sm"
              disabled={isSelectingSandbox || isActiveSandbox}
              onClick={() => onSelectSandbox(resource)}
            >
              {isSelectingSandbox ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {isActiveSandbox ? "已设为沙盒" : "设为 Docker 沙盒"}
            </Button>
          ) : null}
          {resource.status === "running" ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isActing}
              onClick={() => onStop(resource.container_id)}
            >
              {isActing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
              停止
            </Button>
          ) : (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={isActing}
              onClick={() => onStart(resource.container_id)}
            >
              {isActing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              启动
            </Button>
          )}
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={() => onViewLogs(resource.container_id)}
            aria-label="查看日志"
          >
            <Terminal className="h-4 w-4 text-muted-foreground" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            disabled={isActing}
            onClick={() => onDelete(resource.container_id)}
            aria-label="删除登记"
          >
            {isActing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Trash2 className="h-4 w-4 text-muted-foreground" />
            )}
          </Button>
        </div>
      </div>

      <div className="mt-3 grid gap-2 text-xs text-muted-foreground md:grid-cols-2">
        <div className="truncate">镜像：{resource.image || "未指定"}</div>
        <div>容器：{resource.container_id || "未绑定"}</div>
        <div>挂载：{resource.workspace_mount_path || "/workspace"}</div>
        <div>状态：{containerStatusLabel(resource.status)}</div>
        {updatedAt ? <div className="md:col-span-2">更新时间：{updatedAt}</div> : null}
      </div>
    </div>
  );
}

function DockerSandboxRegisterForm({
  form,
  disabled,
  onChange,
  onCancel,
  onSubmit,
}: {
  form: RegisterFormState;
  disabled: boolean;
  onChange: (patch: Partial<RegisterFormState>) => void;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  const modeOptionClass = (mode: RegisterMode) =>
    cn(
      "flex h-8 items-center justify-center rounded-md border px-3 text-sm font-medium transition-colors",
      form.mode === mode
        ? "border-primary bg-primary text-primary-foreground"
        : "border-border bg-background text-muted-foreground hover:bg-muted",
    );

  return (
    <div
      className="mt-4 rounded-xl border border-border bg-background p-4"
      data-testid="docker-sandbox-register-form"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-foreground">
            登记 Docker 沙盒
          </div>
          <div className="mt-1 text-sm text-muted-foreground">
            登记已有容器，或从镜像创建一个只属于当前工作区的容器。
          </div>
        </div>
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-muted p-1">
          <button
            type="button"
            className={modeOptionClass("existing")}
            disabled={disabled}
            onClick={() => onChange({ mode: "existing" })}
          >
            登记已有容器
          </button>
          <button
            type="button"
            className={modeOptionClass("create")}
            disabled={disabled}
            onClick={() => onChange({ mode: "create" })}
          >
            按镜像创建容器
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-2">
        {form.mode === "existing" ? (
          <div className="space-y-1.5 md:col-span-2">
            <Label htmlFor="docker-container-id-or-name">容器 ID 或名称</Label>
            <Input
              id="docker-container-id-or-name"
              value={form.containerIdOrName}
              disabled={disabled}
              onChange={(event) => onChange({ containerIdOrName: event.target.value })}
              placeholder="例如 aiasys-task-env 或容器 ID"
            />
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="docker-image">镜像</Label>
            <Input
              id="docker-image"
              value={form.image}
              disabled={disabled}
              onChange={(event) => onChange({ image: event.target.value })}
              placeholder="例如 python:3.11-slim"
            />
          </div>
        )}

        {form.mode === "existing" ? (
          <div className="space-y-1.5">
            <Label htmlFor="docker-existing-image">镜像（可选）</Label>
            <Input
              id="docker-existing-image"
              value={form.image}
              disabled={disabled}
              onChange={(event) => onChange({ image: event.target.value })}
              placeholder="不填时从容器读取"
            />
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="docker-command">启动命令（可选）</Label>
            <Input
              id="docker-command"
              value={form.command}
              disabled={disabled}
              onChange={(event) => onChange({ command: event.target.value })}
              placeholder="例如 sleep infinity"
            />
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="docker-display-name">显示名称（可选）</Label>
          <Input
            id="docker-display-name"
            value={form.name}
            disabled={disabled}
            onChange={(event) => onChange({ name: event.target.value })}
            placeholder="显示在 Docker 沙盒列表里"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="docker-sandbox-id">沙盒 ID（可选）</Label>
          <Input
            id="docker-sandbox-id"
            value={form.containerId}
            disabled={disabled}
            onChange={(event) => onChange({ containerId: event.target.value })}
            placeholder="不填时自动生成"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="docker-workspace-mount">工作区挂载路径</Label>
          <Input
            id="docker-workspace-mount"
            value={form.workspaceMountPath}
            disabled={disabled}
            onChange={(event) => onChange({ workspaceMountPath: event.target.value })}
            placeholder="/workspace"
          />
        </div>
        {form.mode === "create" ? (
          <div className="flex items-end pb-2">
            <Checkbox
              checked={form.autoStart}
              disabled={disabled}
              label="创建后启动"
              onCheckedChange={(checked) => onChange({ autoStart: checked === true })}
            />
          </div>
        ) : null}
      </div>

      <div className="mt-4 flex justify-end gap-2">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          disabled={disabled}
          onClick={onCancel}
        >
          取消
        </Button>
        <Button
          type="button"
          variant="default"
          size="sm"
          disabled={disabled}
          onClick={onSubmit}
        >
          {disabled ? <Loader2 className="h-4 w-4 animate-spin" /> : <PackagePlus className="h-4 w-4" />}
          {form.mode === "create" ? "创建并登记" : "登记沙盒"}
        </Button>
      </div>
    </div>
  );
}

export function ContainerResourcesPanel({
  workspaceId,
  activeSandboxResourceId,
  selectingSandboxId,
  onSelectSandbox,
  onResourcesLoaded,
}: ContainerResourcesPanelProps) {
  const [resources, setResources] = useState<WorkspaceContainerResource[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [actingId, setActingId] = useState<string | null>(null);
  const [isRegisterOpen, setIsRegisterOpen] = useState(false);
  const [registerForm, setRegisterForm] = useState<RegisterFormState>(
    DEFAULT_REGISTER_FORM,
  );
  const [isRegistering, setIsRegistering] = useState(false);

  const loadResources = useCallback(async () => {
    if (!workspaceId) {
      setResources([]);
      setError(null);
      return;
    }
    setIsLoading(true);
    try {
      setError(null);
      const data = await getWorkspaceContainerResources(workspaceId);
      setResources(data.containers);
      onResourcesLoaded?.(data.containers);
    } catch (err) {
      const message = err instanceof Error ? err.message : "加载 Docker 沙盒失败";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  }, [onResourcesLoaded, workspaceId]);

  useEffect(() => {
    if (!open) return;
    void loadResources();
  }, [loadResources]);

  const handleStart = useCallback(
    async (id: string) => {
      if (!workspaceId) return;
      setActingId(id);
      try {
        await startWorkspaceContainerResource(workspaceId, id);
        await loadResources();
      } catch (err) {
        const message = err instanceof Error ? err.message : "启动失败";
        setError(message);
      } finally {
        setActingId(null);
      }
    },
    [loadResources, workspaceId],
  );

  const handleStop = useCallback(
    async (id: string) => {
      if (!workspaceId) return;
      setActingId(id);
      try {
        await stopWorkspaceContainerResource(workspaceId, id);
        await loadResources();
      } catch (err) {
        const message = err instanceof Error ? err.message : "停止失败";
        setError(message);
      } finally {
        setActingId(null);
      }
    },
    [loadResources, workspaceId],
  );

  const handleDelete = useCallback(
    async (id: string) => {
      if (!workspaceId) return;
      setActingId(id);
      try {
        await deleteWorkspaceContainerResource(workspaceId, id);
        await loadResources();
      } catch (err) {
        const message = err instanceof Error ? err.message : "删除登记失败";
        setError(message);
      } finally {
        setActingId(null);
      }
    },
    [loadResources, workspaceId],
  );

  const handleViewLogs = useCallback(
    async (id: string) => {
      try {
        const data = await getWorkspaceContainerResourceLogs(workspaceId!, id);
        alert(data.logs);
      } catch (err) {
        const message = err instanceof Error ? err.message : "获取日志失败";
        setError(message);
      }
    },
    [workspaceId],
  );

  const handleRegister = useCallback(async () => {
    if (!workspaceId || isRegistering) return;
    const payload = buildRegisterPayload(registerForm);
    if (typeof payload === "string") {
      setError(payload);
      return;
    }
    setIsRegistering(true);
    try {
      setError(null);
      await registerWorkspaceContainerResource(workspaceId, payload);
      setRegisterForm(DEFAULT_REGISTER_FORM);
      setIsRegisterOpen(false);
      await loadResources();
    } catch (err) {
      const message = err instanceof Error ? err.message : "登记 Docker 沙盒失败";
      setError(message);
    } finally {
      setIsRegistering(false);
    }
  }, [isRegistering, loadResources, registerForm, workspaceId]);

  const handleCancelRegister = useCallback(() => {
    if (isRegistering) return;
    setRegisterForm(DEFAULT_REGISTER_FORM);
    setIsRegisterOpen(false);
  }, [isRegistering]);

  const runningCount = useMemo(
    () => resources.filter((r) => r.status === "running").length,
    [resources],
  );

  const content = (
    <div
      className="space-y-5"
      data-testid="container-resources-panel"
    >
      <main className="min-h-0">
        <div className="space-y-5">
          <section className="rounded-2xl border border-border bg-card p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                  <Container className="h-4 w-4 text-info" />
                  Docker 沙盒材料
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  这些材料可作为当前工作区 Docker 沙盒。Shell 和 Monitor 会在选中的容器里执行脚本。
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant={isRegisterOpen ? "secondary" : "default"}
                  size="sm"
                  disabled={!workspaceId}
                  onClick={() => setIsRegisterOpen((value) => !value)}
                >
                  <Plus className="h-4 w-4" />
                  登记 Docker 沙盒
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => void loadResources()}
                >
                  <RefreshCw className="h-4 w-4" />
                  刷新
                </Button>
              </div>
            </div>

            {isRegisterOpen ? (
              <DockerSandboxRegisterForm
                form={registerForm}
                disabled={isRegistering}
                onChange={(patch) =>
                  setRegisterForm((current) => ({ ...current, ...patch }))
                }
                onCancel={handleCancelRegister}
                onSubmit={() => void handleRegister()}
              />
            ) : null}

            <div className="mt-4 grid gap-3 md:grid-cols-3">
              <div className="rounded-xl border border-border bg-background px-3 py-3">
                <div className="text-[11px] font-semibold text-muted-foreground">
                  登记数量
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  {resources.length} 个
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  当前工作区登记的 Docker 沙盒
                </div>
              </div>
              <div className="rounded-xl border border-border bg-background px-3 py-3">
                <div className="text-[11px] font-semibold text-muted-foreground">
                  运行中
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  {runningCount} 个
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  正在运行的容器实例
                </div>
              </div>
              <div className="rounded-xl border border-border bg-background px-3 py-3">
                <div className="text-[11px] font-semibold text-muted-foreground">
                  当前作用
                </div>
                <div className="mt-1 text-sm font-semibold text-foreground">
                  Docker 沙盒
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  选中后进入当前工作区执行策略
                </div>
              </div>
            </div>
          </section>

          {error ? (
            <div className="rounded-lg border border-error/30 bg-error-container px-3 py-2 text-sm text-on-error-container">
              {error}
            </div>
          ) : null}

          {isLoading && resources.length === 0 ? (
            <div className="flex items-center justify-center rounded-2xl border border-dashed border-border py-12 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              正在加载 Docker 沙盒...
            </div>
          ) : resources.length > 0 ? (
            <section className="space-y-3">
              <div>
                <div className="text-xs font-semibold text-muted-foreground">
                  已登记 Docker 沙盒
                </div>
                <div className="mt-1 text-sm text-muted-foreground">
                  这些 Docker 沙盒可以在任务中被引用和使用。
                </div>
              </div>
              {resources.map((resource) => (
                <ContainerResourceCard
                  key={resource.container_id}
                  resource={resource}
                  isActing={actingId === resource.container_id}
                  isActiveSandbox={activeSandboxResourceId === resource.container_id}
                  isSelectingSandbox={selectingSandboxId === resource.container_id}
                  onStart={handleStart}
                  onStop={handleStop}
                  onViewLogs={handleViewLogs}
                  onDelete={handleDelete}
                  onSelectSandbox={onSelectSandbox}
                />
              ))}
            </section>
          ) : (
            <div className="rounded-2xl border border-dashed border-border bg-background px-5 py-10 text-center">
              <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-xl bg-muted">
                <Container className="h-5 w-5 text-muted-foreground" />
              </div>
              <div className="mt-3 text-sm font-semibold text-foreground">
                还没有可用的 Docker 沙盒材料
              </div>
              <div className="mt-1 text-sm text-muted-foreground">
                登记容器后会显示在这里，可设为当前工作区 Docker 沙盒。
              </div>
              <Button
                type="button"
                variant="default"
                size="sm"
                className="mt-4"
                disabled={!workspaceId}
                onClick={() => setIsRegisterOpen(true)}
              >
                <Plus className="h-4 w-4" />
                登记 Docker 沙盒
              </Button>
            </div>
          )}
        </div>
      </main>
    </div>
  );

  return content;
}
