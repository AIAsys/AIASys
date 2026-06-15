import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import {
  AlertCircle,
  Database,
  FolderOpen,
  Info,
  Loader2,
  MoveRight,
  Save,
  ServerCog,
} from "lucide-react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Separator } from "@/components/ui/separator";
import {
  getRuntimeStorageSettings,
  getRuntimeStorageMigrationStatus,
  previewRuntimeStorageMigration,
  saveRuntimeStorageSettings,
  startRuntimeStorageMigration,
  validateRuntimeStoragePath,
  type RuntimeStorageMigrationResponse,
  type RuntimeStoragePathKey,
  type RuntimeStoragePathSetting,
  type RuntimeStoragePathValidationResponse,
  type RuntimeStorageSettingsResponse,
} from "@/lib/api/runtimeStorage";


const PATH_LABELS: Record<RuntimeStoragePathKey, string> = {
  data_dir: "数据根目录",
  workspaces_dir: "工作区根目录",
  logs_dir: "日志目录",
};

const PATH_HELP: Record<RuntimeStoragePathKey, string> = {
  data_dir: "存放系统运行态数据和默认派生目录。",
  workspaces_dir: "新建工作区、会话和用户默认层默认落到这里。",
  logs_dir: "存放后端运行日志。",
};

const PATH_ICONS: Record<RuntimeStoragePathKey, ReactNode> = {
  data_dir: <Database className="h-4 w-4" />,
  workspaces_dir: <FolderOpen className="h-4 w-4" />,
  logs_dir: <ServerCog className="h-4 w-4" />,
};

function buildDraft(
  settings: RuntimeStorageSettingsResponse | null,
): Partial<Record<RuntimeStoragePathKey, string>> {
  const draft: Partial<Record<RuntimeStoragePathKey, string>> = {};
  settings?.paths.forEach((item) => {
    draft[item.key] = item.configured_path || item.effective_path;
  });
  return draft;
}

function getPathStatus(
  item: RuntimeStoragePathSetting,
  draftValue?: string,
): "env" | "pending" | "changed" | "current" {
  if (!item.editable) return "env";
  if (draftValue && draftValue !== item.effective_path) return "changed";
  if (item.pending_path && item.pending_path !== item.effective_path) return "pending";
  return "current";
}

function formatPathStatus(status: ReturnType<typeof getPathStatus>) {
  if (status === "env") return "环境变量控制";
  if (status === "changed") return "待保存";
  if (status === "pending") return "重启后生效";
  return "当前生效";
}

function validationBadge(result?: RuntimeStoragePathValidationResponse) {
  if (!result) return null;
  return (
    <Badge variant={result.ok ? "success" : "error"}>
      {result.ok ? "可用" : "不可用"}
    </Badge>
  );
}

function formatMigrationStatus(status?: string | null) {
  if (status === "in_progress") return "迁移中";
  if (status === "completed") return "已完成";
  if (status === "failed") return "失败";
  if (status === "preview") return "预检结果";
  if (status === "unknown") return "状态未知";
  return "未开始";
}

function migrationProgressValue(migration: RuntimeStorageMigrationResponse | null) {
  const total = migration?.progress?.total_items || 0;
  const completed = migration?.progress?.completed_items || 0;
  if (!total) return 0;
  return Math.min(100, Math.round((completed / total) * 100));
}

