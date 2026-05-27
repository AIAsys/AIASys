import { useEffect, useMemo, useState } from "react";
import { Eye, Loader2, SlidersHorizontal } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Switch } from "@/components/ui/switch";
import type {
  RoleItem,
  RoleVisibilityUpdatePayload,
} from "@/lib/api/roles";

interface RoleVisibilityPopoverProps {
  role: RoleItem;
  disabled?: boolean;
  onSave?: (
    role: RoleItem,
    payload: RoleVisibilityUpdatePayload,
  ) => Promise<void>;
}

const SOURCE_LABELS: Record<RoleItem["visibilitySource"], string> = {
  system: "系统",
  global: "我的默认",
  workspace: "工作区",
};

function getVisibilityLabel(role: RoleItem): string {
  if (!role.hostSelectable) return "Agent 不可见";
  if (!role.defaultEnabled) return "默认关闭";
  return "默认启用";
}

export function RoleVisibilityPopover({
  role,
  disabled = false,
  onSave,
}: RoleVisibilityPopoverProps) {
  const [open, setOpen] = useState(false);
  const [hostSelectable, setHostSelectable] = useState(role.hostSelectable);
  const [defaultEnabled, setDefaultEnabled] = useState(role.defaultEnabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setHostSelectable(role.hostSelectable);
    setDefaultEnabled(role.defaultEnabled);
    setError(null);
  }, [
    open,
    role.defaultEnabled,
    role.hostSelectable,
  ]);

  const locked = Boolean(role.lockReason);
  const readonly = disabled || locked || !onSave;
  const changed =
    hostSelectable !== role.hostSelectable ||
    defaultEnabled !== role.defaultEnabled;

  const triggerTitle = useMemo(() => {
    if (role.lockReason) return role.lockReason;
    return "协作专家可见性与默认启用";
  }, [role.lockReason]);

  const handleSave = async () => {
    if (!onSave || readonly || !changed) return;
    setSaving(true);
    setError(null);
    try {
      await onSave(role, {
        catalog_visible: role.catalogVisible,
        host_selectable: hostSelectable,
        default_enabled: defaultEnabled,
      });
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存协作专家策略失败");
    } finally {
      setSaving(false);
    }
  };

  const TriggerIcon = Eye;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 w-8 rounded-lg p-0"
          title={triggerTitle}
          aria-label={`${role.displayName} 协作专家启用策略`}
          data-testid={`role-visibility-trigger-${role.name}`}
        >
          <TriggerIcon className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        side="left"
        className="w-80 space-y-4 p-4"
        data-testid={`role-visibility-popover-${role.name}`}
      >
        <div className="space-y-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm font-semibold text-foreground">
                {role.displayName}
              </div>
              <div className="mt-1 text-xs text-muted-foreground">
                协作专家可见性与默认启用
              </div>
            </div>
            <Badge variant={role.hostSelectable ? "success" : "secondary"}>
              {getVisibilityLabel(role)}
            </Badge>
          </div>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Badge variant="outline" className="rounded-md px-1.5 py-0.5 text-[10px]">
              来源: {SOURCE_LABELS[role.visibilitySource] ?? role.visibilitySource}
            </Badge>
            {locked ? (
              <Badge variant="warning" className="rounded-md px-1.5 py-0.5 text-[10px]">
                已锁定
              </Badge>
            ) : null}
          </div>
        </div>

        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2.5">
            <div className="min-w-0">
              <div className="text-xs font-medium text-foreground">
                当前 Agent 可见
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                当前 Agent 在协作专家目录中可以看到并选择它
              </div>
            </div>
            <Switch
              checked={hostSelectable}
              onCheckedChange={(checked) => {
                setHostSelectable(checked);
                if (!checked) setDefaultEnabled(false);
              }}
              disabled={readonly || saving}
              data-testid={`role-visibility-host-selectable-${role.name}`}
            />
          </div>

          <div className="flex items-center justify-between gap-3 rounded-md border border-border bg-background px-3 py-2.5">
            <div className="min-w-0">
              <div className="text-xs font-medium text-foreground">
                {role.scope === "global" ? "全局默认启用" : "工作区默认启用"}
              </div>
              <div className="mt-1 text-[11px] text-muted-foreground">
                新会话默认将该专家加入可协作列表
              </div>
            </div>
            <Switch
              checked={defaultEnabled}
              onCheckedChange={setDefaultEnabled}
              disabled={readonly || saving || !hostSelectable}
              data-testid={`role-visibility-default-enabled-${role.name}`}
            />
          </div>
        </div>

        {role.lockReason ? (
          <div className="rounded-md border border-warning/30 bg-warning-container px-3 py-2 text-xs leading-5 text-on-warning-container">
            {role.lockReason}
          </div>
        ) : null}

        {error ? (
          <div className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            {error}
          </div>
        ) : null}

        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8"
            onClick={() => setOpen(false)}
          >
            关闭
          </Button>
          <Button
            type="button"
            size="sm"
            className="h-8"
            onClick={() => void handleSave()}
            disabled={readonly || saving || !changed}
            data-testid={`role-visibility-save-${role.name}`}
          >
            {saving ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <SlidersHorizontal className="h-3.5 w-3.5" />
            )}
            保存
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
