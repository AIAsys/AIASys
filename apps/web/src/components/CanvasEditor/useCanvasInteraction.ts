import { useCallback, useRef, useState } from "react";
import {
  createCanvasId,
  findNodeAtPoint,
  getBestConnectionSides,
  getNodeCenter,
  getNodeSidePoint,
  nodeIntersectsSelectionBox,
  normalizeCanvasSelectionBox,
} from "./canvasUtils";
import type {
  CanvasAlignmentGuide,
  CanvasConnectionPreview,
  CanvasDocument,
  CanvasEdge,
  CanvasNode,
  CanvasNodeSide,
  CanvasResizeHandle,
  CanvasSelectionBox,
  CanvasViewportState,
} from "./types";

const MIN_CANVAS_SCALE = 0.16;
const MAX_CANVAS_SCALE = 3;

interface UseCanvasInteractionOptions {
  canvas: CanvasDocument;
  selectedNodeIds: string[];
  viewport: CanvasViewportState;
  viewportRef: React.RefObject<HTMLDivElement | null>;
  setViewport: React.Dispatch<React.SetStateAction<CanvasViewportState>>;
  setSelectedNodeId: (id: string | null) => void;
  setSelectedNodeIds: (ids: string[]) => void;
  setSelectedEdgeId: (id: string | null) => void;
  setIsDraggingNode: (value: boolean) => void;
  setIsPanning: (value: boolean) => void;
  isSpacePanning: boolean;
  getCanvas: () => CanvasDocument;
  recordHistorySnapshot: () => void;
  updateNode: (nodeId: string, patch: Partial<CanvasNode>) => CanvasDocument;
  updateNodes: (patches: Record<string, Partial<CanvasNode>>) => CanvasDocument;
  addNode: (node: CanvasNode) => CanvasDocument;
  addEdge: (edge: CanvasEdge) => CanvasDocument;
  onSave?: (canvas: CanvasDocument) => void | Promise<void>;
}

function getNodeMinSize(node: CanvasNode): { width: number; height: number } {
  if (node.type === "group") {
    return { width: 220, height: 140 };
  }
  if (node.type === "file") {
    return { width: 180, height: 104 };
  }
  return { width: 160, height: 80 };
}

function buildResizePatch(
  node: CanvasNode,
  handle: CanvasResizeHandle,
  dx: number,
  dy: number,
): Partial<CanvasNode> {
  const minSize = getNodeMinSize(node);
  let x = node.x;
  let y = node.y;
  let width = node.width;
  let height = node.height;

  if (handle.includes("e")) {
    width = Math.max(minSize.width, node.width + dx);
  }
  if (handle.includes("s")) {
    height = Math.max(minSize.height, node.height + dy);
  }
  if (handle.includes("w")) {
    width = Math.max(minSize.width, node.width - dx);
    x = node.x + (node.width - width);
  }
  if (handle.includes("n")) {
    height = Math.max(minSize.height, node.height - dy);
    y = node.y + (node.height - height);
  }

  return { x, y, width, height };
}

function getNodeGuidePoints(node: CanvasNode) {
  return {
    x: [node.x, node.x + node.width / 2, node.x + node.width],
    y: [node.y, node.y + node.height / 2, node.y + node.height],
  };
}

function getContainedNodeIds(nodes: CanvasNode[], groupNode: CanvasNode): string[] {
  if (groupNode.type !== "group") {
    return [];
  }

  return nodes
    .filter((node) => {
      if (node.id === groupNode.id || node.type === "group") {
        return false;
      }
      const center = getNodeCenter(node);
      return (
        center.x >= groupNode.x &&
        center.x <= groupNode.x + groupNode.width &&
        center.y >= groupNode.y &&
        center.y <= groupNode.y + groupNode.height
      );
    })
    .map((node) => node.id);
}

function uniqueNodeIds(ids: string[]): string[] {
  return Array.from(new Set(ids.filter(Boolean)));
}

