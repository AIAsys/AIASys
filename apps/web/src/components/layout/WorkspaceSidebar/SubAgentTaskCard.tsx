/**
 * SubAgentTaskCard - 子任务状态卡片
 *
 * 显示单个 Sub Agent 子任务的执行状态
 */

import { useState } from "react";
import { 
  Clock, 
  Loader2, 
  CheckCircle2, 
  AlertCircle, 
  Ban,
  ChevronDown,
  ChevronRight,
  Terminal
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";

export interface SubAgentTask {
  id: string;
  title: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress?: number;
  agentId?: string;
  startTime?: Date;
  endTime?: Date;
  output?: string;
  error?: string;
}

interface SubAgentTaskCardProps {
  task: SubAgentTask;
  isSelected?: boolean;
  onSelect?: (taskId: string) => void;
  onCancel?: (taskId: string) => void;
  onRetry?: (taskId: string) => void;
}

interface StatusIconConfig {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgColor: string;
  borderColor: string;
  animate?: boolean;
}

const statusConfig: Record<string, StatusIconConfig> = {
  queued: {
    label: "排队中",
    icon: Clock,
    color: "text-warning",
    bgColor: "bg-warning/10",
    borderColor: "border-warning/20",
  },
  running: {
    label: "运行中",
    icon: Loader2,
    color: "text-tertiary",
    bgColor: "bg-tertiary/10",
    borderColor: "border-tertiary/20",
    animate: true,
  },
  completed: {
    label: "已完成",
    icon: CheckCircle2,
    color: "text-success",
    bgColor: "bg-success/10",
    borderColor: "border-success/20",
  },
  failed: {
    label: "失败",
    icon: AlertCircle,
    color: "text-error",
    bgColor: "bg-error/10",
    borderColor: "border-error/20",
  },
  cancelled: {
    label: "已取消",
    icon: Ban,
    color: "text-muted-foreground",
    bgColor: "bg-muted/10",
    borderColor: "border-border/20",
  },
};

export function SubAgentTaskCard({
  task,
  isSelected,
  onSelect,
  onCancel,
  onRetry,
}: SubAgentTaskCardProps) {
  const [isOpen, setIsOpen] = useState(false);
  const config = statusConfig[task.status];
  const StatusIcon = config.icon;

  const formatDuration = () => {
    if (!task.startTime) return "--";
    const end = task.endTime || new Date();
    const diff = Math.floor((end.getTime() - task.startTime.getTime()) / 1000);
    if (diff < 60) return `${diff}s`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ${diff % 60}s`;
    return `${Math.floor(diff / 3600)}h ${Math.floor((diff % 3600) / 60)}m`;
  };

  return (
    <div
      className={cn(
        "rounded-lg border transition-all",
        config.borderColor,
        isSelected && "ring-2 ring-primary",
        "hover:shadow-sm"
      )}
    >
      {/* 任务头部 */}
      <div
        className={cn(
          "p-3 flex items-center gap-3 cursor-pointer",
          config.bgColor
        )}
        onClick={() => onSelect?.(task.id)}
      >
        {/* 状态图标 */}
        <StatusIcon
          className={cn(
            "w-4 h-4 flex-shrink-0",
            config.color,
            config.animate && "animate-spin"
          )}
        />

        {/* 任务信息 */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">{task.title}</span>
            <Badge variant="outline" className={cn("text-[10px] h-4", config.color)}>
              {config.label}
            </Badge>
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {task.status === "running" && task.progress !== undefined && (
              <span>{task.progress}% · </span>
            )}
            <span>耗时: {formatDuration()}</span>
          </div>
        </div>

        {/* 操作按钮 */}
        <div className="flex items-center gap-1">
          {task.status === "running" && onCancel && (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={(e) => {
                e.stopPropagation();
                onCancel(task.id);
              }}
            >
              <Ban className="w-3 h-3" />
            </Button>
          )}
          {task.status === "failed" && onRetry && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-xs"
              onClick={(e) => {
                e.stopPropagation();
                onRetry(task.id);
              }}
            >
              重试
            </Button>
          )}

          {/* 展开/折叠 */}
          {(task.output || task.error) && (
            <Collapsible open={isOpen} onOpenChange={setIsOpen}>
              <CollapsibleTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6"
                  onClick={(e) => e.stopPropagation()}
                >
                  {isOpen ? (
                    <ChevronDown className="w-3 h-3" />
                  ) : (
                    <ChevronRight className="w-3 h-3" />
                  )}
                </Button>
              </CollapsibleTrigger>
            </Collapsible>
          )}
        </div>
      </div>

      {/* 进度条 */}
      {task.status === "running" && task.progress !== undefined && (
        <div className="px-3 pb-2">
          <div className="h-1 bg-secondary rounded-full overflow-hidden">
            <div
              className={cn("h-full transition-all", config.color.replace("text-", "bg-"))}
              style={{ width: `${task.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* 展开内容 */}
      {(task.output || task.error) && (
        <Collapsible open={isOpen} onOpenChange={setIsOpen}>
          <CollapsibleContent>
            <div className="px-3 pb-3">
              {task.output && (
                <div className="bg-background rounded border p-2 text-xs font-mono whitespace-pre-wrap max-h-32 overflow-auto">
                  <div className="flex items-center gap-1 text-muted-foreground mb-1">
                    <Terminal className="w-3 h-3" />
                    <span>输出</span>
                  </div>
                  {task.output}
                </div>
              )}
              {task.error && (
                <div className="bg-error-container rounded border border-error/20 p-2 text-xs text-error mt-2">
                  <div className="flex items-center gap-1 mb-1">
                    <AlertCircle className="w-3 h-3" />
                    <span>错误</span>
                  </div>
                  {task.error}
                </div>
              )}
            </div>
          </CollapsibleContent>
        </Collapsible>
      )}
    </div>
  );
}
