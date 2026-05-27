import { useEffect, useMemo, useRef, useState } from "react";
import type { GraphVisualizationResponse } from "@/types/graphrag";
import { useContainerSize } from "./hooks/useContainerSize";
import { GraphControls } from "./components/GraphControls";
import {
  buildGraphData,
  normalizeLayoutMode,
  type LayoutMode,
} from "./lib/graphConfig";
import { findFirstMatchedNodeId } from "./lib/graphInteractions";
import {
  PixiGraphController,
  type PixiGraphViewport,
} from "./lib/pixiGraph";

export type { LayoutMode };

interface PixiExplorerProps {
  data: GraphVisualizationResponse;
  selectedNodeId: string | null;
  searchQuery: string;
  layoutMode: LayoutMode;
  onSelectNode: (nodeId: string | null) => void;
}

export function PixiExplorer({
  data,
  selectedNodeId,
  searchQuery,
  layoutMode,
  onSelectNode,
}: PixiExplorerProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const controllerRef = useRef<PixiGraphController | null>(null);
  const viewportRef = useRef<PixiGraphViewport | null>(null);
  const [graphReady, setGraphReady] = useState(false);
  const size = useContainerSize(containerRef);

  const graphData = useMemo(() => buildGraphData(data), [data]);
  const normalizedLayoutMode = normalizeLayoutMode(layoutMode);

  useEffect(() => {
    return () => {
      controllerRef.current?.destroy();
      controllerRef.current = null;
      viewportRef.current = null;
    };
  }, []);

  useEffect(() => {
    const currentContainer = containerRef.current;
    if (!currentContainer || size.width <= 0 || size.height <= 0) {
      return;
    }

    let cancelled = false;
    const container = currentContainer;

    async function initController() {
      if (controllerRef.current) {
        controllerRef.current.setSize(size);
        return;
      }

      const controller = await PixiGraphController.create({
        container,
        data: graphData,
        size,
        selectedNodeId,
        searchQuery,
        onSelectNode,
      });

      if (cancelled) {
        controller.destroy();
        return;
      }

      controllerRef.current = controller;
      viewportRef.current = controller;
      setGraphReady(true);
    }

    void initController();

    return () => {
      cancelled = true;
    };
  }, [graphData, onSelectNode, searchQuery, selectedNodeId, size]);

  useEffect(() => {
    controllerRef.current?.setData(graphData);
  }, [graphData, normalizedLayoutMode]);

  useEffect(() => {
    controllerRef.current?.setSize(size);
  }, [size]);

  useEffect(() => {
    const controller = controllerRef.current;
    if (!controller) {
      return;
    }

    controller.setInteractionState(selectedNodeId, searchQuery);

    if (selectedNodeId) {
      controller.focusNode(selectedNodeId);
      return;
    }

    const firstMatchedNodeId = findFirstMatchedNodeId(graphData, searchQuery);
    if (firstMatchedNodeId) {
      controller.focusNode(firstMatchedNodeId);
    }
  }, [graphData, searchQuery, selectedNodeId]);

  return (
    <div className="relative h-full w-full overflow-hidden">
      <div
        ref={containerRef}
        className="h-full w-full bg-card"
      />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(15,23,42,0.035)_1px,transparent_1px),linear-gradient(90deg,rgba(15,23,42,0.03)_1px,transparent_1px)] bg-[size:42px_42px] opacity-70" />
      <GraphControls graphRef={viewportRef} graphReady={graphReady} />
    </div>
  );
}
