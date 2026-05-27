import { useCallback, useRef, useState } from "react";
import { normalizeCanvasDocument } from "./canvasUtils";
import type {
  CanvasDocument,
  CanvasEdge,
  CanvasNode,
  CanvasViewportState,
} from "./types";

interface CanvasHistoryState {
  past: CanvasDocument[];
  present: CanvasDocument;
  future: CanvasDocument[];
}

function uniqueIds(ids: string[]): string[] {
  return Array.from(new Set(ids.filter(Boolean)));
}

function isSameCanvasDocument(
  left: CanvasDocument,
  right: CanvasDocument,
): boolean {
  return JSON.stringify(normalizeCanvasDocument(left)) ===
    JSON.stringify(normalizeCanvasDocument(right));
}

function findLastDifferentCanvasIndex(
  snapshots: CanvasDocument[],
  present: CanvasDocument,
): number {
  for (let index = snapshots.length - 1; index >= 0; index -= 1) {
    const snapshot = snapshots[index];
    if (!isSameCanvasDocument(snapshot, present)) {
      return index;
    }
  }
  return -1;
}

export function useCanvasState(initialCanvas: CanvasDocument | null) {
  const initial = normalizeCanvasDocument(initialCanvas);
  const canvasRef = useRef<CanvasDocument>(initial);
  const historyRef = useRef<CanvasHistoryState>({
    past: [],
    present: initial,
    future: [],
  });
  const [canvas, setCanvasState] = useState<CanvasDocument>(initial);
  const [historyCounts, setHistoryCounts] = useState({ past: 0, future: 0 });
  const [viewport, setViewport] = useState<CanvasViewportState>({
    x: 40,
    y: 40,
    scale: 1,
  });
  const [selectedNodeIds, setSelectedNodeIdsState] = useState<string[]>([]);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [isDraggingNode, setIsDraggingNode] = useState(false);
  const [isPanning, setIsPanning] = useState(false);
  const selectedNodeId = selectedNodeIds[0] || null;

  const setSelectedNodeIds = useCallback((ids: string[]) => {
    setSelectedNodeIdsState(uniqueIds(ids));
  }, []);

  const setSelectedNodeId = useCallback((id: string | null) => {
    setSelectedNodeIdsState(id ? [id] : []);
  }, []);

  const updateHistoryCounts = useCallback(() => {
    setHistoryCounts({
      past: historyRef.current.past.length,
      future: historyRef.current.future.length,
    });
  }, []);

  const commitCanvas = useCallback((next: CanvasDocument): CanvasDocument => {
    const normalized = normalizeCanvasDocument(next);
    historyRef.current.present = normalized;
    canvasRef.current = normalized;
    setCanvasState(normalized);
    return normalized;
  }, []);

  const setCanvasDocument = useCallback(
    (next: CanvasDocument): CanvasDocument => commitCanvas(next),
    [commitCanvas],
  );

  const replaceCanvas = useCallback(
    (next: CanvasDocument): CanvasDocument => {
      const normalized = normalizeCanvasDocument(next);
      historyRef.current = { past: [], present: normalized, future: [] };
      updateHistoryCounts();
      canvasRef.current = normalized;
      setCanvasState(normalized);
      return normalized;
    },
    [updateHistoryCounts],
  );

  const recordHistorySnapshot = useCallback(() => {
    const current = historyRef.current.present;
    const lastPast = historyRef.current.past.at(-1);
    if (lastPast && isSameCanvasDocument(lastPast, current)) {
      if (historyRef.current.future.length > 0) {
        historyRef.current = {
          past: historyRef.current.past,
          present: current,
          future: [],
        };
        updateHistoryCounts();
      }
      return;
    }
    historyRef.current = {
      past: [...historyRef.current.past.slice(-79), current],
      present: current,
      future: [],
    };
    updateHistoryCounts();
  }, [updateHistoryCounts]);

  const undoCanvas = useCallback((): CanvasDocument | null => {
    const history = historyRef.current;
    const previousIndex = findLastDifferentCanvasIndex(
      history.past,
      history.present,
    );
    const previous = previousIndex >= 0 ? history.past[previousIndex] : null;
    if (!previous) {
      return null;
    }

    historyRef.current = {
      past: history.past.slice(0, previousIndex),
      present: previous,
      future: [history.present, ...history.future].slice(0, 80),
    };
    canvasRef.current = previous;
    setCanvasState(previous);
    updateHistoryCounts();
    return previous;
  }, [updateHistoryCounts]);

  const redoCanvas = useCallback((): CanvasDocument | null => {
    const history = historyRef.current;
    const nextIndex = history.future.findIndex(
      (snapshot) => !isSameCanvasDocument(snapshot, history.present),
    );
    const next = nextIndex >= 0 ? history.future[nextIndex] : null;
    if (!next) {
      return null;
    }

    historyRef.current = {
      past: [...history.past.slice(-79), history.present],
      present: next,
      future: history.future.slice(nextIndex + 1),
    };
    canvasRef.current = next;
    setCanvasState(next);
    updateHistoryCounts();
    return next;
  }, [updateHistoryCounts]);

  const getCanvas = useCallback(() => canvasRef.current, []);

  const addNode = useCallback(
    (node: CanvasNode): CanvasDocument => {
      const current = canvasRef.current;
      if (current.nodes.some((item) => item.id === node.id)) {
        return current;
      }
      return commitCanvas({
        ...current,
        nodes: node.type === "group" ? [node, ...current.nodes] : [...current.nodes, node],
      });
    },
    [commitCanvas],
  );

  const updateNode = useCallback(
    (nodeId: string, patch: Partial<CanvasNode>): CanvasDocument => {
      const current = canvasRef.current;
      if (!current.nodes.some((node) => node.id === nodeId)) {
        return current;
      }
      return commitCanvas({
        ...current,
        nodes: current.nodes.map((node) =>
          node.id === nodeId ? { ...node, ...patch, id: node.id } : node,
        ),
      });
    },
    [commitCanvas],
  );

  const updateNodes = useCallback(
    (patches: Record<string, Partial<CanvasNode>>): CanvasDocument => {
      const current = canvasRef.current;
      const patchEntries = Object.entries(patches).filter(([, patch]) => patch);
      if (patchEntries.length === 0) {
        return current;
      }
      const patchMap = new Map(patchEntries);
      const hasTarget = current.nodes.some((node) => patchMap.has(node.id));
      if (!hasTarget) {
        return current;
      }
      return commitCanvas({
        ...current,
        nodes: current.nodes.map((node) => {
          const patch = patchMap.get(node.id);
          return patch ? { ...node, ...patch, id: node.id } : node;
        }),
      });
    },
    [commitCanvas],
  );

  const removeNode = useCallback(
    (nodeId: string): CanvasDocument => {
      const current = canvasRef.current;
      return commitCanvas({
        ...current,
        nodes: current.nodes.filter((node) => node.id !== nodeId),
        edges: current.edges.filter(
          (edge) => edge.fromNode !== nodeId && edge.toNode !== nodeId,
        ),
      });
    },
    [commitCanvas],
  );

  const removeNodes = useCallback(
    (nodeIds: string[]): CanvasDocument => {
      const ids = new Set(nodeIds);
      const current = canvasRef.current;
      if (ids.size === 0) {
        return current;
      }
      return commitCanvas({
        ...current,
        nodes: current.nodes.filter((node) => !ids.has(node.id)),
        edges: current.edges.filter(
          (edge) => !ids.has(edge.fromNode) && !ids.has(edge.toNode),
        ),
      });
    },
    [commitCanvas],
  );

  const addEdge = useCallback(
    (edge: CanvasEdge): CanvasDocument => {
      const current = canvasRef.current;
      const hasEdge = current.edges.some((item) => item.id === edge.id);
      const hasSameConnection = current.edges.some(
        (item) => item.fromNode === edge.fromNode && item.toNode === edge.toNode,
      );
      const hasNodes = current.nodes.some((node) => node.id === edge.fromNode) &&
        current.nodes.some((node) => node.id === edge.toNode);

      if (hasEdge || hasSameConnection || !hasNodes || edge.fromNode === edge.toNode) {
        return current;
      }

      return commitCanvas({
        ...current,
        edges: [...current.edges, edge],
      });
    },
    [commitCanvas],
  );

  const removeEdge = useCallback(
    (edgeId: string): CanvasDocument => {
      const current = canvasRef.current;
      return commitCanvas({
        ...current,
        edges: current.edges.filter((edge) => edge.id !== edgeId),
      });
    },
    [commitCanvas],
  );

  const updateEdge = useCallback(
    (edgeId: string, patch: Partial<CanvasEdge>): CanvasDocument => {
      const current = canvasRef.current;
      if (!current.edges.some((edge) => edge.id === edgeId)) {
        return current;
      }
      return commitCanvas({
        ...current,
        edges: current.edges.map((edge) =>
          edge.id === edgeId ? { ...edge, ...patch, id: edge.id } : edge,
        ),
      });
    },
    [commitCanvas],
  );

  return {
    canvas,
    replaceCanvas,
    setCanvasDocument,
    recordHistorySnapshot,
    undoCanvas,
    redoCanvas,
    canUndo: historyCounts.past > 0,
    canRedo: historyCounts.future > 0,
    getCanvas,
    viewport,
    setViewport,
    selectedNodeId,
    setSelectedNodeId,
    selectedNodeIds,
    setSelectedNodeIds,
    selectedEdgeId,
    setSelectedEdgeId,
    isDraggingNode,
    setIsDraggingNode,
    isPanning,
    setIsPanning,
    addNode,
    updateNode,
    updateNodes,
    removeNode,
    removeNodes,
    addEdge,
    updateEdge,
    removeEdge,
  };
}
