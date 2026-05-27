import { useMemo } from "react";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import type { GraphVisualizationResponse, GraphVisualizationNode } from "@/types/graphrag";
import { EmptyState, EntityTypeBadge, formatGraphNumber, normalizeDisplayText } from "../shared";

interface NodeSearchTabProps {
  activeGraph: GraphVisualizationResponse | null;
  searchQuery: string;
  selectedNodeId: string | null;
  onSearchQueryChange: (query: string) => void;
  onSelectNode: (nodeId: string | null) => void;
}

function matchesNode(node: GraphVisualizationNode, query: string) {
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return true;

  return [
    node.name,
    node.description || "",
    node.entity_type,
    node.primary_community || "",
    node.community_ids.join(" "),
  ]
    .join(" ")
    .toLowerCase()
    .includes(normalizedQuery);
}

export function NodeSearchTab({
  activeGraph,
  searchQuery,
  selectedNodeId,
  onSearchQueryChange,
  onSelectNode,
}: NodeSearchTabProps) {
  const filteredNodes = useMemo(() => {
    return (activeGraph?.nodes || []).filter((node) => matchesNode(node, searchQuery));
  }, [activeGraph?.nodes, searchQuery]);

  return (
    <div className="flex h-full flex-col px-4 py-4">
      <div className="space-y-2">
        <Label htmlFor="graph-search">搜索节点</Label>
        <Input
          id="graph-search"
          value={searchQuery}
          onChange={(e) => onSearchQueryChange(e.target.value)}
          placeholder="实体名、描述、类型或社区号"
        />
      </div>

      <div className="mt-4 rounded-2xl border border-border bg-muted/70 p-3 text-xs leading-6 text-muted-foreground">
        当前视图共{" "}
        <span className="font-semibold text-foreground">
          {formatGraphNumber(activeGraph?.nodes.length)}
        </span>{" "}
        个节点，搜索命中{" "}
        <span className="font-semibold text-foreground">
          {formatGraphNumber(filteredNodes.length)}
        </span>{" "}
        个。
      </div>

      <div className="mt-4 flex-1 space-y-2 overflow-auto pr-1">
        {filteredNodes.length > 0 ? (
          filteredNodes.slice(0, 24).map((node) => {
            const isSelected = node.id === selectedNodeId;
            return (
              <button
                key={node.id}
                type="button"
                className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                  isSelected
                    ? "border-foreground bg-foreground text-white"
                    : "border-border bg-white hover:border-border hover:bg-muted"
                }`}
                onClick={() => onSelectNode(node.id)}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold">
                      {normalizeDisplayText(node.name)}
                    </div>
                    <div
                      className={`mt-1 text-xs ${
                        isSelected ? "text-muted-foreground" : "text-muted-foreground"
                      }`}
                    >
                      degree {node.degree}
                    </div>
                  </div>
                  <EntityTypeBadge
                    entityType={node.entity_type}
                    className={isSelected ? "border-white/20 bg-white/10 text-white" : ""}
                  />
                </div>
              </button>
            );
          })
        ) : (
          <EmptyState
            title="没有命中节点"
            description="换个关键字试试，或者先切回总览图查看全局图谱。"
          />
        )}
      </div>
    </div>
  );
}
