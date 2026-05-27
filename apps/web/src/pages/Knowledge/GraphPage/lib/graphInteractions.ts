import type {
  GraphEdgeMeta,
  GraphNodeMeta,
  GraphRenderData,
} from "./graphConfig";

export type GraphInteractionState = {
  matchedNodeIds: Set<string>;
  matchedEdgeIds: Set<string>;
  focusNodeIds: Set<string>;
  focusEdgeIds: Set<string>;
  dimmedNodeIds: Set<string>;
  dimmedEdgeIds: Set<string>;
};

export function createAdjacency(data: GraphRenderData) {
  const neighbors = new Map<string, Set<string>>();
  const activeEdgesByNode = new Map<string, Set<string>>();

  for (const node of data.nodes) {
    neighbors.set(String(node.id), new Set());
    activeEdgesByNode.set(String(node.id), new Set());
  }

  for (const edge of data.edges) {
    const source = String(edge.source);
    const target = String(edge.target);
    const edgeId = String(edge.id || `${source}-${target}`);

    neighbors.get(source)?.add(target);
    neighbors.get(target)?.add(source);
    activeEdgesByNode.get(source)?.add(edgeId);
    activeEdgesByNode.get(target)?.add(edgeId);
  }

  return { neighbors, activeEdgesByNode };
}

export function buildInteractionState(
  graphData: GraphRenderData,
  selectedNodeId: string | null,
  searchQuery: string,
): GraphInteractionState {
  const normalizedQuery = searchQuery.trim().toLowerCase();
  const { neighbors, activeEdgesByNode } = createAdjacency(graphData);
  const nodeIds = new Set(graphData.nodes.map((node) => String(node.id)));
  const edgeIds = new Set(
    graphData.edges.map((edge) => String(edge.id || `${edge.source}-${edge.target}`)),
  );

  const matchedNodeIds = new Set<string>();
  const matchedEdgeIds = new Set<string>();

  if (normalizedQuery) {
    for (const node of graphData.nodes) {
      const meta = node.data as Partial<GraphNodeMeta>;
      const propValues = Object.values(meta.properties || {})
        .map((value) => (typeof value === "string" ? value : String(value)))
        .join(" ");
      const haystack = [meta.label, meta.description, meta.entityType, propValues]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();

      if (haystack.includes(normalizedQuery)) {
        matchedNodeIds.add(String(node.id));
      }
    }

    for (const edge of graphData.edges) {
      const meta = edge.data as Partial<GraphEdgeMeta>;
      const sourceMatched = matchedNodeIds.has(String(edge.source));
      const targetMatched = matchedNodeIds.has(String(edge.target));
      if (
        sourceMatched ||
        targetMatched ||
        (meta.relationType || "").toLowerCase().includes(normalizedQuery) ||
        (meta.description || "").toLowerCase().includes(normalizedQuery)
      ) {
        matchedEdgeIds.add(String(edge.id || `${edge.source}-${edge.target}`));
      }
    }
  }

  const focusNodeIds = new Set<string>();
  const focusEdgeIds = new Set<string>();

  if (selectedNodeId && nodeIds.has(selectedNodeId)) {
    focusNodeIds.add(selectedNodeId);
    neighbors.get(selectedNodeId)?.forEach((id) => focusNodeIds.add(id));
    activeEdgesByNode.get(selectedNodeId)?.forEach((id) => focusEdgeIds.add(id));
  }

  matchedNodeIds.forEach((id) => focusNodeIds.add(id));
  matchedEdgeIds.forEach((id) => focusEdgeIds.add(id));

  const hasFocusedNodes = focusNodeIds.size > 0;
  const dimmedNodeIds = new Set<string>();
  const dimmedEdgeIds = new Set<string>();

  if (hasFocusedNodes) {
    nodeIds.forEach((id) => {
      if (!focusNodeIds.has(id) && selectedNodeId !== id) {
        dimmedNodeIds.add(id);
      }
    });

    edgeIds.forEach((id) => {
      if (!focusEdgeIds.has(id) && !matchedEdgeIds.has(id)) {
        dimmedEdgeIds.add(id);
      }
    });
  }

  return {
    matchedNodeIds,
    matchedEdgeIds,
    focusNodeIds,
    focusEdgeIds,
    dimmedNodeIds,
    dimmedEdgeIds,
  };
}

export function findFirstMatchedNodeId(
  graphData: GraphRenderData,
  searchQuery: string,
): string | null {
  const normalizedQuery = searchQuery.trim().toLowerCase();
  if (!normalizedQuery) {
    return null;
  }

  for (const node of graphData.nodes) {
    const meta = node.data;
    const propValues = Object.values(meta.properties || {})
      .map((value) => (typeof value === "string" ? value : String(value)))
      .join(" ");
    const haystack = [meta.label, meta.description, meta.entityType, propValues]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();

    if (haystack.includes(normalizedQuery)) {
      return String(node.id);
    }
  }

  return null;
}
