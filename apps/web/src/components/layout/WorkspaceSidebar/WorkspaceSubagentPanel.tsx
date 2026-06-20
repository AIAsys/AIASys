import { useEffect, useRef, useState } from "react";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Loader2,
  Workflow,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import type {
  ExecutionTree,
  SubAgentDetail,
  SubAgentSummary,
} from "@/hooks/useExecutionTree";
import { AgentExecutionView } from "./AgentExecutionView";
import { SubAgentTreeOverview } from "./SubAgentTreeOverview";

interface WorkspaceSubagentPanelProps {
  executionTree: ExecutionTree | null;
  selectedSubAgent: SubAgentDetail | null;
  isLoadingTree: boolean;
  isLoadingSubAgent: boolean;
  onSelectSubAgent: (agentId: string | null) => void;
  onStopSubAgent: (agentId: string) => Promise<boolean>;
  onRetrySubAgent: (agentId: string) => Promise<boolean>;
  onTogglePin?: (agentId: string) => void;
  pinnedSubAgentIds?: Set<string>;
  userId?: string;
  sessionId?: string;
  onOpenInMainCanvas?: (subagentId: string) => void;
  /** 是否在窄 sidebar 中以紧凑模式渲染 */
  compact?: boolean;
}

function getHostStatusLabel(status?: string | null): string {
  switch (status) {
    case "idle":
      return "空闲";
    case "running":
      return "运行中";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    case "queued":
      return "排队中";
    default:
      return "待启动";
  }
}

function SubagentMetricBar({
  items,
}: {
  items: { label: string; value: React.ReactNode; color?: string }[];
}) {
  return (
    <div className="flex items-center gap-1 flex-wrap">
      {items.map((item, i) => (
        <div key={item.label} className="flex items-center gap-1 text-[11px]">
          {i > 0 && <span className="text-muted-foreground/30 mx-1">|</span>}
          <span className="text-muted-foreground/60">{item.label}</span>
          <span className={cn("font-semibold tabular-nums", item.color || "text-foreground")}>{item.value}</span>
        </div>
      ))}
    </div>
  );
}

function SubagentSectionCard({
  title,
  description,
  children,
  compact,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <section className={cn("rounded-xl", compact ? "px-0 py-0" : "px-4 py-4")}>
      {!compact && (
        <div className="mb-3">
          <div className="font-semibold tracking-tight text-foreground text-[18px]">
            {title}
          </div>
          {description && <p className="text-sm text-muted-foreground mt-2 leading-6">{description}</p>}
        </div>
      )}
      <div className="flex flex-col gap-2">{children}</div>
    </section>
  );
}

function SubagentInfoRow({
  icon,
  label,
  value,
  description,
  compact,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  description: string;
  compact?: boolean;
}) {
  return (
    <div className={cn("border border-border bg-background px-3 py-3", compact ? "rounded-xl" : "rounded-2xl")}>
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-2 text-[15px] font-semibold text-foreground">{value}</div>
      <div className="mt-1 text-[11px] leading-5 text-muted-foreground">
        {description}
      </div>
    </div>
  );
}

