import { GraphCanvas } from "./GraphCanvas";
import { NodePanel } from "./NodePanel";
import type { GraphVisualizationResponse, GraphVisualizationNode, GraphEntity } from "@/types/graphrag";
import type { LayoutMode } from "../lib/graphConfig";

interface OverviewTabProps {
  activeGraph: GraphVisualizationResponse | null;
  activeView: "overview" | "query";
  selectedNodeId: string | null;
  searchQuery: string;
  layoutMode: LayoutMode;
  isLoading: boolean;
  isRefreshing: boolean;
  isLoadingOverviewGraph: boolean;
  selectedGraphNode: GraphVisualizationNode | null;
  selectedEntity: GraphEntity | null;
  isLoadingEntity: boolean;
  entityError: string | null;
  inspectorTab: "search" | "details";
  onActiveViewChange: (view: "overview") => void;
  onRefresh: () => void;
  onSelectNode: (nodeId: string | null) => void;
  onInspectorTabChange: (tab: "search" | "details") => void;
  onSearchQueryChange: (query: string) => void;
  presentation?: "page" | "dialog";
}

export function OverviewTab({
  activeGraph,
  activeView,
  selectedNodeId,
  searchQuery,
  layoutMode,
  isLoading,
  isRefreshing,
  isLoadingOverviewGraph,
  selectedGraphNode,
  selectedEntity,
  isLoadingEntity,
  entityError,
  inspectorTab,
  onActiveViewChange,
  onRefresh,
  onSelectNode,
  onInspectorTabChange,
  onSearchQueryChange,
  presentation = "page",
}: OverviewTabProps) {
  return (
    <div
      className={
        presentation === "dialog"
          ? "grid min-h-0 items-stretch gap-4 xl:grid-cols-[minmax(0,1.35fr)_340px]"
          : "grid items-start gap-6 xl:grid-cols-[minmax(0,1.35fr)_360px]"
      }
    >
      <GraphCanvas
        activeGraph={activeGraph}
        activeView={activeView}
        selectedNodeId={selectedNodeId}
        searchQuery={searchQuery}
        layoutMode={layoutMode}
        isLoading={isLoading}
        isRefreshing={isRefreshing}
        isLoadingOverviewGraph={isLoadingOverviewGraph}
        selectedGraphNode={selectedGraphNode}
        onActiveViewChange={onActiveViewChange}
        onRefresh={onRefresh}
        onSelectNode={onSelectNode}
        presentation={presentation}
      />
      <NodePanel
        activeGraph={activeGraph}
        searchQuery={searchQuery}
        selectedNodeId={selectedNodeId}
        selectedGraphNode={selectedGraphNode}
        selectedEntity={selectedEntity}
        isLoadingEntity={isLoadingEntity}
        entityError={entityError}
        inspectorTab={inspectorTab}
        onInspectorTabChange={onInspectorTabChange}
        onSearchQueryChange={onSearchQueryChange}
        onSelectNode={onSelectNode}
        presentation={presentation}
      />
    </div>
  );
}
