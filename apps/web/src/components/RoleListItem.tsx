import { Pencil, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { RoleVisibilityPopover } from "@/components/RoleVisibilityPopover";
import type {
  RoleItem,
  RoleVisibilityUpdatePayload,
} from "@/lib/api/roles";

interface RoleListItemProps {
  role: RoleItem;
  onEdit?: (role: RoleItem) => void;
  onDelete?: (role: RoleItem) => void;
  onPreview?: (role: RoleItem) => void;
  onVisibilitySave?: (
    role: RoleItem,
    payload: RoleVisibilityUpdatePayload,
  ) => Promise<void>;
  onEnableDefault?: (role: RoleItem) => Promise<void>;
  onEnableWorkspace?: (role: RoleItem) => Promise<void>;
  onDefaultEnabledChange?: (role: RoleItem, enabled: boolean) => Promise<void>;
}

export function RoleListItem({
  role,
  onEdit,
  onDelete,
  onPreview,
  onVisibilitySave,
  onEnableDefault,
  onEnableWorkspace,
  onDefaultEnabledChange,
}: RoleListItemProps) {
  const isSystemRole = role.source === "system" || role.source === "builtin";
  const isInstalled = role.installedToGlobal || role.installedToWorkspace;
  const isMarketView = Boolean(onEnableDefault);

  // 浏览视图（market）显示安装状态；管理视图（manage）显示可见性
  const statusLabel = !isInstalled
    ? "可安装"
    : isMarketView
      ? "已安装"
      : role.hostSelectable
        ? "Agent 可见"
        : "Agent 不可见";
  const statusVariant = !isInstalled
    ? "secondary"
    : isMarketView
      ? "success"
      : role.hostSelectable
        ? "success"
        : "outline";

  const installedLabel = role.installedToWorkspace
    ? "已安装到当前工作区"
    : role.installedToGlobal
      ? "已安装到我的默认"
      : null;
  const installedInCurrentScope =
    role.installedToGlobal ||
    role.installedToWorkspace ||
    role.source === "global" ||
    role.source === "workspace";
  const canRemove = Boolean(onDelete) && installedInCurrentScope;
  const removeLabel = isSystemRole
    ? role.installedToGlobal
      ? "移出我的默认"
      : role.installedToWorkspace
        ? "移出当前工作区"
        : "移出"
    : "删除";
  const removeTitle = isSystemRole
    ? `${removeLabel}，内置源仍可从市场重新安装`
    : "删除";

  return (
    <div className="flex items-start gap-3 rounded-xl border border-border bg-card px-4 py-3 shadow-sm">
      <div
        className="min-w-0 flex-1 cursor-pointer"
        onClick={() => onPreview?.(role)}
      >
        {/* 第一行：名称 + badges + 操作按钮 */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="min-w-0 truncate text-sm font-semibold text-foreground">
              {role.displayName}
            </span>
            {role.displayName !== role.name ? (
              <Badge variant="outline" className="text-[10px]">
                {role.name}
              </Badge>
            ) : null}
            {isSystemRole ? (
              <Badge variant="outline" className="text-[10px]">
                系统
              </Badge>
            ) : (
              <Badge variant="outline" className="text-[10px]">
                自定义
              </Badge>
            )}
            <Badge variant={statusVariant} className="text-[10px]">
              {statusLabel}
            </Badge>
            {/* 管理视图显示安装位置标签 */}
            {installedLabel && !isMarketView ? (
              <Badge variant="info" className="text-[10px]">
                {installedLabel}
              </Badge>
            ) : null}
            {role.lockReason ? (
              <Badge variant="warning" className="text-[10px]">
                锁定
              </Badge>
            ) : null}
          </div>

          {/* 操作按钮固定在名称行右侧 */}
          <div className="flex shrink-0 items-center gap-1">
            {onDefaultEnabledChange && isInstalled ? (
              <div className="mr-2 flex items-center gap-2 text-xs text-muted-foreground">
                <span>默认启用</span>
                <Switch
                  checked={role.defaultEnabled}
                  disabled={!role.hostSelectable || Boolean(role.lockReason)}
                  onCheckedChange={(checked) =>
                    void onDefaultEnabledChange(role, checked)
                  }
                  data-testid={`role-default-enabled-toggle-${role.name}`}
                />
              </div>
            ) : null}

            {onEnableDefault && !role.installedToGlobal ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  void onEnableDefault(role);
                }}
              >
                <Plus className="h-3.5 w-3.5" />
                安装到我的协作专家
              </Button>
            ) : null}

            {onEnableWorkspace && !role.installedToWorkspace ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 gap-1.5 text-xs"
                onClick={(e) => {
                  e.stopPropagation();
                  void onEnableWorkspace(role);
                }}
              >
                <Plus className="h-3.5 w-3.5" />
                安装到工作区
              </Button>
            ) : null}

            {onVisibilitySave ? (
              <RoleVisibilityPopover
                role={role}
                onSave={onVisibilitySave}
              />
            ) : null}

            {!isSystemRole && onEdit ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 w-8 rounded-lg p-0"
                onClick={(e) => {
                  e.stopPropagation();
                  onEdit(role);
                }}
                title="编辑"
              >
                <Pencil className="h-3.5 w-3.5" />
              </Button>
            ) : null}

            {canRemove ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className={cn(
                  "h-8 rounded-lg text-destructive hover:text-destructive",
                  isSystemRole ? "px-2 text-xs" : "w-8 p-0",
                )}
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete?.(role);
                }}
                title={removeTitle}
                data-testid={`role-remove-${role.name}`}
              >
                <Trash2 className="h-3.5 w-3.5" />
                {isSystemRole ? (
                  <span className="ml-1.5">{removeLabel}</span>
                ) : null}
              </Button>
            ) : null}
          </div>
        </div>

        {/* 第二行：描述 */}
        <p className="mt-0.5 truncate text-xs text-muted-foreground">
          {role.description || "暂无描述"}
        </p>

        {/* 第三行：模型 + 工具（合并为一行） */}
        {(role.model || role.toolCount > 0) && (
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {role.model ? `模型: ${role.model}` : null}
            {role.model && role.toolCount > 0 ? " · " : null}
            {role.toolCount > 0 ? `工具: ${role.toolCount} 个` : null}
          </p>
        )}
      </div>
    </div>
  );
}
