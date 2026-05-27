import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { createGraphragApi } from "@/lib/api/graphrag";
import type {
  GraphCommunitySummary,
  GraphHealth,
  GraphStatistics,
} from "@/types/graphrag";
import {
  EmptyState,
  MetricCard,
  formatGraphNumber,
  getEntityTypeLabel,
  normalizeDisplayText,
} from "@/pages/Knowledge/GraphPage/shared";

interface CommunityAnalysisPanelProps {
  workspaceId?: string | null;
  graphId?: string | null;
  onOpenWorkbench?: () => void;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return fallback;
}

export function CommunityAnalysisPanel({
  workspaceId = null,
  graphId = null,
  onOpenWorkbench,
}: CommunityAnalysisPanelProps) {
  const graphragApi = useMemo(
    () => createGraphragApi({ workspaceId, graphId }),
    [graphId, workspaceId],
  );
  const [level, setLevel] = useState("0");
  const [communities, setCommunities] = useState<GraphCommunitySummary[]>([]);
  const [reports, setReports] = useState<Record<string, string>>({});
  const [stats, setStats] = useState<GraphStatistics | null>(null);
  const [health, setHealth] = useState<GraphHealth | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isGeneratingReports, setIsGeneratingReports] = useState(false);
  const [pageError, setPageError] = useState<string | null>(null);
  const [reportError, setReportError] = useState<string | null>(null);

  async function loadCommunityData(silent = false) {
    if (silent) {
      setIsRefreshing(true);
    } else {
      setIsLoading(true);
    }
    setPageError(null);

    try {
      const numericLevel = Number.parseInt(level, 10) || 0;
      const [nextCommunities, nextStats, nextHealth] = await Promise.all([
        graphragApi.listCommunities(numericLevel),
        graphragApi.getStatistics(),
        graphragApi.getHealth(),
      ]);
      setCommunities(nextCommunities);
      setStats(nextStats);
      setHealth(nextHealth);
    } catch (error) {
      setPageError(getErrorMessage(error, "加载社区数据失败"));
    } finally {
      setIsLoading(false);
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function refreshCommunities() {
      setIsLoading(true);
      setPageError(null);

      try {
        const numericLevel = Number.parseInt(level, 10) || 0;
        const [nextCommunities, nextStats, nextHealth] = await Promise.all([
          graphragApi.listCommunities(numericLevel),
          graphragApi.getStatistics(),
          graphragApi.getHealth(),
        ]);

        if (!cancelled) {
          setCommunities(nextCommunities);
          setStats(nextStats);
          setHealth(nextHealth);
        }
      } catch (error) {
        if (!cancelled) {
          setPageError(getErrorMessage(error, "加载社区数据失败"));
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void refreshCommunities();

    return () => {
      cancelled = true;
    };
  }, [graphragApi, level]);

  async function handleGenerateReports() {
    setIsGeneratingReports(true);
    setReportError(null);

    try {
      const numericLevel = Number.parseInt(level, 10) || 0;
      const response = await graphragApi.generateCommunityReports(numericLevel);
      setReports(response.reports);
    } catch (error) {
      setReportError(getErrorMessage(error, "社区报告生成失败"));
    } finally {
      setIsGeneratingReports(false);
    }
  }

  const totalWeight = communities.reduce(
    (sum, community) => sum + community.weight,
    0,
  );
  const currentGraphLabel = graphId || "当前默认图谱";

  return (
    <div
      className="space-y-6"
      data-testid="knowledge-graph-dialog-panel-communities"
    >
      <Card className="border-border/90 bg-white/92 shadow-sm">
        <CardContent className="flex flex-col gap-4 p-5 xl:flex-row xl:items-center xl:justify-between">
          <div className="space-y-2">
            <div className="text-sm font-semibold text-foreground">社区分析</div>
            <p className="max-w-2xl text-sm leading-6 text-muted-foreground">
              这里聚焦图谱社区层级、结构指标和社区报告，不显示任何工作区挂载信息。适合在图谱构建后做结构验收与业务解释。
            </p>
            <div className="inline-flex items-center rounded-full border border-border bg-muted px-3 py-1 text-xs text-muted-foreground">
              当前图谱: {currentGraphLabel}
            </div>
          </div>

          {onOpenWorkbench ? (
            <Button
              variant="outline"
              className="border-border bg-white"
              onClick={onOpenWorkbench}
            >
              切到图谱工作台
            </Button>
          ) : null}
        </CardContent>
      </Card>

      <Card className="border-border/90 shadow-sm">
        <CardContent className="flex flex-col gap-4 p-5 lg:flex-row lg:items-center lg:justify-between">
          <div className="grid flex-1 gap-4 md:grid-cols-[220px_minmax(0,1fr)]">
            <select
              value={level}
              onChange={(event) => setLevel(event.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm text-muted-foreground"
              aria-label="社区层级"
            >
              <option value="0">Level 0</option>
              <option value="1">Level 1</option>
              <option value="2">Level 2</option>
            </select>

            <div className="rounded-2xl border border-border bg-muted/80 px-4 py-3 text-sm leading-6 text-muted-foreground">
              当前图谱 LLM 状态为{" "}
              <span className="font-medium text-foreground">
                {health?.llm_status || stats?.llm_status || "--"}
              </span>
              ，社区报告生成依赖可用的抽取器和报告器配置。
            </div>
          </div>

          <div className="flex flex-wrap gap-3">
            <Button
              variant="outline"
              className="gap-2"
              disabled={isRefreshing}
              onClick={() => void loadCommunityData(true)}
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
              />
              刷新
            </Button>
            <Button
              className="gap-2"
              disabled={isGeneratingReports}
              onClick={() => void handleGenerateReports()}
            >
              {isGeneratingReports ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Sparkles className="h-4 w-4" />
              )}
              生成社区报告
            </Button>
          </div>
        </CardContent>
      </Card>

      {pageError ? (
        <div className="flex items-start gap-3 rounded-2xl border border-warning/20 bg-warning-container p-4 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>{pageError}</div>
        </div>
      ) : null}

      {reportError ? (
        <div className="rounded-2xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
          {reportError}
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="当前层级社区数"
          value={formatGraphNumber(communities.length)}
          helper={`level ${level} 的社区摘要数量`}
        />
        <MetricCard
          label="总权重"
          value={totalWeight.toFixed(2)}
          helper="用于观察社区重要性规模"
        />
        <MetricCard
          label="图谱实体"
          value={formatGraphNumber(stats?.entity_count)}
          helper="社区分析覆盖的实体节点"
        />
        <MetricCard
          label="图谱关系"
          value={formatGraphNumber(stats?.relation_count)}
          helper="关系越丰富，社区结构通常越稳定"
        />
      </div>

      <Card className="border-border/90 shadow-sm">
        <CardHeader>
          <CardTitle className="text-xl text-foreground">社区摘要</CardTitle>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            当前先聚焦于关键实体、规模和类型分布，而不是复杂图可视化。
          </p>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              正在加载社区摘要...
            </div>
          ) : communities.length > 0 ? (
            <div className="grid gap-4 xl:grid-cols-2">
              {communities.map((community) => (
                <div
                  key={community.community_id}
                  className="rounded-2xl border border-border bg-white p-5 shadow-sm"
                >
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-lg font-semibold text-foreground">
                        社区 #{community.community_id}
                      </div>
                      <div className="mt-1 text-sm text-muted-foreground">
                        size {community.size} / weight{" "}
                        {community.weight.toFixed(2)}
                      </div>
                    </div>
                    <div className="rounded-xl bg-muted px-3 py-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">
                      {Object.keys(community.entity_types || {}).length} types
                    </div>
                  </div>

                  <div className="mt-4 space-y-2">
                    <div className="text-sm font-medium text-muted-foreground">
                      关键实体
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {community.key_entities.length > 0 ? (
                        community.key_entities.map((name) => (
                          <span
                            key={name}
                            className="rounded-full bg-muted px-3 py-1 text-xs text-muted-foreground"
                          >
                            {normalizeDisplayText(name)}
                          </span>
                        ))
                      ) : (
                        <span className="text-sm text-muted-foreground">
                          当前社区没有关键实体摘要。
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="mt-5 space-y-3">
                    <div className="text-sm font-medium text-muted-foreground">
                      实体类型分布
                    </div>
                    {Object.entries(community.entity_types || {}).length > 0 ? (
                      Object.entries(community.entity_types || {})
                        .sort(([, left], [, right]) => right - left)
                        .map(([type, count]) => {
                          const percentage = community.size
                            ? Math.round((count / community.size) * 100)
                            : 0;

                          return (
                            <div key={type} className="space-y-1.5">
                              <div className="flex items-center justify-between text-sm text-muted-foreground">
                                <span>{getEntityTypeLabel(type)}</span>
                                <span>
                                  {count} / {percentage}%
                                </span>
                              </div>
                              <div className="h-2 rounded-full bg-muted">
                                <div
                                  className="h-2 rounded-full bg-info"
                                  style={{ width: `${percentage}%` }}
                                />
                              </div>
                            </div>
                          );
                        })
                    ) : (
                      <span className="text-sm text-muted-foreground">
                        当前社区没有类型分布数据。
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="当前层级没有社区"
              description="图谱规模较小时，社区检测可能为空；可以先在图谱工作台继续添加文档，再回到这里刷新。"
            />
          )}
        </CardContent>
      </Card>

      <Card className="border-border/90 shadow-sm">
        <CardHeader>
          <CardTitle className="text-xl text-foreground">社区报告</CardTitle>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            报告由后端 LLM
            按社区摘要生成，适合做结果验收和业务解释，不建议替代实体级核查。
          </p>
        </CardHeader>
        <CardContent>
          {Object.keys(reports).length > 0 ? (
            <div className="space-y-4">
              {Object.entries(reports).map(([communityId, report]) => (
                <div
                  key={communityId}
                  className="rounded-2xl border border-border bg-white p-5 shadow-sm"
                >
                  <div className="text-base font-semibold text-foreground">
                    社区 #{communityId}
                  </div>
                  <div className="mt-3 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">
                    {report}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <EmptyState
              title="还没有社区报告"
              description="点击上方“生成社区报告”后，这里会展示后端返回的报告文本。"
            />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