export function WorkspaceSubagentPanel({
  executionTree,
  selectedSubAgent,
  isLoadingTree,
  isLoadingSubAgent,
  onSelectSubAgent,
  onStopSubAgent,
  onRetrySubAgent,
  onTogglePin,
  pinnedSubAgentIds = new Set(),
  userId,
  sessionId,
  onOpenInMainCanvas,
  compact = false,
}: WorkspaceSubagentPanelProps) {
  const [isDetailExpanded, setIsDetailExpanded] = useState(false);
  const previousSelectedIdRef = useRef<string | null>(null);

  useEffect(() => {
    const currentId = selectedSubAgent?.id ?? null;
    if (currentId && currentId !== previousSelectedIdRef.current) {
      setIsDetailExpanded(true);
    }
    previousSelectedIdRef.current = currentId;
  }, [selectedSubAgent]);

  const subagentCalls = executionTree?.subagent_calls ?? [];
  const subagentById = new Map(subagentCalls.map((c) => [c.subagent.id, c.subagent]));
  const pinnedList = Array.from(pinnedSubAgentIds)
    .map((id) => subagentById.get(id))
    .filter((sa): sa is SubAgentSummary => Boolean(sa));
  const runningCount = subagentCalls.filter(
    (call) => call.subagent.status === "running" || call.subagent.status === "queued",
  ).length;
  const completedCount = subagentCalls.filter(
    (call) => call.subagent.status === "completed",
  ).length;
  const queuedCount = subagentCalls.filter(
    (call) => call.subagent.status === "queued",
  ).length;
  const abnormalCount = subagentCalls.filter(
    (call) =>
      call.subagent.status === "failed" || call.subagent.status === "cancelled",
  ).length;
  const latestUpdatedAt = subagentCalls
    .map((call) => call.subagent.updated_at)
    .filter(Boolean)
    .sort()
    .at(-1);

  return (
    <div className={cn("min-h-0 h-full overflow-y-auto overscroll-contain pb-6 pt-2", compact ? "px-3" : "px-5")}>
      <div className={cn("flex w-full flex-col gap-4 rounded-2xl border border-border bg-background shadow-sm", compact ? "px-3 py-4" : "px-5 py-5")}>
        <div>
          <div className="flex items-center justify-between">
            <h2 className={cn("font-semibold tracking-tight text-foreground", compact ? "text-xl" : "text-3xl")}>
              专家协作节点
            </h2>
            {!compact && (
              <Badge
                variant="outline"
                className="shrink-0 rounded-full border-primary/20 bg-primary/10 px-3 py-1 text-[11px] text-primary"
              >
                当前视图：专家协作节点
              </Badge>
            )}
          </div>

          <div className="mt-3">
            <SubagentMetricBar
              items={[
                { label: "总数", value: subagentCalls.length },
                { label: "运行中", value: runningCount, color: runningCount > 0 ? "text-tertiary" : undefined },
                { label: "排队", value: queuedCount, color: queuedCount > 0 ? "text-warning" : undefined },
                { label: abnormalCount > 0 ? "异常" : "已完成", value: abnormalCount > 0 ? abnormalCount : completedCount, color: abnormalCount > 0 ? "text-error" : undefined },
              ]}
            />
          </div>

          {pinnedList.length > 0 && (
            <div className="mt-4 flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] font-medium text-muted-foreground mr-1">
                已固定:
              </span>
              {pinnedList.map((sa) => (
                <button
                  key={sa.id}
                  type="button"
                  className={cn(
                    "inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11px] transition-colors",
                    selectedSubAgent?.id === sa.id
                      ? "border-tertiary/40 bg-tertiary/10 text-tertiary"
                      : "border-border bg-muted/40 text-muted-foreground hover:border-tertiary/20 hover:bg-tertiary/5",
                  )}
                  onClick={() => onSelectSubAgent(sa.id)}
                >
                  <Bot className="h-3 w-3 shrink-0" />
                  <span className="max-w-[120px] truncate">
                    {sa.nickname || sa.name || sa.id.slice(0, 8)}
                  </span>
                  <span
                    className="ml-0.5 inline-flex cursor-pointer rounded-full p-0.5 hover:bg-muted"
                    onClick={(e) => {
                      e.stopPropagation();
                      onTogglePin?.(sa.id);
                    }}
                  >
                    <X className="h-2.5 w-2.5" />
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className={cn("grid gap-4", compact ? "grid-cols-1" : "xl:grid-cols-[minmax(0,1fr)_280px]")}>
          <div>
            {isLoadingTree && !executionTree ? (
              <div className={cn("flex items-center justify-center gap-2 rounded-xl border border-dashed border-border bg-background text-sm text-muted-foreground", compact ? "min-h-[80px]" : "min-h-[200px]")}>
                <Loader2 className="h-4 w-4 animate-spin" />
                正在读取专家协作节点状态...
              </div>
            ) : subagentCalls.length === 0 ? (
              <div className={cn("flex items-center justify-center text-center rounded-lg border border-border/60 bg-background", compact ? "min-h-[80px] px-3 py-4" : "min-h-[200px] px-6 py-8")}>
                <div className="text-center">
                  <Clock3 className={cn("mx-auto text-muted-foreground", compact ? "h-4 w-4" : "h-5 w-5")} />
                  <div className={cn("font-medium text-foreground mt-2", compact ? "text-xs" : "text-sm")}>
                    暂无专家协作节点
                  </div>
                  <div className={cn("mt-1 leading-5 text-muted-foreground", compact ? "text-[10px]" : "text-xs")}>
                    主控派发任务后自动显示
                  </div>
                </div>
              </div>
            ) : (
              <div className="min-h-0">
                <SubAgentTreeOverview
                  executionTree={executionTree}
                  selectedSubAgent={selectedSubAgent}
                  isLoadingSubAgent={isLoadingSubAgent}
                  onSelectSubAgent={onSelectSubAgent}
                  onStopSubAgent={onStopSubAgent}
                  onRetrySubAgent={onRetrySubAgent}
                  onTogglePin={onTogglePin}
                  pinnedSubAgentIds={pinnedSubAgentIds}
                  userId={userId}
                  sessionId={sessionId}
                  allowStopActions={false}
                  allowRetryActions={false}
                  onOpenInMainCanvas={onOpenInMainCanvas}
                  compact={compact}
                />
              </div>
            )}
          </div>

          {compact && subagentCalls.length > 0 && (
            <Collapsible open={isDetailExpanded} onOpenChange={setIsDetailExpanded}>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="flex w-full items-center justify-between rounded-xl border border-border bg-background px-3 py-2 text-left text-sm font-medium text-foreground transition-colors hover:bg-muted/30"
                >
                  <span>
                    {selectedSubAgent
                      ? `节点详情：${selectedSubAgent.nickname || selectedSubAgent.name || selectedSubAgent.id.slice(0, 8)}`
                      : "节点详情"}
                  </span>
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 text-muted-foreground transition-transform",
                      isDetailExpanded && "rotate-180",
                    )}
                  />
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="mt-3 flex flex-col gap-4">
                  <AgentExecutionView
                    subagent={selectedSubAgent}
                    isLoading={isLoadingSubAgent}
                    className="px-3 py-3"
                  />

                  <SubagentSectionCard
                    title="当前会话状态"
                    description=""
                    compact={compact}
                  >
                    <SubagentInfoRow
                      icon={<Workflow className="h-3.5 w-3.5" />}
                      label="当前会话"
                      value={getHostStatusLabel(executionTree?.host.status)}
                      description=""
                      compact={compact}
                    />
                    <SubagentInfoRow
                      icon={<Clock3 className="h-3.5 w-3.5" />}
                      label="最近更新"
                      value={
                        latestUpdatedAt
                          ? new Date(latestUpdatedAt).toLocaleString("zh-CN", {
                              hour12: false,
                            })
                          : "暂无"
                      }
                      description=""
                      compact={compact}
                    />
                  </SubagentSectionCard>

                  <SubagentSectionCard
                    title="推进链路"
                    description=""
                    compact={compact}
                  >
                    <SubagentInfoRow
                      icon={<Workflow className="h-3.5 w-3.5" />}
                      label="1"
                      value="主控拆分任务"
                      description=""
                      compact={compact}
                    />
                    <SubagentInfoRow
                      icon={<Bot className="h-3.5 w-3.5" />}
                      label="2"
                      value="节点独立执行"
                      description=""
                      compact={compact}
                    />
                    <SubagentInfoRow
                      icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                      label="3"
                      value="结果回流主会话"
                      description=""
                      compact={compact}
                    />
                  </SubagentSectionCard>
                </div>
              </CollapsibleContent>
            </Collapsible>
          )}

          {!compact && (
            <div className="flex flex-col gap-4">
              <AgentExecutionView
                subagent={selectedSubAgent}
                isLoading={isLoadingSubAgent}
              />

              <SubagentSectionCard
                title="当前会话状态"
                description=""
                compact={compact}
              >
                <SubagentInfoRow
                  icon={<Workflow className="h-3.5 w-3.5" />}
                  label="当前会话"
                  value={getHostStatusLabel(executionTree?.host.status)}
                  description=""
                  compact={compact}
                />
                <SubagentInfoRow
                  icon={<Clock3 className="h-3.5 w-3.5" />}
                  label="最近更新"
                  value={
                    latestUpdatedAt
                      ? new Date(latestUpdatedAt).toLocaleString("zh-CN", {
                          hour12: false,
                        })
                      : "暂无"
                  }
                  description=""
                  compact={compact}
                />
              </SubagentSectionCard>

              <SubagentSectionCard
                title="推进链路"
                description=""
                compact={compact}
              >
                <SubagentInfoRow
                  icon={<Workflow className="h-3.5 w-3.5" />}
                  label="1"
                  value="主控拆分任务"
                  description=""
                  compact={compact}
                />
                <SubagentInfoRow
                  icon={<Bot className="h-3.5 w-3.5" />}
                  label="2"
                  value="节点独立执行"
                  description=""
                  compact={compact}
                />
                <SubagentInfoRow
                  icon={<CheckCircle2 className="h-3.5 w-3.5" />}
                  label="3"
                  value="结果回流主会话"
                  description=""
                  compact={compact}
                />
            </SubagentSectionCard>
          </div>
        )}
        </div>
      </div>
    </div>
  );
}

export default WorkspaceSubagentPanel;
