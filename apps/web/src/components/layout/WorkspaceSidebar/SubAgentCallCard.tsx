/**
 * SubAgentCallCard - 协作节点卡片组件
 *
 * 包含 HostNodeCard、SubAgentCallCard、NestedSubAgentCallView
 * 以及相关的工具函数和类型。
 */

import { useState } from "react";
import {
  Bot,
  Play,
  CheckCircle2,
  XCircle,
  Clock,
  Pause,
  ChevronRight,
  Terminal,
  Pin,
  PinOff,
  ExternalLink,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import {
  Collapsible,
  CollapsibleContent,
} from "@/components/ui/collapsible";
import type { ExecutionTree, SubAgentDetail } from "@/hooks/useExecutionTree";

export type SubAgentCallItem = ExecutionTree["subagent_calls"][0];

export interface NestedSubAgentCall {
  call: SubAgentCallItem;
  children: NestedSubAgentCall[];
}

interface StatusIconConfig {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  bgColor: string;
  dotColor: string;
  animate?: boolean;
}

export const statusConfig: Record<string, StatusIconConfig> = {
  idle: { label: "空闲", icon: Bot, color: "text-muted-foreground", bgColor: "bg-muted/10", dotColor: "bg-muted-foreground" },
  running: { label: "运行中", icon: Play, color: "text-tertiary", bgColor: "bg-tertiary/10", dotColor: "bg-tertiary", animate: true },
  completed: { label: "已完成", icon: CheckCircle2, color: "text-success", bgColor: "bg-success/10", dotColor: "bg-success" },
  failed: { label: "失败", icon: XCircle, color: "text-error", bgColor: "bg-error/10", dotColor: "bg-error" },
  cancelled: { label: "已取消", icon: Pause, color: "text-warning", bgColor: "bg-warning-container0/10", dotColor: "bg-warning" },
  queued: { label: "排队中", icon: Clock, color: "text-warning", bgColor: "bg-warning/10", dotColor: "bg-warning" },
};

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  return `${Math.floor(ms / 3600000)}h ${Math.floor((ms % 3600000) / 60000)}m`;
}

export function formatShortId(value?: string | null): string {
  if (!value) return "未记录";
  return value.length <= 16 ? value : `${value.slice(0, 8)}...${value.slice(-4)}`;
}

export function getNodeRoleLabel(call: SubAgentCallItem["subagent"]): string {
  if (call.hosting_controller || call.node_role === "hosting_controller") {
    return "托管控制";
  }
  return "协作节点";
}

export function getExpertRoleLabel(
  subagent: SubAgentCallItem["subagent"],
): string | null {
  return subagent.role_summary?.display_name || subagent.subagent_type || null;
}

export function buildNestedSubAgentCalls(calls: SubAgentCallItem[]): NestedSubAgentCall[] {
  const nodeByAgentId = new Map<string, NestedSubAgentCall>();
  const roots: NestedSubAgentCall[] = [];

  calls.forEach((call) => {
    nodeByAgentId.set(call.subagent.id, { call, children: [] });
  });

  calls.forEach((call) => {
    const node = nodeByAgentId.get(call.subagent.id);
    if (!node) return;

    const parentAgentId = call.subagent.parent_agent_id?.trim();
    const parent = parentAgentId ? nodeByAgentId.get(parentAgentId) : null;
    if (parent && parent.call.subagent.id !== call.subagent.id) {
      parent.children.push(node);
      return;
    }

    roots.push(node);
  });

  return roots;
}

