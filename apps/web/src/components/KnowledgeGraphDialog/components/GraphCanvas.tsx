import { lazy, Suspense } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { Loader2, RefreshCw } from "lucide-react";
import type { GraphVisualizationResponse, GraphVisualizationNode } from "@/types/graphrag";
import { EmptyState } from "../shared";
import type { LayoutMode } from "../lib/graphConfig";

const PixiExplorer = lazy(() =>
  import("../PixiExplorer").then((module) => ({
    default: module.PixiExplorer,
  })),
);

interface GraphCanvasProps {
  activeGraph: GraphVisualizationResponse | null;
  activeView: "overview" | "query";
  selectedNodeId: string | null;
  searchQuery: string;
  layoutMode: LayoutMode;
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingOverviewGraph: boolean;
  selectedGraphNode: GraphVisualizationNode | null;
  onActiveViewChange: (view: "overview") => void;
  onRefresh: () => void;
  onSelectNode: (nodeId: string | null) => void;
  presentation?: "page" | "dialog";
}

export function GraphCanvas({
  activeGraph,
  activeView,
  selectedNodeId,
  searchQuery,
  layoutMode,
  isLoading,
  isRefreshing,
  isLoadingOverviewGraph,
  selectedGraphNode,
  onActiveViewChange,
  onRefresh,
  onSelectNode,
  presentation = "page",
}: GraphCanvasProps) {
  const compact = presentation === "dialog";
  const canvasHeightClass = compact
    ? "min-h-[360px] h-[52vh] max-h-[640px]"
    : "min-h-[420px] h-[60vh] max-h-[560px]";

  return (
    <Card
      className={cn(
        "overflow-hidden border-border/90 shadow-sm",
        compact ? "h-full self-auto" : "self-start",
      )}
    >
      <CardHeader
        className={cn(
          "flex flex-row items-start justify-between gap-4",
          compact && "border-b border-border/80 px-5 py-4",
        )}
      >
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge className="bg-foreground text-white">
              {activeView === "query" ? "Query Focus" : "Overview"}
            </Badge>
            {activeGraph?.truncated ? (
              <Badge variant="outline" className="border-warning/20 text-warning">
                已截断展示
              </Badge>
            ) : null}
            {selectedGraphNode?.primary_community ? (
              <Badge
                variant="outline"
                className="border-info/20 bg-info-container text-info"
              >
                社区 #{selectedGraphNode.primary_community}
              </Badge>
            ) : null}
          </div>
          <div>
            <CardTitle className={cn("text-foreground", compact ? "text-lg" : "text-xl")}>
              图探索画布
            </CardTitle>
            <p className={cn("text-sm leading-6 text-muted-foreground", compact ? "mt-1" : "mt-2")}>
              {compact
                ? "节点点击后会联动右侧详情；搜索命中会直接在当前图上高亮。"
                : "节点点击后会联动右侧详情；搜索会在当前图上高亮命中节点；问答结果会直接切换到子图模式。"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {activeView === "query" ? (
            <Button
              variant="outline"
              size="sm"
              onClick={() => onActiveViewChange("overview")}
            >
              回到总览
            </Button>
          ) : null}
          <Button
            variant="outline"
            size="sm"
            className="gap-2"
            disabled={isRefreshing}
            onClick={onRefresh}
          >
            <RefreshCw
              className={`h-4 w-4 ${isRefreshing ? "animate-spin" : ""}`}
            />
            刷新
          </Button>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {isLoading && !activeGraph ? (
          <div className={cn("flex items-center justify-center text-sm text-muted-foreground", canvasHeightClass)}>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在加载图数据...
          </div>
        ) : isLoadingOverviewGraph &&
          activeView !== "query" &&
          !activeGraph ? (
          <div className={cn("flex items-center justify-center text-sm text-muted-foreground", canvasHeightClass)}>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            正在准备图画布...
          </div>
        ) : activeGraph && activeGraph.nodes.length > 0 ? (
          <div className={cn(canvasHeightClass, "bg-card")}>
            <Suspense
              fallback={
                <div className={cn("flex items-center justify-center text-sm text-muted-foreground", canvasHeightClass)}>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  正在加载图引擎...
                </div>
              }
            >
              <PixiExplorer
                data={activeGraph}
                selectedNodeId={selectedNodeId}
                searchQuery={searchQuery}
                layoutMode={layoutMode}
                onSelectNode={onSelectNode}
              />
            </Suspense>
          </div>
        ) : (
          <div className="p-6">
            <EmptyState
              title="图谱还没有可视化数据"
              description="先在下方提交一段文档构图，或者执行一次图谱问答，页面就会生成可探索的节点与关系。"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
