import { Search, Network, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import type { GraphQueryResponse } from "@/types/graphrag";
import { EmptyState, EntityTypeBadge, formatGraphNumber, normalizeDisplayText } from "../shared";

interface QueryTabProps {
  question: string;
  queryTopK: string;
  queryDepth: string;
  useCommunities: boolean;
  isQuerying: boolean;
  queryError: string | null;
  queryResult: GraphQueryResponse | null;
  onQuestionChange: (q: string) => void;
  onTopKChange: (k: string) => void;
  onDepthChange: (d: string) => void;
  onUseCommunitiesChange: (v: boolean) => void;
  onSubmit: (e: React.FormEvent) => void;
  onEntityClick: (entityName: string, hasSubgraph: boolean) => void;
}

export function QueryTab({
  question,
  queryTopK,
  queryDepth,
  useCommunities,
  isQuerying,
  queryError,
  queryResult,
  onQuestionChange,
  onTopKChange,
  onDepthChange,
  onUseCommunitiesChange,
  onSubmit,
  onEntityClick,
}: QueryTabProps) {
  return (
    <Card className="self-start border-border/90 shadow-sm">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="flex items-center gap-2 text-xl text-foreground">
            <Network className="h-5 w-5" />
            图谱问答与子图切换
          </CardTitle>
        </div>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          问答更适合作为看图之后的下游动作。这里会调用后端 GraphRAG 查询，并把命中的子图切回上方画布做聚焦浏览。
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="space-y-4" onSubmit={onSubmit}>
          <div className="space-y-2">
            <Label htmlFor="graph-question">查询问题</Label>
            <Input
              id="graph-question"
              value={question}
              onChange={(e) => onQuestionChange(e.target.value)}
              placeholder="例如：张明和 Atlas shared knowledge cache 有什么关系？"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="graph-top-k">Top K</Label>
              <Input
                id="graph-top-k"
                type="number"
                min="1"
                max="20"
                value={queryTopK}
                onChange={(e) => onTopKChange(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="graph-depth">子图深度</Label>
              <Input
                id="graph-depth"
                type="number"
                min="1"
                max="3"
                value={queryDepth}
                onChange={(e) => onDepthChange(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-muted p-3">
            <Checkbox
              id="graph-use-communities"
              checked={useCommunities}
              onCheckedChange={(checked) => onUseCommunitiesChange(checked === true)}
            />
            <Label
              htmlFor="graph-use-communities"
              className="cursor-pointer text-sm text-muted-foreground"
            >
              返回命中的社区信息
            </Label>
          </div>

          {queryError ? (
            <div className="rounded-xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
              {queryError}
            </div>
          ) : null}

          <Button type="submit" className="gap-2" disabled={isQuerying}>
            {isQuerying ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            执行图谱查询
          </Button>
        </form>

        {queryResult ? (
          <div className="space-y-4 rounded-2xl border border-border bg-muted/70 p-4">
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl bg-white p-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  命中实体
                </div>
                <div className="mt-2 text-2xl font-semibold text-foreground">
                  {formatGraphNumber(queryResult.entities.length)}
                </div>
              </div>
              <div className="rounded-xl bg-white p-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  子图节点
                </div>
                <div className="mt-2 text-2xl font-semibold text-foreground">
                  {formatGraphNumber(queryResult.subgraph_stats?.nodes)}
                </div>
              </div>
              <div className="rounded-xl bg-white p-3 shadow-sm">
                <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                  子图边
                </div>
                <div className="mt-2 text-2xl font-semibold text-foreground">
                  {formatGraphNumber(queryResult.subgraph_stats?.edges)}
                </div>
              </div>
            </div>

            {queryResult.entities.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {queryResult.entities.map((entity) => (
                  <button
                    key={`${entity.name}-${entity.entity_type}`}
                    type="button"
                    className="rounded-full border border-border bg-white px-3 py-2 shadow-sm"
                    onClick={() => onEntityClick(entity.name, !!queryResult.subgraph?.nodes.length)}
                  >
                    <div className="text-sm font-medium text-foreground">
                      {normalizeDisplayText(entity.name)}
                    </div>
                    <div className="mt-1">
                      <EntityTypeBadge entityType={entity.entity_type} />
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState
                title="未命中实体"
                description="当前问题没有在图谱里召回到实体，可以先构入一段文档再重试。"
              />
            )}

            <div className="max-h-[240px] overflow-auto whitespace-pre-wrap rounded-2xl border border-border bg-foreground p-4 font-mono text-sm leading-6 text-primary-foreground">
              {queryResult.context || "当前查询没有生成上下文内容。"}
            </div>

            {queryResult.communities && queryResult.communities.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-2">
                {queryResult.communities.map((community) => (
                  <div
                    key={community.community_id}
                    className="rounded-2xl border border-border bg-white p-4 shadow-sm"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="text-base font-semibold text-foreground">
                        社区 #{community.community_id}
                      </div>
                      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        size {community.size}
                      </div>
                    </div>
                    <div className="mt-3 text-sm text-muted-foreground">
                      命中实体:{" "}
                      {community.overlap_entities
                        .map((item) => normalizeDisplayText(item))
                        .join(", ")}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
