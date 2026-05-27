/**
 * SubAgentTreeOverview - 协作节点树形概览
 *
 * 显示当前会话和所有协作节点的执行状态卡片
 * 点击节点在主画布 Tab 中打开详情
 */

import type { ExecutionTree, SubAgentDetail } from "@/hooks/useExecutionTree";
import {
  buildNestedSubAgentCalls,
  HostNodeCard,
  NestedSubAgentCallView,
} from "./SubAgentCallCard";

interface SubAgentTreeOverviewProps {
  executionTree: ExecutionTree | null;
  selectedSubAgent: SubAgentDetail | null;
  isLoadingSubAgent: boolean;
  onSelectSubAgent: (agentId: string | null) => void;
  onStopSubAgent: (agentId: string) => Promise<boolean>;
  onRetrySubAgent: (agentId: string) => Promise<boolean>;
  onSubAgentTaskClick?: (toolCallId: string) => void;
  onTogglePin?: (agentId: string) => void;
  pinnedSubAgentIds?: Set<string>;
  userId?: string;
  sessionId?: string;
  allowStopActions?: boolean;
  allowRetryActions?: boolean;
  onOpenInMainCanvas?: (subagentId: string) => void;
}

export function SubAgentTreeOverview({
  executionTree,
  selectedSubAgent,
  onSelectSubAgent,
  onStopSubAgent,
  onRetrySubAgent,
  onSubAgentTaskClick,
  onTogglePin,
  pinnedSubAgentIds = new Set(),
  allowStopActions = false,
  onOpenInMainCanvas,
}: SubAgentTreeOverviewProps) {
  const nestedCalls = executionTree
    ? buildNestedSubAgentCalls(executionTree.subagent_calls)
    : [];
  if (!executionTree) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        暂无执行数据
      </div>
    );
  }

  const handleSelectSubAgent = (agentId: string) => {
    if (onOpenInMainCanvas) {
      onOpenInMainCanvas(agentId);
      return;
    }
    onSelectSubAgent(agentId);
  };

  return (
    <div className="divide-y divide-border/50 rounded-lg border border-border/60 bg-background overflow-hidden">
      <HostNodeCard host={executionTree.host} />

      {executionTree.subagent_calls.length > 0 ? (
        <div>
          {nestedCalls.map((node) => (
            <NestedSubAgentCallView
              key={node.call.subagent.id}
              node={node}
              level={0}
              selectedSubAgent={selectedSubAgent}
              pinnedSubAgentIds={pinnedSubAgentIds}
              onSelect={handleSelectSubAgent}
              onStop={async (agentId) => {
                await onStopSubAgent(agentId);
              }}
              onRetry={async (agentId) => {
                await onRetrySubAgent(agentId);
              }}
              onTaskClick={onSubAgentTaskClick}
              onTogglePin={onTogglePin}
              allowStopActions={allowStopActions}
            />
          ))}
        </div>
      ) : executionTree.host.status === "running" ? (
        <div className="text-center py-4 text-[11px] text-muted-foreground">
          当前会话正在处理；如有协作节点，会显示在这里。
        </div>
      ) : null}
    </div>
  );
}
