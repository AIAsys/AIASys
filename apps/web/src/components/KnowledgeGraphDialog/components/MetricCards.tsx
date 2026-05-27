import { MetricCard, formatGraphNumber } from "../shared";
import type { GraphVisualizationResponse } from "@/types/graphrag";

interface MetricCardsProps {
  activeGraph: GraphVisualizationResponse | null;
  activeView: "overview" | "query";
  totalCommunities: number;
  communitiesCount: number;
  llmStatus: { extractor_available: boolean; reporter_available: boolean } | null;
  healthLlmStatus?: string;
  statsLlmStatus?: string;
  currentGraphId?: string;
}

export function MetricCards({
  activeGraph,
  activeView,
  totalCommunities,
  communitiesCount,
  llmStatus,
  healthLlmStatus,
  statsLlmStatus,
  currentGraphId,
}: MetricCardsProps) {
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      <MetricCard
        label="当前图节点"
        value={formatGraphNumber(activeGraph?.nodes.length)}
        helper={
          activeView === "query"
            ? "当前问答子图中的节点数量"
            : "总览图当前可见节点"
        }
      />
      <MetricCard
        label="当前图边"
        value={formatGraphNumber(activeGraph?.edges.length)}
        helper={
          activeView === "query"
            ? "当前问答子图中的边数量"
            : "总览图当前可见关系"
        }
      />
      <MetricCard
        label="社区数"
        value={formatGraphNumber(totalCommunities)}
        helper={
          totalCommunities > 0
            ? `L0 摘要 ${formatGraphNumber(communitiesCount)} 个`
            : "尚未检测到社区结构"
        }
      />
      <MetricCard
        label="LLM 状态"
        value={healthLlmStatus || statsLlmStatus || "--"}
        helper={
          llmStatus
            ? `当前图谱 ${currentGraphId || "--"} / 抽取器 ${llmStatus.extractor_available ? "已就绪" : "未就绪"} / 报告器 ${llmStatus.reporter_available ? "已就绪" : "未就绪"}`
            : `当前图谱 ${currentGraphId || "--"} / 用于抽取和社区报告生成`
        }
      />
    </div>
  );
}
