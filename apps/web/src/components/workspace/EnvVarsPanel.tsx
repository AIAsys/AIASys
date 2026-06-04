import { useCallback, useEffect, useMemo, useState } from "react";
import { Eye, EyeOff, Plus, Trash2, Globe, Pencil } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { apiRequest } from "@/lib/api/httpClient";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";

interface EnvVarsPanelProps {
  workspaceSummary?: TaskWorkspaceSummary;
  onSaved?: () => void;
  variant?: "compact" | "runtime-dialog";
}

type VarSource = "global" | "workspace" | "overridden";

interface MergedEnvVar {
  key: string;
  value: string;
  source: VarSource;
}

export function EnvVarsPanel({
  workspaceSummary,
  onSaved,
  variant = "compact",
}: EnvVarsPanelProps) {
  const workspaceEnvVars = useMemo(
    () => workspaceSummary?.runtime_binding?.env_vars ?? {},
    [workspaceSummary?.runtime_binding?.env_vars],
  );
  const workspaceId = workspaceSummary?.workspace_id;

  const [globalEnvVars, setGlobalEnvVars] = useState<Record<string, string>>({});
  const [globalLoading, setGlobalLoading] = useState(false);
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setGlobalLoading(true);
    apiRequest<{ env_vars: Record<string, string> }>("/api/global-env-vars/me")
      .then((res) => setGlobalEnvVars(res.env_vars ?? {}))
      .catch(() => setGlobalEnvVars({}))
      .finally(() => setGlobalLoading(false));
  }, []);

  const mergedVars = useMemo<MergedEnvVar[]>(() => {
    const map = new Map<string, MergedEnvVar>();
    // 先放入全局变量
    for (const [key, value] of Object.entries(globalEnvVars)) {
      map.set(key, { key, value, source: "global" });
    }
    // 工作区变量覆盖
    for (const [key, value] of Object.entries(workspaceEnvVars)) {
      if (map.has(key)) {
        map.set(key, { key, value, source: "overridden" });
      } else {
        map.set(key, { key, value, source: "workspace" });
      }
    }
    return Array.from(map.values()).sort((a, b) => a.key.localeCompare(b.key));
  }, [globalEnvVars, workspaceEnvVars]);

  const toggleVisible = useCallback((key: string) => {
    setVisibleKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const save = useCallback(
    async (updated: Record<string, string>) => {
      if (!workspaceId) return;
      setSaving(true);
      setError(null);
      try {
        await apiRequest(`/api/workspaces/${workspaceId}`, {
          method: "PATCH",
          body: { runtime_binding: { env_vars: updated } },
        });
        onSaved?.();
      } catch (err) {
        setError(err instanceof Error ? err.message : "保存环境变量失败");
      } finally {
        setSaving(false);
      }
    },
    [workspaceId, onSaved],
  );

  const handleAdd = useCallback(() => {
    const key = newKey.trim();
    if (!key) return;
    const updated = { ...workspaceEnvVars, [key]: newValue };
    save(updated);
    setNewKey("");
    setNewValue("");
  }, [newKey, newValue, workspaceEnvVars, save]);

  const handleDelete = useCallback(
    (key: string) => {
      const updated = { ...workspaceEnvVars };
      delete updated[key];
      save(updated);
    },
    [workspaceEnvVars, save],
  );

  const startEdit = useCallback((key: string, value: string) => {
    setEditingKey(key);
    setEditValue(value);
  }, []);

  const commitEdit = useCallback(() => {
    if (!editingKey) return;
    const key = editingKey.trim();
    if (!key || !workspaceId) return;
    const updated = { ...workspaceEnvVars, [key]: editValue };
    save(updated);
    setEditingKey(null);
    setEditValue("");
  }, [editingKey, editValue, workspaceEnvVars, save, workspaceId]);

  const cancelEdit = useCallback(() => {
    setEditingKey(null);
    setEditValue("");
  }, []);

  const isWorkspaceVar = (source: VarSource) => source === "workspace" || source === "overridden";

  const sourceBadge = (source: VarSource) => {
    if (source === "global") {
      return (
        <Badge variant="secondary" className="text-[10px] h-4 px-1 gap-0.5 shrink-0">
          <Globe className="h-2.5 w-2.5" />
          全局
        </Badge>
      );
    }
    if (source === "overridden") {
      return (
        <Badge
          variant="outline"
          className="text-[10px] h-4 px-1 shrink-0 border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900 dark:bg-amber-950 dark:text-amber-300"
        >
          覆盖全局
        </Badge>
      );
    }
    return (
      <Badge variant="outline" className="text-[10px] h-4 px-1 shrink-0">
        工作区
      </Badge>
    );
  };

  return (
    <div className={variant === "runtime-dialog" ? "flex flex-col gap-4 p-5" : "flex flex-col gap-3 p-3"}>
      {variant === "compact" ? (
        <div className="text-sm text-muted-foreground">
          注入到 Shell / Python / Notebook 执行环境中的变量
        </div>
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          <div className="rounded-xl border border-border bg-background px-3 py-3">
            <div className="text-[11px] font-semibold text-muted-foreground">当前工作区</div>
            <div className="mt-1 text-sm font-semibold text-foreground">{workspaceSummary?.title || "未选择"}</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">变量只影响当前工作区</div>
          </div>
          <div className="rounded-xl border border-border bg-background px-3 py-3">
            <div className="text-[11px] font-semibold text-muted-foreground">注入位置</div>
            <div className="mt-1 text-sm font-semibold text-foreground">Shell / Python</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">下一次执行会读取最新值</div>
          </div>
          <div className="rounded-xl border border-border bg-background px-3 py-3">
            <div className="text-[11px] font-semibold text-muted-foreground">生效变量</div>
            <div className="mt-1 text-sm font-semibold text-foreground">{mergedVars.length} 个</div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              全局 {Object.keys(globalEnvVars).length} 个 · 工作区 {Object.keys(workspaceEnvVars).length} 个
            </div>
          </div>
        </div>
      )}

      {error ? (
        <div className="rounded-lg border border-error/30 bg-error-container px-3 py-2 text-sm text-on-error-container">
          {error}
        </div>
      ) : null}

      {/* 统一生效变量列表 */}
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <div className="text-xs font-medium text-muted-foreground">
            生效环境变量
            {mergedVars.length > 0 && (
              <span className="ml-1 text-muted-foreground/60">({mergedVars.length} 个)</span>
            )}
          </div>
        </div>

        {globalLoading && mergedVars.length === 0 && (
          <div className="rounded-lg border border-dashed border-border py-6 text-center text-sm text-muted-foreground">
            加载中...
          </div>
        )}

        {!globalLoading && mergedVars.length === 0 && (
          <div className="rounded-lg border border-dashed border-border py-6 text-center text-sm text-muted-foreground">
            暂无任何环境变量
          </div>
        )}

        {mergedVars.map(({ key, value, source }) => {
          const isEditing = editingKey === key && isWorkspaceVar(source);
          const wsOnly = isWorkspaceVar(source);
          return (
            <div
              key={key}
              className="flex items-center gap-2 rounded-md border bg-card p-2"
            >
              <div className="flex min-w-0 flex-1 items-center gap-1.5">
                <code className="text-xs font-mono text-primary min-w-0 truncate">
                  {key}
                </code>
                {sourceBadge(source)}
              </div>

              <span className="text-xs text-muted-foreground">=</span>

              {isEditing ? (
                <Input
                  className="h-7 text-xs font-mono flex-[2] min-w-0"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitEdit();
                    if (e.key === "Escape") cancelEdit();
                  }}
                  autoFocus
                />
              ) : (
                <code className="text-xs font-mono min-w-0 truncate flex-[2]">
                  {visibleKeys.has(key) ? value : "●".repeat(Math.min(12, value.length || 4))}
                </code>
              )}

              {/* 操作按钮 */}
              {isEditing ? (
                <>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs shrink-0"
                    onClick={commitEdit}
                  >
                    保存
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 px-2 text-xs shrink-0"
                    onClick={cancelEdit}
                  >
                    取消
                  </Button>
                </>
              ) : (
                <>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="h-6 w-6 shrink-0"
                    onClick={() => toggleVisible(key)}
                  >
                    {visibleKeys.has(key) ? (
                      <EyeOff className="h-3.5 w-3.5" />
                    ) : (
                      <Eye className="h-3.5 w-3.5" />
                    )}
                  </Button>
                  {wsOnly && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0"
                      onClick={() => startEdit(key, value)}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                  )}
                  {wsOnly && (
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-6 w-6 shrink-0 text-destructive hover:text-destructive"
                      onClick={() => handleDelete(key)}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  )}
                </>
              )}
            </div>
          );
        })}
      </div>

      {/* 添加 / 编辑提示 */}
      <div className="grid gap-2 border-t pt-3 md:grid-cols-[minmax(0,1fr)_auto_minmax(0,2fr)_auto]">
        <Input
          className="h-8 text-xs font-mono flex-1"
          placeholder="KEY"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <span className="hidden self-center text-xs text-muted-foreground md:block">=</span>
        <Input
          className="h-8 text-xs font-mono flex-[2]"
          placeholder="value"
          value={newValue}
          onChange={(e) => setNewValue(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8 shrink-0"
          disabled={!newKey.trim() || saving}
          onClick={handleAdd}
          aria-label="新增环境变量"
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>

      {newKey.trim() && newKey.trim() in globalEnvVars && (
        <div className="text-[11px] text-amber-600 dark:text-amber-400">
          此变量名与全局环境变量同名，保存后将覆盖全局值
        </div>
      )}

      {newKey.trim() && newKey.trim() in workspaceEnvVars && (
        <div className="text-[11px] text-blue-600 dark:text-blue-400">
          此变量已存在于工作区变量中，保存后将更新其值
        </div>
      )}
    </div>
  );
}