function normalizeWheelDelta(event: Pick<WheelEvent, "deltaMode" | "deltaY">) {
  if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
    return event.deltaY * 16;
  }
  if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
    return event.deltaY * 800;
  }
  return event.deltaY;
}

function getWheelScaleFactor(deltaY: number): number {
  if (deltaY === 0) {
    return 1;
  }
  const normalizedDelta = Math.min(Math.max(Math.abs(deltaY), 16), 240);
  const factor = 1.1 ** (normalizedDelta / 100);
  return deltaY > 0 ? 1 / factor : factor;
}

function resolveDragSnap(
  currentNodes: CanvasNode[],
  draggedNodes: CanvasNode[],
  dx: number,
  dy: number,
): {
  dx: number;
  dy: number;
  guides: CanvasAlignmentGuide[];
} {
  const draggedIds = new Set(draggedNodes.map((node) => node.id));
  const stationaryNodes = currentNodes.filter((node) => !draggedIds.has(node.id));
  if (draggedNodes.length === 0 || stationaryNodes.length === 0) {
    return { dx, dy, guides: [] };
  }

  const threshold = 8;
  let snapXOffset = 0;
  let snapXDistance = Number.POSITIVE_INFINITY;
  let snapXPosition: number | null = null;
  let snapYOffset = 0;
  let snapYDistance = Number.POSITIVE_INFINITY;
  let snapYPosition: number | null = null;

  const stationaryX = stationaryNodes.flatMap((node) => getNodeGuidePoints(node).x);
  const stationaryY = stationaryNodes.flatMap((node) => getNodeGuidePoints(node).y);

  draggedNodes.forEach((node) => {
    const proposedNode = { ...node, x: node.x + dx, y: node.y + dy };
    const draggedPoints = getNodeGuidePoints(proposedNode);

    draggedPoints.x.forEach((source) => {
      stationaryX.forEach((target) => {
        const offset = target - source;
        const distance = Math.abs(offset);
        if (distance <= threshold && distance < snapXDistance) {
          snapXOffset = offset;
          snapXDistance = distance;
          snapXPosition = target;
        }
      });
    });

    draggedPoints.y.forEach((source) => {
      stationaryY.forEach((target) => {
        const offset = target - source;
        const distance = Math.abs(offset);
        if (distance <= threshold && distance < snapYDistance) {
          snapYOffset = offset;
          snapYDistance = distance;
          snapYPosition = target;
        }
      });
    });
  });

  const guides: CanvasAlignmentGuide[] = [];
  if (snapXPosition !== null) {
    guides.push({ orientation: "vertical", position: snapXPosition });
  }
  if (snapYPosition !== null) {
    guides.push({ orientation: "horizontal", position: snapYPosition });
  }

  return {
    dx: dx + (snapXPosition !== null ? snapXOffset : 0),
    dy: dy + (snapYPosition !== null ? snapYOffset : 0),
    guides,
  };
}

