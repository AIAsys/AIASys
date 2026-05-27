/**
 * SkillCard - Skill 市场卡片组件
 *
 * 新架构下展示 Skill 仓库或工作区启用的 Skill，
 * 根据启用状态显示不同操作按钮。
 */
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import type { MarketSkill } from "@/types/api";
import { useState } from "react";
import {
  BookOpen,
  Eye,
  KeyRound,
  Plus,
  RefreshCw,
  Trash2,
} from "lucide-react";

interface SkillCardProps {
  skill: MarketSkill;
  workspaceId?: string | null;
  /** 当前正在处理的 skill 名称（显示 loading） */
  processingSkill: string | null;
  onInstall: (skillName: string, version?: string) => void;
  onUninstall: (skillName: string) => void;
  onUpdate?: (skillName: string) => void;
  onToggleGlobal?: (skillName: string, enabled: boolean) => void;
  onViewEntry?: (skillName: string) => void;
  /** 从 Skill 仓库移除（仅在有权限时展示） */
  onRemoveStore?: (skillName: string) => void;
}

export function SkillCard({
  skill,
  workspaceId,
  processingSkill,
  onInstall,
  onUninstall,
  onUpdate,
  onToggleGlobal,
  onViewEntry,
  onRemoveStore,
}: SkillCardProps) {
  const isProcessing = processingSkill === skill.name;
  const [isToggling, setIsToggling] = useState(false);

  const handleToggle = async () => {
    if (!onToggleGlobal) return;
    setIsToggling(true);
    await onToggleGlobal(skill.name, skill.globally_enabled ?? false);
    setIsToggling(false);
  };

  const canInstallToWorkspace = Boolean(workspaceId) && !skill.installed;

  return (
    <Card className="group flex h-full flex-col overflow-hidden rounded-3xl border-border bg-muted/60 transition-all duration-200 hover:-translate-y-0.5 hover:border-tertiary/30 hover:bg-card hover:shadow-md">
      <CardHeader className="space-y-4 pb-4">
        <div className="flex items-start justify-between gap-3">
          <div className="rounded-2xl border border-tertiary/20 bg-tertiary-container p-2.5">
            <BookOpen className="h-5 w-5 text-on-tertiary-container" />
          </div>
          <div className="flex shrink-0 flex-wrap items-center justify-end gap-2">
            <span className="inline-flex items-center rounded-md border border-border bg-card px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
              {skill.source === "builtin"
                ? "系统内置"
                : skill.source === "store"
                  ? "已导入"
                  : "已启用"}
            </span>
            {skill.installed && skill.hash_status === "outdated" ? (
              <span className="inline-flex items-center rounded-md border border-warning/20 bg-warning-container/60 px-2 py-0.5 text-[11px] font-medium text-on-warning-container">
                可更新
              </span>
            ) : null}
            {skill.installed && skill.hash_status === "modified" ? (
              <span className="inline-flex items-center rounded-md border border-info/20 bg-info-container/60 px-2 py-0.5 text-[11px] font-medium text-on-info-container">
                已自定义
              </span>
            ) : null}
            {skill.installed && skill.hash_status === "custom" ? (
              <span className="inline-flex items-center rounded-md border border-secondary/20 bg-secondary-container/60 px-2 py-0.5 text-[11px] font-medium text-on-secondary-container">
                自定义
              </span>
            ) : null}
            {onViewEntry ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={() => onViewEntry(skill.name)}
                disabled={isProcessing}
              >
                <Eye className="mr-1.5 h-3.5 w-3.5" />
                预览
              </Button>
            ) : null}
            {canInstallToWorkspace ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs"
                onClick={() => onInstall(skill.name)}
                disabled={isProcessing}
              >
                <Plus className="mr-1.5 h-3.5 w-3.5" />
                启用
              </Button>
            ) : null}
            {skill.installed && skill.hash_status === "outdated" && onUpdate ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs text-warning hover:border-warning/30 hover:bg-warning/5 hover:text-warning"
                onClick={() => onUpdate(skill.name)}
                disabled={isProcessing}
              >
                <RefreshCw className="mr-1.5 h-3.5 w-3.5" />
                更新
              </Button>
            ) : null}
            {skill.installed && onUninstall ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs text-destructive hover:border-destructive/30 hover:bg-destructive/5 hover:text-destructive"
                onClick={() => onUninstall(skill.name)}
                disabled={isProcessing}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                卸载
              </Button>
            ) : null}
            {!skill.installed && skill.source === "store" && onRemoveStore ? (
              <Button
                variant="outline"
                size="sm"
                className="h-8 text-xs text-destructive hover:border-destructive/30 hover:bg-destructive/5 hover:text-destructive"
                onClick={() => onRemoveStore(skill.name)}
                disabled={isProcessing}
              >
                <Trash2 className="mr-1.5 h-3.5 w-3.5" />
                移除
              </Button>
            ) : null}
          </div>
        </div>
        <div className="space-y-2">
          <CardTitle className="line-clamp-2 min-h-[2.75rem] text-base font-semibold leading-6">
            {skill.display_name || skill.name}
          </CardTitle>
          <div className="text-xs text-muted-foreground">{skill.name}</div>
          <div className="line-clamp-4 min-h-[5rem] text-sm leading-6 text-muted-foreground">
            {skill.description}
          </div>
          {skill.env_fields && skill.env_fields.length > 0 ? (
            <div className="flex flex-wrap gap-1.5 pt-1">
              <span className="inline-flex items-center gap-1 rounded-md border border-warning/20 bg-warning-container/60 px-2 py-0.5 text-[11px] text-on-warning-container">
                <KeyRound className="h-3 w-3" />
                需配置 {skill.env_fields.length} 项环境变量
              </span>
            </div>
          ) : null}
        </div>
      </CardHeader>

      {onToggleGlobal ? (
        <div className="mt-auto flex items-center gap-2 border-t border-border px-6 py-4">
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-muted-foreground">
              {skill.globally_enabled ? "我的默认启用" : "未启用到我的默认"}
            </span>
            <Switch
              checked={skill.globally_enabled ?? false}
              onCheckedChange={() => void handleToggle()}
              disabled={isProcessing || isToggling}
            />
          </div>
        </div>
      ) : null}
    </Card>
  );
}
