import { useCallback, useEffect, useState } from "react";
import { Eye, EyeOff, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import { apiRequest } from "@/lib/api/httpClient";

interface GlobalEnvVarsDialogProps {
  userId: string;
}

export function GlobalEnvVarsDialog({
  userId,
}: GlobalEnvVarsDialogProps) {
  const [envVars, setEnvVars] = useState<Record<string, string>>({});
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!userId) return;
    apiRequest<{ env_vars: Record<string, string> }>(
      `/api/global-env-vars/${userId}`,
    )
      .then((res) => setEnvVars(res.env_vars ?? {}))
      .catch(() => {});
  }, [userId]);

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
      setSaving(true);
      try {
        await apiRequest(`/api/global-env-vars/${userId}`, {
          method: "PUT",
          body: { env_vars: updated },
        });
        setEnvVars(updated);
      } finally {
        setSaving(false);
      }
    },
    [userId],
  );

  const handleAdd = useCallback(() => {
    const key = newKey.trim();
    if (!key || key in envVars) return;
    save({ ...envVars, [key]: newValue });
    setNewKey("");
    setNewValue("");
  }, [newKey, newValue, envVars, save]);

  const handleDelete = useCallback(
    (key: string) => {
      const updated = { ...envVars };
      delete updated[key];
      save(updated);
    },
    [envVars, save],
  );

  const entries = Object.entries(envVars);

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        对所有工作区生效，工作区级别的同名变量会覆盖此处的值。
      </p>

      <div className="flex flex-col gap-2 max-h-80 overflow-y-auto">
        {entries.length === 0 && (
          <div className="text-xs text-muted-foreground py-4 text-center">
            暂无全局环境变量
          </div>
        )}
        {entries.map(([key, value]) => (
          <div
            key={key}
            className="flex items-center gap-2 rounded-md border bg-card p-2"
          >
            <code className="text-xs font-mono text-primary min-w-0 truncate flex-1">
              {key}
            </code>
            <span className="text-xs text-muted-foreground">=</span>
            <code className="text-xs font-mono min-w-0 truncate flex-[2]">
              {visibleKeys.has(key)
                ? value
                : "●".repeat(Math.min(12, value.length || 4))}
            </code>
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
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 shrink-0 text-destructive hover:text-destructive"
              onClick={() => handleDelete(key)}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        ))}
      </div>

      <div className="flex items-center gap-2 pt-2 border-t">
        <Input
          className="h-8 text-xs font-mono flex-1"
          placeholder="KEY"
          value={newKey}
          onChange={(e) => setNewKey(e.target.value.toUpperCase())}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
        />
        <span className="text-xs text-muted-foreground">=</span>
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
        >
          <Plus className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