export function HostNodeCard({ host }: { host: ExecutionTree["host"] }) {
  const config = statusConfig[host.status] || statusConfig.idle;
  const StatusIcon = config.icon;

  const hasSteps = host.total_steps > 0 && host.current_step > 0;
  const progress = hasSteps
    ? (host.current_step / host.total_steps) * 100
    : host.status === "running" ? 50 : 0;

  let stepText = "";
  if (hasSteps) {
    stepText = `Step ${host.current_step} / ${host.total_steps}`;
  } else if (host.status === "running") {
    stepText = "执行中";
  } else if (host.status === "completed") {
    stepText = "已完成";
  } else {
    stepText = "就绪";
  }

  return (
    <div className="px-2 py-2 border-b border-border/50">
      <div className="flex items-center gap-2">
        <div className={cn(
          "w-5 h-5 rounded flex items-center justify-center shrink-0",
          config.bgColor
        )}>
          <StatusIcon className={cn("w-2.5 h-2.5", config.color, config.animate && "animate-pulse")} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5">
            <span className="text-sm font-medium">当前会话</span>
            <span className={cn("text-[10px] font-medium", config.color)}>{config.label}</span>
          </div>
          <div className="text-[10px] text-muted-foreground/70 mt-0.5">
            {stepText}
          </div>
        </div>
      </div>
      {(host.status === "running" || hasSteps) && (
        <div className="mt-1.5 ml-7">
          <Progress value={progress} className="h-0.5" />
        </div>
      )}
    </div>
  );
}

