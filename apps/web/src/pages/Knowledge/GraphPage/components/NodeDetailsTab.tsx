import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import type { GraphVisualizationResponse, GraphVisualizationNode, GraphEntity } from "@/types/graphrag";
import { EmptyState, EntityTypeBadge, formatMetadataValue, normalizeDisplayText } from "../shared";

interface NodeDetailsTabProps {
  activeGraph: GraphVisualizationResponse | null;
  selectedNodeId: string | null;
  selectedGraphNode: GraphVisualizationNode | null;
  selectedEntity: GraphEntity | null;
  isLoadingEntity: boolean;
  entityError: string | null;
}

function getNodeSummary(
  activeGraph: GraphVisualizationResponse | null,
  selectedNodeId: string | null,
) {
  if (!activeGraph || !selectedNodeId) return [];

  return activeGraph.edges
    .filter(
      (edge) => edge.source === selectedNodeId || edge.target === selectedNodeId,
    )
    .slice(0, 10)
    .map((edge) => {
      const partner = edge.source === selectedNodeId ? edge.target : edge.source;
      return {
        id: edge.id,
        partner,
        relationType: edge.relation_type || "",
        description: edge.description || "",
        strength: edge.strength,
      };
    });
}

export function NodeDetailsTab({
  activeGraph,
  selectedNodeId,
  selectedGraphNode,
  selectedEntity,
  isLoadingEntity,
  entityError,
}: NodeDetailsTabProps) {
  const selectedRelations = getNodeSummary(activeGraph, selectedNodeId);
  const selectedMetadata = Object.entries(
    selectedEntity?.properties || selectedGraphNode?.properties || {},
  );

  if (!selectedGraphNode) {
    return (
      <div className="flex h-full flex-col px-4 py-4">
        <EmptyState
          title="选择一个节点"
          description="点击左侧图中的节点，或者先在「搜索节点」里选一个实体查看详情。"
        />
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col px-4 py-4">
      <div className="rounded-2xl border border-border bg-muted/70 p-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-lg font-semibold text-foreground">
              {normalizeDisplayText(selectedGraphNode.name)}
            </div>
            <div className="mt-1 text-sm text-muted-foreground">
              degree {selectedGraphNode.degree}
            </div>
          </div>
          <EntityTypeBadge entityType={selectedGraphNode.entity_type} />
        </div>

        <div className="mt-3 text-sm leading-6 text-muted-foreground">
          {normalizeDisplayText(
            selectedEntity?.description ||
              selectedGraphNode.description ||
              "暂无描述信息。",
          )}
        </div>

        {selectedGraphNode.community_ids.length > 0 ? (
          <div className="mt-3 flex flex-wrap gap-2">
            {selectedGraphNode.community_ids.map((communityId) => (
              <Badge
                key={communityId}
                variant="outline"
                className="border-info/20 bg-info-container text-info"
              >
                社区 #{communityId}
              </Badge>
            ))}
          </div>
        ) : null}
      </div>

      <div className="mt-4 flex-1 overflow-auto pr-1">
        {isLoadingEntity ? (
          <div className="rounded-xl border border-border bg-white px-4 py-3 text-sm text-muted-foreground">
            <Loader2 className="mr-2 inline h-4 w-4 animate-spin" />
            正在加载实体详情...
          </div>
        ) : null}

        {entityError ? (
          <div className="mb-3 rounded-xl border border-warning/20 bg-warning-container px-4 py-3 text-sm text-warning">
            {entityError}
          </div>
        ) : null}

        <Accordion
          type="multiple"
          defaultValue={["relations"]}
          className="rounded-2xl border border-border bg-white px-4"
        >
          <AccordionItem value="relations">
            <AccordionTrigger className="py-4 text-sm font-medium text-foreground hover:no-underline">
              邻接关系
            </AccordionTrigger>
            <AccordionContent className="pb-4">
              {selectedRelations.length > 0 ? (
                <div className="space-y-2">
                  {selectedRelations.map((relation) => (
                    <div
                      key={relation.id}
                      className="rounded-2xl border border-border bg-muted/70 px-3 py-3 text-sm"
                    >
                      <div className="font-medium text-foreground">
                        {normalizeDisplayText(selectedGraphNode.name)} →{" "}
                        {normalizeDisplayText(relation.partner)}
                      </div>
                      <div className="mt-1 text-muted-foreground">
                        {normalizeDisplayText(relation.description) ||
                          normalizeDisplayText(relation.relationType) ||
                          "未提供关系描述"}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2 text-xs text-muted-foreground">
                        {relation.relationType ? (
                          <Badge variant="outline">
                            {normalizeDisplayText(relation.relationType)}
                          </Badge>
                        ) : null}
                        <span className="uppercase tracking-[0.18em]">
                          strength {relation.strength}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-border bg-muted p-4 text-sm text-muted-foreground">
                  当前节点在该视图里没有暴露更多边关系。
                </div>
              )}
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="metadata">
            <AccordionTrigger className="py-4 text-sm font-medium text-foreground hover:no-underline">
              元数据
            </AccordionTrigger>
            <AccordionContent className="pb-4">
              {selectedMetadata.length > 0 ? (
                <div className="space-y-2">
                  {selectedMetadata.map(([key, value]) => (
                    <div
                      key={key}
                      className="rounded-2xl border border-border bg-muted/70 px-3 py-3"
                    >
                      <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
                        {key}
                      </div>
                      <div className="mt-2 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">
                        {formatMetadataValue(value)}
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="rounded-2xl border border-dashed border-border bg-muted p-4 text-sm text-muted-foreground">
                  当前节点没有额外元数据。
                </div>
              )}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>
    </div>
  );
}
