import type { GraphVisualizationResponse } from "@/types/graphrag";

export type LayoutMode = "force";

export type GraphNodeMeta = {
  label: string;
  description: string;
  color: string;
  size: number;
  degree: number;
  entityType: string;
  communityIds: string[];
  primaryCommunity: string | null;
  properties: Record<string, unknown>;
};

export type GraphEdgeMeta = {
  relationType: string;
  description: string;
  lineWidth: number;
  strength: number;
};

export type GraphRenderNode = {
  id: string;
  data: GraphNodeMeta;
};

export type GraphRenderEdge = {
  id: string;
  source: string;
  target: string;
  data: GraphEdgeMeta;
};

export type GraphRenderData = {
  nodes: GraphRenderNode[];
  edges: GraphRenderEdge[];
};

export const ENTITY_COLORS: Record<string, string> = {
  person: "#2563eb",
  organization: "#059669",
  technology: "#7c3aed",
  concept: "#d97706",
  product: "#db2777",
  industry: "#0891b2",
  event: "#dc2626",
  location: "#65a30d",
  unknown: "#64748b",
};

export const COMMUNITY_COLORS = [
  "#2563eb",
  "#0f766e",
  "#c2410c",
  "#7c3aed",
  "#be123c",
  "#1d4ed8",
  "#15803d",
  "#9333ea",
  "#b45309",
  "#0369a1",
];

export function normalizeLayoutMode(value?: string | null): LayoutMode {
  void value;
  return "force";
}

export function normalizeEntityType(value?: string | null): string {
  return (value || "unknown")
    .trim()
    .replace(/^["'`]|["'`]$/g, "")
    .toLowerCase();
}

export function normalizeDisplayText(value?: string | null): string {
  return (value || "")
    .trim()
    .replace(/^["'`"']+|["'`"']+$/g, "")
    .trim();
}

export function getCommunityColor(communityId?: string | null): string | null {
  if (!communityId) {
    return null;
  }

  const numericId = Number.parseInt(communityId, 10);
  if (Number.isFinite(numericId)) {
    return COMMUNITY_COLORS[Math.abs(numericId) % COMMUNITY_COLORS.length];
  }

  const seed = Array.from(communityId).reduce(
    (sum, char) => sum + char.charCodeAt(0),
    0,
  );
  return COMMUNITY_COLORS[seed % COMMUNITY_COLORS.length];
}

export function getNodeColor(node: {
  primary_community?: string | null;
  entity_type?: string;
}): string {
  return (
    getCommunityColor(node.primary_community) ||
    ENTITY_COLORS[normalizeEntityType(node.entity_type)] ||
    ENTITY_COLORS.unknown
  );
}

export function buildGraphData(data: GraphVisualizationResponse): GraphRenderData {
  const nodes = data.nodes.map((node) => {
    const label = normalizeDisplayText(node.name) || node.id;
    const color = getNodeColor(node);

    return {
      id: node.id,
      data: {
        label,
        description: normalizeDisplayText(node.description),
        color,
        degree: node.degree,
        size: 18 + Math.sqrt(Math.max(node.degree, 1)) * 5,
        entityType: normalizeEntityType(node.entity_type),
        communityIds: node.community_ids,
        primaryCommunity: node.primary_community || null,
        properties: node.properties || {},
      } satisfies GraphNodeMeta,
    };
  });

  const edges = data.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    data: {
      relationType: normalizeDisplayText(edge.relation_type),
      description: normalizeDisplayText(edge.description),
      strength: edge.strength || 1,
      lineWidth: Math.max(1, Math.min(3, (edge.strength || 1) * 0.28)),
    } satisfies GraphEdgeMeta,
  }));

  return { nodes, edges };
}

export function getPreferredZoom(nodeCount: number): number {
  if (nodeCount <= 8) {
    return 1.9;
  }
  if (nodeCount <= 16) {
    return 1.55;
  }
  if (nodeCount <= 28) {
    return 1.28;
  }
  return 1;
}