export function SubAgentCallCard({
  call,
  level: _level,
  childCount,
  isSelected,
  isPinned,
  onSelect,
  onStop,
  onRetry,
  onTaskClick,
  onTogglePin,
  onOpenInMainCanvas,
  allowStopActions = false,
}: {
  call: SubAgentCallItem;
  level: number;
  childCount: number;
  isSelected: boolean;
  isPinned: boolean;
  onSelect: () => void;
  onStop: () => void;
  onRetry?: () => void;
  onTaskClick?: (toolCallId: string) => void;
  onTogglePin?: (agentId: string) => void;
  onOpenInMainCanvas?: (subagentId: string) => void;
  allowStopActions?: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const { subagent, step_number, tool_call_id } = call;
  const config = statusConfig[subagent.status] || statusConfig.idle;
  const StatusIcon = config.icon;

  const progress = subagent.progress.total_steps > 0
    ? (subagent.progress.current_step / subagent.progress.total_steps) * 100
    : 0;
  const stepText = subagent.progress.total_steps > 0
    ? `${subagent.progress.current_step}/${subagent.progress.total_steps}`
    : null;
  const expertRoleLabel = getExpertRoleLabel(subagent);
  const parentToolCallId = subagent.parent_tool_call_id || tool_call_id;
  const displayName = subagent.nickname || subagent.name;
  const hasChildren = childCount > 0;

  return (
    <div
      className={cn(
        "group relative px-2 py-2 transition-colors cursor-pointer border-b border-border/50 last:border-b-0",
        isSelected ? "bg-primary/[0.03]" : "hover:bg-muted/30"
      )}
      onClick={() => {
        onSelect();
        if (onTaskClick && tool_call_id) {
          onTaskClick(tool_call_id);
        }
      }}
    >
      {/* 主行：展开箭头 + 状态 + 名称/角色 + 操作 */}
      <div className="flex items-center gap-1.5">
        {/* 展开箭头 */}
        <button
          type="button"
          className="shrink-0 p-0.5 rounded hover:bg-muted text-muted-foreground/50 hover:text-muted-foreground transition-colors"
          onClick={(e) => {
            e.stopPropagation();
            setIsExpanded(!isExpanded);
          }}
        >
          <ChevronRight className={cn(
            "w-3.5 h-3.5 transition-transform",
            isExpanded && "rotate-90"
          )} />
        </button>

        {/* 状态圆点 + 图标 */}
        <div className={cn(
          "shrink-0 w-5 h-5 rounded flex items-center justify-center",
          config.bgColor
        )}>
          <StatusIcon className={cn("w-2.5 h-2.5", config.color, config.animate && "animate-pulse")} />
        </div>

        {/* 名称与元信息 */}
        <div className="min-w-0 flex-1 overflow-hidden">
          <div className="flex items-center gap-1.5 min-w-0">
            <span className="text-sm font-medium truncate">{displayName}</span>
            {hasChildren ? (
              <span className="shrink-0 text-[10px] text-muted-foreground/50">
                {childCount}
              </span>
            ) : null}
          </div>
          {/* 紧凑元信息行，确保不换行 */}
          <div className="flex items-center gap-x-1.5 text-[10px] text-muted-foreground/70 mt-0.5 whitespace-nowrap">
            <span className={cn("font-medium shrink-0", config.color)}>{config.label}</span>
            <span className="text-border shrink-0">·</span>
            <span className="shrink-0">Step {step_number}</span>
            {subagent.duration_ms > 0 ? (
              <>
                <span className="text-border shrink-0">·</span>
                <span className="shrink-0">{formatDuration(subagent.duration_ms)}</span>
              </>
            ) : null}
            {subagent.progress.tool_calls > 0 ? (
              <>
                <span className="text-border shrink-0">·</span>
                <span className="flex items-center gap-0.5 shrink-0">
                  <Terminal className="w-2.5 h-2.5" />
                  {subagent.progress.tool_calls}
                </span>
              </>
            ) : null}
            {expertRoleLabel ? (
              <>
                <span className="text-border shrink-0">·</span>
                <span className="truncate">{expertRoleLabel}</span>
              </>
            ) : null}
          </div>
        </div>

        {/* 操作按钮（hover 或 pinned 时显示） */}
        <div className="flex items-center gap-0 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          {onOpenInMainCanvas ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-muted-foreground/50 hover:text-muted-foreground"
              onClick={(e) => {
                e.stopPropagation();
                onOpenInMainCanvas(subagent.id);
              }}
              title="在主画布打开"
            >
              <ExternalLink className="w-3 h-3" />
            </Button>
          ) : null}
          {onTogglePin ? (
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                "h-6 w-6",
                isPinned
                  ? "text-tertiary opacity-100"
                  : "text-muted-foreground/50 hover:text-muted-foreground",
              )}
              onClick={(e) => {
                e.stopPropagation();
                onTogglePin(subagent.id);
              }}
              title={isPinned ? "取消固定" : "固定到标签页"}
            >
              {isPinned ? <PinOff className="w-3 h-3" /> : <Pin className="w-3 h-3" />}
            </Button>
          ) : null}
          {allowStopActions && subagent.status === "running" ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-warning hover:text-warning shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                onStop();
              }}
            >
              <Pause className="w-3 h-3" />
            </Button>
          ) : null}
          {allowStopActions && onRetry && (subagent.status === "failed" || subagent.status === "cancelled") ? (
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 text-primary hover:text-primary shrink-0"
              onClick={(e) => {
                e.stopPropagation();
                onRetry();
              }}
            >
              <Play className="w-3 h-3" />
            </Button>
          ) : null}
        </div>
      </div>

      {/* 进度条（仅运行中/有步骤时） */}
      {(subagent.status === "running" || progress > 0) && (
        <div className="mt-1.5 ml-[52px] flex items-center gap-2">
          <Progress value={progress} className="h-0.5 flex-1" />
          {stepText ? (
            <span className="text-[10px] text-muted-foreground/60 whitespace-nowrap shrink-0">
              {stepText}
            </span>
          ) : null}
        </div>
      )}

      {/* 展开详情 */}
      <Collapsible open={isExpanded} onOpenChange={setIsExpanded}>
        <CollapsibleContent>
          <div className="mt-2 pt-2 border-t border-border/30 ml-[52px] space-y-2">
            {/* 角色配置 */}
            {subagent.role_summary ? (
              <div className="rounded-md border border-border/60 bg-muted/20 px-2.5 py-2">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] font-medium text-foreground">
                    {subagent.role_summary.display_name}
                  </span>
                  <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                    {subagent.role_summary.role_id}
                  </Badge>
                  {subagent.role_summary.tool_policy ? (
                    <Badge
                      variant={
                        subagent.role_summary.tool_policy === "inherit"
                          ? "outline"
                          : "secondary"
                      }
                      className="text-[9px] px-1 py-0 h-4"
                    >
                      {subagent.role_summary.tool_policy === "inherit"
                        ? "继承模式"
                        : "白名单模式"}
                    </Badge>
                  ) : null}
                  {subagent.role_summary.supports_background ? (
                    <Badge variant="outline" className="text-[9px] px-1 py-0 h-4">
                      可后台
                    </Badge>
                  ) : null}
                </div>
                {subagent.role_summary.description ? (
                  <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">
                    {subagent.role_summary.description}
                  </p>
                ) : null}
                {subagent.role_summary.when_to_use ? (
                  <p className="mt-1 text-[10px] text-muted-foreground leading-relaxed">
                    建议：{subagent.role_summary.when_to_use}
                  </p>
                ) : null}
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {subagent.role_summary.capabilities.map((capability) => (
                    <Badge key={capability} variant="outline" className="text-[9px] px-1 py-0 h-4">
                      {capability}
                    </Badge>
                  ))}
                  {subagent.role_summary.permissions.map((permission) => (
                    <Badge key={permission} variant="secondary" className="text-[9px] px-1 py-0 h-4">
                      {permission}
                    </Badge>
                  ))}
                </div>
              </div>
            ) : null}

            {/* 实例元数据 */}
            <div className="text-[10px] text-muted-foreground/70 space-y-0.5">
              <div>ID: <code className="bg-muted/50 px-1 rounded text-[9px]">{subagent.id.slice(0, 8)}...</code></div>
              <div>主控会话: <code className="bg-muted/50 px-1 rounded text-[9px]">{formatShortId(subagent.host_session_id)}</code></div>
              {subagent.parent_agent_id ? (
                <div>父节点: <code className="bg-muted/50 px-1 rounded text-[9px]">{formatShortId(subagent.parent_agent_id)}</code></div>
              ) : null}
              {parentToolCallId ? (
                <div>父调用: <code className="bg-muted/50 px-1 rounded text-[9px]">{formatShortId(parentToolCallId)}</code></div>
              ) : null}
              {subagent.agent_path ? (
                <div>路径: <code className="bg-muted/50 px-1 rounded text-[9px]">{subagent.agent_path}</code></div>
              ) : null}
              <div className="flex gap-3">
                <span>创建于 {new Date(subagent.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

export function NestedSubAgentCallView({
  node,
  level,
  selectedSubAgent,
  pinnedSubAgentIds,
  onSelect,
  onStop,
  onRetry,
  onTaskClick,
  onTogglePin,
  allowStopActions,
}: {
  node: NestedSubAgentCall;
  level: number;
  selectedSubAgent: SubAgentDetail | null;
  pinnedSubAgentIds: Set<string>;
  onSelect: (agentId: string) => void;
  onStop: (agentId: string) => Promise<void>;
  onRetry: (agentId: string) => Promise<void>;
  onTaskClick?: (toolCallId: string) => void;
  onTogglePin?: (agentId: string) => void;
  allowStopActions: boolean;
}) {
  const agentId = node.call.subagent.id;
  return (
    <div className={cn(level > 0 && "ml-4 border-l border-border/70 pl-3")}>
      <SubAgentCallCard
        call={node.call}
        level={level}
        childCount={node.children.length}
        isSelected={selectedSubAgent?.id === agentId}
        isPinned={pinnedSubAgentIds.has(agentId)}
        onSelect={() => onSelect(agentId)}
        onStop={() => onStop(agentId)}
        onRetry={onRetry ? () => onRetry(agentId) : undefined}
        onTaskClick={onTaskClick}
        onTogglePin={onTogglePin}
        allowStopActions={allowStopActions}
      />
      {node.children.length > 0 ? (
        <div className="mt-2 space-y-2">
          {node.children.map((child) => (
            <NestedSubAgentCallView
              key={child.call.subagent.id}
              node={child}
              level={level + 1}
              selectedSubAgent={selectedSubAgent}
              pinnedSubAgentIds={pinnedSubAgentIds}
              onSelect={onSelect}
              onStop={onStop}
              onRetry={onRetry}
              onTaskClick={onTaskClick}
              onTogglePin={onTogglePin}
              allowStopActions={allowStopActions}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
