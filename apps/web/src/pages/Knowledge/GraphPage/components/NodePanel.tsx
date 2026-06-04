import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { Waypoints } from "lucide-react";
import type { GraphVisualizationResponse, GraphVisualizationNode, GraphEntity } from "@/types/graphrag";
import { formatGraphNumber } from "../shared";
import { NodeSearchTab } from "./NodeSearchTab";
import { NodeDetailsTab } from "./NodeDetailsTab";

interface NodePanelProps {
  activeGraph: GraphVisualizationResponse | null;
  searchQuery: string;
  selectedNodeId: string | null;
  selectedGraphNode: GraphVisualizationNode | null;
  selectedEntity: GraphEntity | null;
  isLoadingEntity: boolean;
  entityError: string | null;
  inspectorTab: "search" | "details";
  onInspectorTabChange: (tab: "search" | "details") => void;
  onSearchQueryChange: (query: string) => void;
  onSelectNode: (nodeId: string | null) => void;
  presentation?: "page" | "dialog";
}

export function NodePanel({
  activeGraph,
  searchQuery,
  selectedNodeId,
  selectedGraphNode,
  selectedEntity,
  isLoadingEntity,
  entityError,
  inspectorTab,
  onInspectorTabChange,
  onSearchQueryChange,
  onSelectNode,
  presentation = "page",
}: NodePanelProps) {
  const compact = presentation === "dialog";

  return (
    <Card
      className={cn(
        "overflow-hidden border-border/90 shadow-sm",
        compact
          ? "h-full min-h-[360px] self-auto"
          : "self-start min-h-[420px] h-[60vh] max-h-[560px]",
      )}
    >
      <CardHeader className={cn("border-b border-border/80", compact ? "px-5 py-4" : "pb-4")}>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className={cn("flex items-center gap-2 text-foreground", compact ? "text-base" : "text-lg")}>
            <Waypoints className="h-4 w-4" />
            节点面板
          </CardTitle>
          <div className="text-xs text-muted-foreground">
            当前节点 {formatGraphNumber(activeGraph?.nodes.length)}
          </div>
        </div>
      </CardHeader>
      <CardContent
        className={cn(
          "flex flex-col p-0",
          compact
            ? "h-[calc(52vh-5.25rem)] min-h-[280px] max-h-[560px]"
            : "h-[calc(60vh-5.75rem)] min-h-[324px] max-h-[468px]",
        )}
      >
        <Tabs
          value={inspectorTab}
          onValueChange={(value) => onInspectorTabChange(value as "search" | "details")}
          className="flex h-full flex-col"
        >
          <div className="border-b border-border/80 px-4 py-3">
            <TabsList className="grid h-auto w-full grid-cols-2 rounded-xl bg-muted p-1">
              <TabsTrigger value="search" className="rounded-lg py-2">
                搜索
              </TabsTrigger>
              <TabsTrigger value="details" className="rounded-lg py-2">
                详情
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="search" className="mt-0 flex-1 overflow-hidden">
            <NodeSearchTab
              activeGraph={activeGraph}
              searchQuery={searchQuery}
              selectedNodeId={selectedNodeId}
              onSearchQueryChange={onSearchQueryChange}
              onSelectNode={onSelectNode}
            />
          </TabsContent>

          <TabsContent value="details" className="mt-0 flex-1 overflow-hidden">
            <NodeDetailsTab
              activeGraph={activeGraph}
              selectedNodeId={selectedNodeId}
              selectedGraphNode={selectedGraphNode}
              selectedEntity={selectedEntity}
              isLoadingEntity={isLoadingEntity}
              entityError={entityError}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