export function StorageSettingsDialog() {
  const [settings, setSettings] = useState<RuntimeStorageSettingsResponse | null>(null);
  const [migration, setMigration] = useState<RuntimeStorageMigrationResponse | null>(null);
  const [draft, setDraft] = useState<Partial<Record<RuntimeStoragePathKey, string>>>({});
  const [validations, setValidations] = useState<
    Partial<Record<RuntimeStoragePathKey, RuntimeStoragePathValidationResponse>>
  >({});
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isPreviewingMigration, setIsPreviewingMigration] = useState(false);
  const [isStartingMigration, setIsStartingMigration] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedNotice, setSavedNotice] = useState<string | null>(null);

  const loadSettings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const [data, migrationData] = await Promise.all([
        getRuntimeStorageSettings(),
        getRuntimeStorageMigrationStatus(),
      ]);
      setSettings(data);
      setMigration(migrationData);
      setDraft(buildDraft(data));
      setValidations({});
    } catch (err) {
      setError(err instanceof Error ? err.message : "读取存储设置失败");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings]);

  useEffect(() => {
    if (migration?.status !== "in_progress") return;
    const timer = window.setInterval(() => {
      void getRuntimeStorageMigrationStatus()
        .then((data) => {
          setMigration(data);
          if (data.status === "completed") {
            setSavedNotice("迁移已完成，重启系统后使用新存储位置。");
            void loadSettings();
          }
          if (data.status === "failed") {
            setError(data.message || "迁移失败");
          }
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "读取迁移状态失败");
        });
    }, 1500);
    return () => window.clearInterval(timer);
  }, [loadSettings, migration?.status]);

  const editablePaths = useMemo(
    () => settings?.paths.filter((item) => item.editable) ?? [],
    [settings],
  );

  const hasDraftChanges = useMemo(
    () =>
      editablePaths.some((item) => {
        const value = (draft[item.key] || "").trim();
        return value && value !== item.configured_path;
      }),
    [draft, editablePaths],
  );

  const isMigrationRunning = migration?.status === "in_progress";

  const buildEditablePayload = () => {
    const payload: Partial<Record<RuntimeStoragePathKey, string>> = {};
    editablePaths.forEach((item) => {
      payload[item.key] = (draft[item.key] || "").trim();
    });
    return payload;
  };

  const handleValidatePath = async (key: RuntimeStoragePathKey) => {
    const value = (draft[key] || "").trim();
    if (!value) {
      setError("路径不能为空");
      return;
    }
    setError(null);
    try {
      const result = await validateRuntimeStoragePath(value, true);
      setValidations((prev) => ({ ...prev, [key]: result }));
    } catch (err) {
      setError(err instanceof Error ? err.message : "路径校验失败");
    }
  };

  const handlePreviewMigration = async () => {
    setIsPreviewingMigration(true);
    setError(null);
    setSavedNotice(null);
    try {
      const data = await previewRuntimeStorageMigration(buildEditablePayload());
      setMigration(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "迁移预检失败");
    } finally {
      setIsPreviewingMigration(false);
    }
  };

  const handleStartMigration = async () => {
    setIsStartingMigration(true);
    setError(null);
    setSavedNotice(null);
    try {
      const data = await startRuntimeStorageMigration(buildEditablePayload());
      setMigration(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "启动迁移失败");
    } finally {
      setIsStartingMigration(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    setSavedNotice(null);
    try {
      const data = await saveRuntimeStorageSettings(buildEditablePayload());
      setSettings(data);
      setDraft(buildDraft(data));
      setSavedNotice("路径配置已保存，重启系统后生效。");
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存存储设置失败");
    } finally {
      setIsSaving(false);
    }
  };

  const content = (
    <div className="flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">
            {isLoading ? (
              <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
                正在读取存储设置...
              </div>
            ) : (
              <>
                {error ? (
                  <Alert variant="destructive" className="mb-4">
                    <AlertCircle className="h-4 w-4" />
                    <AlertTitle>操作失败</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                  </Alert>
                ) : null}
                {savedNotice ? (
                  <div className="mb-4 flex items-start gap-3 rounded-lg border border-warning-container bg-warning-container/40 p-4 text-sm">
                    <Info className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
                    <div>
                      <p className="font-medium text-foreground">需要重启系统</p>
                      <p className="text-muted-foreground">{savedNotice}</p>
                    </div>
                  </div>
                ) : null}

                <div className="space-y-4">
                  <p className="text-sm text-muted-foreground">
                    修改后保存为待生效配置，当前运行中的后端不会切换目录。
                  </p>

                  <div className="space-y-3">
                    {settings?.paths.map((item) => {
                      const status = getPathStatus(item, draft[item.key]);
                      const validation = validations[item.key];
                      return (
                        <div
                          key={item.key}
                          className="rounded-lg border border-border bg-background p-4"
                        >
                          <div className="mb-3 flex items-start justify-between gap-3">
                            <div className="flex min-w-0 items-start gap-3">
                              <div className="mt-0.5 rounded-md bg-muted p-2 text-muted-foreground">
                                {PATH_ICONS[item.key]}
                              </div>
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <Label htmlFor={`storage-${item.key}`}>
                                    {PATH_LABELS[item.key]}
                                  </Label>
                                  <Badge variant={status === "env" ? "outline" : "secondary"}>
                                    {formatPathStatus(status)}
                                  </Badge>
                                  {validationBadge(validation)}
                                </div>
                                <p className="mt-1 text-xs text-muted-foreground">
                                  {PATH_HELP[item.key]}
                                </p>
                              </div>
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              disabled={!item.editable || isMigrationRunning}
                              onClick={() => void handleValidatePath(item.key)}
                            >
                              检查
                            </Button>
                          </div>

                          <Input
                            id={`storage-${item.key}`}
                            value={draft[item.key] ?? ""}
                            disabled={!item.editable || isMigrationRunning}
                            onChange={(event) => {
                              setDraft((prev) => ({ ...prev, [item.key]: event.target.value }));
                              setValidations((prev) => ({ ...prev, [item.key]: undefined }));
                              setMigration(null);
                              setSavedNotice(null);
                            }}
                            className="font-mono text-xs"
                          />
                          <div className="mt-2 space-y-1 text-xs text-muted-foreground">
                            <p>当前生效：{item.effective_path}</p>
                            {item.overridden_by_env ? (
                              <p>由环境变量 {item.overridden_by_env} 控制，界面不能覆盖。</p>
                            ) : null}
                            {validation ? <p>{validation.message}</p> : null}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="mt-6 space-y-4">
                  <div className="flex items-start gap-3 rounded-lg border border-border bg-muted/30 p-4 text-sm">
                    <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                    <div>
                      <p className="font-medium text-foreground">保存后需要重启</p>
                      <p className="text-muted-foreground">
                        当前会话、工作区注册、文件工具和资源索引已经绑定到当前目录。系统不会在运行中切换到新目录。
                      </p>
                    </div>
                  </div>
                  <div className="rounded-lg border border-border bg-muted/40 p-4 text-sm text-muted-foreground">
                    <p className="font-medium text-foreground">保存配置不会搬迁已有数据</p>
                    <p className="mt-2">
                      新路径会在下次启动后成为默认存储位置。需要让旧工作区继续显示时，先执行下面的数据迁移。
                    </p>
                  </div>
                  <div className="rounded-lg border border-border p-4">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">已有数据迁移</p>
                        <p className="mt-1 text-xs text-muted-foreground">
                          迁移会复制当前目录数据，完成前系统会暂时拒绝新的写操作。
                        </p>
                      </div>
                      <Badge variant={isMigrationRunning ? "secondary" : "outline"}>
                        {formatMigrationStatus(migration?.status)}
                      </Badge>
                    </div>

                    {migration ? (
                      <div className="mt-4 space-y-3">
                        {isMigrationRunning || migration.status === "completed" ? (
                          <div className="space-y-2">
                            <Progress value={migrationProgressValue(migration)} />
                            <p className="text-xs text-muted-foreground">
                              {migration.message || "正在处理迁移任务"}
                            </p>
                          </div>
                        ) : null}

                        {migration.items.length ? (
                          <div className="space-y-2">
                            {migration.items.map((item) => (
                              <div
                                key={item.key}
                                className="rounded-md border border-border bg-muted/30 p-3 text-xs"
                              >
                                <div className="flex flex-wrap items-center gap-2 text-foreground">
                                  <span className="font-medium">{PATH_LABELS[item.key]}</span>
                                  <Badge variant={item.ok ? "success" : "error"}>
                                    {item.ok ? "可迁移" : "需处理"}
                                  </Badge>
                                  <span className="text-muted-foreground">{item.message}</span>
                                </div>
                                <div className="mt-2 grid gap-1 font-mono text-muted-foreground">
                                  <span className="break-all">从 {item.source_path}</span>
                                  <span className="flex items-center gap-1 break-all">
                                    <MoveRight className="h-3 w-3 shrink-0" />
                                    到 {item.target_path}
                                  </span>
                                </div>
                              </div>
                            ))}
                          </div>
                        ) : null}

                        {migration.warnings.length ? (
                          <div className="text-xs text-warning">
                            {migration.warnings.join("；")}
                          </div>
                        ) : null}
                        {migration.errors.length ? (
                          <div className="text-xs text-destructive">
                            {migration.errors.join("；")}
                          </div>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="mt-4 flex flex-wrap items-center gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={() => void handlePreviewMigration()}
                        disabled={isMigrationRunning || isPreviewingMigration || isStartingMigration}
                      >
                        {isPreviewingMigration ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : null}
                        预检迁移
                      </Button>
                      <Button
                        type="button"
                        size="sm"
                        onClick={() => void handleStartMigration()}
                        disabled={
                          isMigrationRunning ||
                          isPreviewingMigration ||
                          isStartingMigration ||
                          !migration?.can_start
                        }
                      >
                        {isStartingMigration || isMigrationRunning ? (
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        ) : null}
                        迁移已有数据
                      </Button>
                    </div>
                  </div>
                  <div className="rounded-lg border border-border p-4">
                    <p className="text-sm font-medium text-foreground">配置文件</p>
                    <p className="mt-2 break-all font-mono text-xs text-muted-foreground">
                      {settings?.config_path || "正在读取..."}
                    </p>
                  </div>
                </div>
              </>
            )}
          </div>

          <Separator />
          <div className="flex items-center justify-between gap-3 px-6 py-4">
            <div className="text-xs text-muted-foreground">
              {settings?.restart_required
                ? "已有待生效配置，重启后使用新路径。"
                : "当前没有待重启生效的路径变更。"}
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => void loadSettings()}
                disabled={isLoading || isSaving || isMigrationRunning}
              >
                重新读取
              </Button>
              <Button
                type="button"
                onClick={() => void handleSave()}
                disabled={
                  isLoading ||
                  isSaving ||
                  isMigrationRunning ||
                  (!hasDraftChanges && !settings?.restart_required)
                }
              >
                <Save className="mr-2 h-4 w-4" />
                {isSaving ? "保存中..." : "保存配置"}
              </Button>
            </div>
          </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-background">
      {content}
    </div>
  );
}