export function useCanvasInteraction(options: UseCanvasInteractionOptions) {
  const {
    selectedNodeIds,
    viewport,
    viewportRef,
    setViewport,
    setSelectedNodeId,
    setSelectedNodeIds,
    setSelectedEdgeId,
    setIsDraggingNode,
    setIsPanning,
    isSpacePanning,
    getCanvas,
    recordHistorySnapshot,
    updateNode,
    updateNodes,
    addNode,
    addEdge,
    onSave,
  } = options;

  const [connectionPreview, setConnectionPreview] =
    useState<CanvasConnectionPreview | null>(null);
  const [selectionBox, setSelectionBox] = useState<CanvasSelectionBox | null>(null);
  const [alignmentGuides, setAlignmentGuides] = useState<CanvasAlignmentGuide[]>([]);
  const dragRef = useRef<{
    nodeIds: string[];
    startX: number;
    startY: number;
    originals: Record<string, { x: number; y: number }>;
    hasMoved: boolean;
    historyRecorded: boolean;
  } | null>(null);
  const resizeRef = useRef<{
    nodeId: string;
    handle: CanvasResizeHandle;
    startX: number;
    startY: number;
    original: CanvasNode;
    hasResized: boolean;
    historyRecorded: boolean;
  } | null>(null);
  const selectionRef = useRef<{
    startClientX: number;
    startClientY: number;
    start: { x: number; y: number };
    additive: boolean;
  } | null>(null);
  const panRef = useRef<{
    startX: number;
    startY: number;
    origVx: number;
    origVy: number;
  } | null>(null);
  const connectionRef = useRef<{
    fromNodeId: string;
    fromSide: CanvasNodeSide;
  } | null>(null);

  const startPan = useCallback(
    (event: React.PointerEvent) => {
      event.preventDefault();
      const target = event.currentTarget as HTMLElement;
      target.setPointerCapture?.(event.pointerId);
      setIsPanning(true);
      panRef.current = {
        startX: event.clientX,
        startY: event.clientY,
        origVx: viewport.x,
        origVy: viewport.y,
      };
    },
    [setIsPanning, viewport.x, viewport.y],
  );

  const clientToCanvas = useCallback(
    (clientX: number, clientY: number) => {
      const rect = viewportRef.current?.getBoundingClientRect();
      if (!rect) {
        return { x: 0, y: 0 };
      }
      return {
        x: (clientX - rect.left - viewport.x) / viewport.scale,
        y: (clientY - rect.top - viewport.y) / viewport.scale,
      };
    },
    [viewport, viewportRef],
  );

  const saveCanvas = useCallback(
    (next: CanvasDocument) => {
      void onSave?.(next);
    },
    [onSave],
  );

  const zoomAtClientPoint = useCallback(
    (clientX: number, clientY: number, deltaY: number) => {
      const rect = viewportRef.current?.getBoundingClientRect();
      if (!rect) {
        return;
      }

      const mouseX = clientX - rect.left;
      const mouseY = clientY - rect.top;
      const scaleFactor = getWheelScaleFactor(deltaY);

      setViewport((current) => {
        const nextScale = Math.min(
          Math.max(current.scale * scaleFactor, MIN_CANVAS_SCALE),
          MAX_CANVAS_SCALE,
        );
        if (nextScale === current.scale) {
          return current;
        }

        const scaleRatio = nextScale / current.scale;
        return {
          x: mouseX - (mouseX - current.x) * scaleRatio,
          y: mouseY - (mouseY - current.y) * scaleRatio,
          scale: nextScale,
        };
      });
    },
    [setViewport, viewportRef],
  );

  const handleNodePointerDown = useCallback(
    (event: React.PointerEvent, nodeId: string) => {
      if (event.button !== 0 && event.button !== 1) {
        return;
      }

      event.stopPropagation();

      if (event.button === 1 || event.altKey || isSpacePanning) {
        startPan(event);
        return;
      }

      const target = event.currentTarget as HTMLElement;
      target.setPointerCapture?.(event.pointerId);

      const current = getCanvas();
      const node = current.nodes.find((item) => item.id === nodeId);
      if (!node) {
        return;
      }

      setSelectedEdgeId(null);
      const isToggleSelect = event.metaKey || event.ctrlKey || event.shiftKey;
      const isAlreadySelected = selectedNodeIds.includes(nodeId);

      if (isToggleSelect) {
        const nextSelection = isAlreadySelected
          ? selectedNodeIds.filter((id) => id !== nodeId)
          : [...selectedNodeIds, nodeId];
        setSelectedNodeIds(nextSelection);
        return;
      }

      const dragNodeIds = isAlreadySelected && selectedNodeIds.length > 0
        ? selectedNodeIds
        : [nodeId];
      const nodeIdsToMove = uniqueNodeIds([
        ...dragNodeIds,
        ...getContainedNodeIds(current.nodes, node),
      ]);
      if (!isAlreadySelected || selectedNodeIds.length === 0) {
        setSelectedNodeIds([nodeId]);
      }

      const originals = Object.fromEntries(
        current.nodes
          .filter((item) => nodeIdsToMove.includes(item.id))
          .map((item) => [item.id, { x: item.x, y: item.y }]),
      );
      setIsDraggingNode(true);
      dragRef.current = {
        nodeIds: nodeIdsToMove,
        startX: event.clientX,
        startY: event.clientY,
        originals,
        hasMoved: false,
        historyRecorded: false,
      };
    },
    [
      getCanvas,
      isSpacePanning,
      selectedNodeIds,
      setIsDraggingNode,
      setSelectedEdgeId,
      setSelectedNodeIds,
      startPan,
    ],
  );

  const handleResizeHandlePointerDown = useCallback(
    (
      event: React.PointerEvent,
      nodeId: string,
      handle: CanvasResizeHandle,
    ) => {
      if (event.button !== 0) {
        return;
      }

      event.stopPropagation();
      const target = event.currentTarget as HTMLElement;
      target.setPointerCapture?.(event.pointerId);
      setSelectedNodeId(nodeId);
      setSelectedEdgeId(null);

      const node = getCanvas().nodes.find((item) => item.id === nodeId);
      if (!node) {
        return;
      }

      resizeRef.current = {
        nodeId,
        handle,
        startX: event.clientX,
        startY: event.clientY,
        original: node,
        hasResized: false,
        historyRecorded: false,
      };
    },
    [getCanvas, setSelectedEdgeId, setSelectedNodeId],
  );

  const handleConnectionHandlePointerDown = useCallback(
    (event: React.PointerEvent, nodeId: string, side: CanvasNodeSide) => {
      if (event.button !== 0) {
        return;
      }

      event.stopPropagation();
      const target = event.currentTarget as HTMLElement;
      target.setPointerCapture?.(event.pointerId);
      setSelectedNodeId(nodeId);
      setSelectedEdgeId(null);

      const node = getCanvas().nodes.find((item) => item.id === nodeId);
      if (!node) {
        return;
      }

      const from = getNodeSidePoint(node, side);
      const to = clientToCanvas(event.clientX, event.clientY);
      connectionRef.current = { fromNodeId: nodeId, fromSide: side };
      setConnectionPreview({ fromNodeId: nodeId, fromSide: side, from, to });
    },
    [clientToCanvas, getCanvas, setSelectedEdgeId, setSelectedNodeId],
  );

  const handleEdgePointerDown = useCallback(
    (event: React.PointerEvent, edgeId: string) => {
      event.stopPropagation();
      setSelectedEdgeId(edgeId);
      setSelectedNodeId(null);
    },
    [setSelectedEdgeId, setSelectedNodeId],
  );

  const handleBackgroundPointerDown = useCallback(
    (event: React.PointerEvent) => {
      if (event.button !== 0 && event.button !== 1) {
        return;
      }

      const target = event.currentTarget as HTMLElement;
      target.setPointerCapture?.(event.pointerId);

      if (event.button === 1 || event.altKey || isSpacePanning) {
        startPan(event);
        return;
      }

      const additive = event.shiftKey || event.metaKey || event.ctrlKey;
      if (!additive) {
        setSelectedNodeIds([]);
        setSelectedEdgeId(null);
      }
      selectionRef.current = {
        startClientX: event.clientX,
        startClientY: event.clientY,
        start: clientToCanvas(event.clientX, event.clientY),
        additive,
      };
      setSelectionBox(null);
    },
    [
      clientToCanvas,
      setSelectedEdgeId,
      setSelectedNodeIds,
      isSpacePanning,
      startPan,
    ],
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent) => {
      if (connectionRef.current) {
        const current = getCanvas();
        const connection = connectionRef.current;
        const fromNode = current.nodes.find(
          (node) => node.id === connection.fromNodeId,
        );
        if (!fromNode) {
          return;
        }
        const pointer = clientToCanvas(event.clientX, event.clientY);
        const targetNode = findNodeAtPoint(
          current.nodes,
          pointer,
          connection.fromNodeId,
        );
        const { toSide } = targetNode
          ? getBestConnectionSides(fromNode, targetNode)
          : { toSide: null };
        setConnectionPreview({
          fromNodeId: fromNode.id,
          fromSide: connection.fromSide,
          from: getNodeSidePoint(fromNode, connection.fromSide),
          to: targetNode && toSide ? getNodeSidePoint(targetNode, toSide) : pointer,
          targetNodeId: targetNode?.id,
        });
        return;
      }

      if (resizeRef.current) {
        const dx = (event.clientX - resizeRef.current.startX) / viewport.scale;
        const dy = (event.clientY - resizeRef.current.startY) / viewport.scale;
        const hasDelta = Math.abs(dx) >= 0.5 || Math.abs(dy) >= 0.5;
        if (hasDelta && !resizeRef.current.historyRecorded) {
          recordHistorySnapshot();
          resizeRef.current.historyRecorded = true;
        }
        if (!hasDelta && !resizeRef.current.hasResized) {
          return;
        }
        resizeRef.current.hasResized = true;
        const next = buildResizePatch(
          resizeRef.current.original,
          resizeRef.current.handle,
          dx,
          dy,
        );
        updateNode(resizeRef.current.nodeId, next);
        return;
      }

      if (dragRef.current) {
        const rawDx = (event.clientX - dragRef.current.startX) / viewport.scale;
        const rawDy = (event.clientY - dragRef.current.startY) / viewport.scale;
        const hasDelta = Math.abs(rawDx) >= 0.5 || Math.abs(rawDy) >= 0.5;
        if (hasDelta && !dragRef.current.historyRecorded) {
          recordHistorySnapshot();
          dragRef.current.historyRecorded = true;
        }
        if (!hasDelta && !dragRef.current.hasMoved) {
          return;
        }
        dragRef.current.hasMoved = true;
        const current = getCanvas();
        const draggedNodes = current.nodes
          .filter((node) => dragRef.current?.nodeIds.includes(node.id))
          .map((node) => {
            const original = dragRef.current?.originals[node.id];
            return original ? { ...node, x: original.x, y: original.y } : node;
          });
        const { dx, dy, guides } = resolveDragSnap(
          current.nodes,
          draggedNodes,
          rawDx,
          rawDy,
        );
        const patches: Record<string, Partial<CanvasNode>> = {};
        dragRef.current.nodeIds.forEach((nodeId) => {
          const original = dragRef.current?.originals[nodeId];
          if (original) {
            patches[nodeId] = { x: original.x + dx, y: original.y + dy };
          }
        });
        setAlignmentGuides(guides);
        updateNodes(patches);
        return;
      }

      if (selectionRef.current) {
        const dx = event.clientX - selectionRef.current.startClientX;
        const dy = event.clientY - selectionRef.current.startClientY;
        if (Math.abs(dx) < 3 && Math.abs(dy) < 3) {
          return;
        }
        const pointer = clientToCanvas(event.clientX, event.clientY);
        setSelectionBox(
          normalizeCanvasSelectionBox(selectionRef.current.start, pointer),
        );
        return;
      }

      if (panRef.current) {
        const dx = event.clientX - panRef.current.startX;
        const dy = event.clientY - panRef.current.startY;
        setViewport((current) => ({
          ...current,
          x: panRef.current ? panRef.current.origVx + dx : current.x,
          y: panRef.current ? panRef.current.origVy + dy : current.y,
        }));
      }
    },
    [
      clientToCanvas,
      getCanvas,
      recordHistorySnapshot,
      setViewport,
      updateNode,
      updateNodes,
      viewport.scale,
    ],
  );

  const handlePointerUp = useCallback(
    (event: React.PointerEvent) => {
      if (connectionRef.current) {
        const connection = connectionRef.current;
        const sourceId = connection.fromNodeId;
        const current = getCanvas();
        const pointer = clientToCanvas(event.clientX, event.clientY);
        const fromNode = current.nodes.find((node) => node.id === sourceId);
        const toNode = findNodeAtPoint(current.nodes, pointer, sourceId);

        if (fromNode && toNode && fromNode.id !== toNode.id) {
          const { toSide } = getBestConnectionSides(fromNode, toNode);
          recordHistorySnapshot();
          const next = addEdge({
            id: createCanvasId("edge"),
            fromNode: fromNode.id,
            fromSide: connection.fromSide,
            toNode: toNode.id,
            toSide,
            toEnd: "arrow",
          });
          saveCanvas(next);
        }

        connectionRef.current = null;
        setConnectionPreview(null);
        return;
      }

      if (resizeRef.current) {
        const shouldSave = resizeRef.current.hasResized;
        resizeRef.current = null;
        setAlignmentGuides([]);
        if (shouldSave) {
          saveCanvas(getCanvas());
        }
        return;
      }

      if (dragRef.current) {
        const shouldSave = dragRef.current.hasMoved;
        dragRef.current = null;
        setIsDraggingNode(false);
        setAlignmentGuides([]);
        if (shouldSave) {
          saveCanvas(getCanvas());
        }
        return;
      }

      if (selectionRef.current) {
        const selection = selectionRef.current;
        const dx = event.clientX - selection.startClientX;
        const dy = event.clientY - selection.startClientY;
        if (Math.abs(dx) >= 3 || Math.abs(dy) >= 3) {
          const box = normalizeCanvasSelectionBox(
            selection.start,
            clientToCanvas(event.clientX, event.clientY),
          );
          const selectedIds = getCanvas().nodes
            .filter((node) => nodeIntersectsSelectionBox(node, box))
            .map((node) => node.id);
          setSelectedNodeIds(
            selection.additive
              ? Array.from(new Set([...selectedNodeIds, ...selectedIds]))
              : selectedIds,
          );
          setSelectedEdgeId(null);
        }
        selectionRef.current = null;
        setSelectionBox(null);
        return;
      }

      if (panRef.current) {
        panRef.current = null;
        setIsPanning(false);
      }
    },
    [
      addEdge,
      clientToCanvas,
      getCanvas,
      recordHistorySnapshot,
      saveCanvas,
      selectedNodeIds,
      setIsDraggingNode,
      setIsPanning,
      setSelectedEdgeId,
      setSelectedNodeIds,
    ],
  );

  const handleWheel = useCallback(
    (event: React.WheelEvent) => {
      if (event.ctrlKey || event.metaKey) {
        return;
      }
      event.preventDefault();
      zoomAtClientPoint(
        event.clientX,
        event.clientY,
        normalizeWheelDelta(event.nativeEvent),
      );
    },
    [zoomAtClientPoint],
  );

  const handleNativeWheel = useCallback(
    (event: WheelEvent) => {
      if (!event.ctrlKey && !event.metaKey) {
        return;
      }
      event.preventDefault();
      event.stopPropagation();
      zoomAtClientPoint(
        event.clientX,
        event.clientY,
        normalizeWheelDelta(event),
      );
    },
    [zoomAtClientPoint],
  );

  const handleBackgroundDoubleClick = useCallback(
    (event: React.MouseEvent) => {
      const pos = clientToCanvas(event.clientX, event.clientY);
      recordHistorySnapshot();
      const next = addNode({
        id: createCanvasId("node"),
        type: "text",
        x: pos.x - 130,
        y: pos.y - 66,
        width: 260,
        height: 132,
        text: "新节点",
      });
      saveCanvas(next);
    },
    [addNode, clientToCanvas, recordHistorySnapshot, saveCanvas],
  );

  return {
      connectionPreview,
      selectionBox,
      alignmentGuides,
      clientToCanvas,
      handleNodePointerDown,
    handleResizeHandlePointerDown,
    handleConnectionHandlePointerDown,
    handleEdgePointerDown,
    handleBackgroundPointerDown,
    handlePointerMove,
    handlePointerUp,
    handleWheel,
    handleNativeWheel,
    handleBackgroundDoubleClick,
  };
}
