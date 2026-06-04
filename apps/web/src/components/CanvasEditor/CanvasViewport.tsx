import React, { useMemo } from "react";
import {
  buildEdgePath,
  getCanvasFillColor,
  getCanvasStrokeColor,
  getNodeCenter,
} from "./canvasUtils";
import { CanvasNodeComponent } from "./CanvasNode";
import { CanvasEdgeComponent } from "./CanvasEdge";
import type {
  CanvasAlignmentGuide,
  CanvasConnectionPreview,
  CanvasDocument,
  CanvasNodeSide,
  CanvasResizeHandle,
  CanvasSelectionBox,
  CanvasViewportState,
} from "./types";
import type { WorkspaceMarkdownLinkScope } from "@/utils/workspaceMarkdownLinks";

interface CanvasViewportProps {
  canvas: CanvasDocument;
  viewport: CanvasViewportState;
  viewportRef: React.RefObject<HTMLDivElement | null>;
  selectedNodeIds: string[];
  selectedEdgeId: string | null;
  editingNodeId: string | null;
  editValue: string;
  connectionPreview: CanvasConnectionPreview | null;
  selectionBox: CanvasSelectionBox | null;
  alignmentGuides: CanvasAlignmentGuide[];
  isPanning: boolean;
  isSpacePanning: boolean;
  onEditValueChange: (value: string) => void;
  getFileUrl?: (fileName: string) => string;
  onOpenLink: (url: string) => void;
  onOpenFile: (
    fileName: string,
    options?: { scope?: WorkspaceMarkdownLinkScope; suffix?: string },
  ) => void;
  onNodePointerDown: (event: React.PointerEvent, nodeId: string) => void;
  onConnectionHandlePointerDown: (
    event: React.PointerEvent,
    nodeId: string,
    side: CanvasNodeSide,
  ) => void;
  onResizeHandlePointerDown: (
    event: React.PointerEvent,
    nodeId: string,
    handle: CanvasResizeHandle,
  ) => void;
  onNodeContextMenu: (event: React.MouseEvent, nodeId: string) => void;
  onNodeDoubleClick: (nodeId: string) => void;
  onEdgePointerDown: (event: React.PointerEvent, edgeId: string) => void;
  onEdgeDoubleClick: (edgeId: string) => void;
  onEdgeContextMenu: (event: React.MouseEvent, edgeId: string) => void;
  onBackgroundPointerDown: (event: React.PointerEvent) => void;
  onBackgroundDoubleClick: (event: React.MouseEvent) => void;
  onWheel: (event: React.WheelEvent) => void;
  onDragOver: (event: React.DragEvent) => void;
  onDrop: (event: React.DragEvent) => void;
  onEditCommit: () => void;
  onEditCancel: () => void;
}

export const CanvasViewport: React.FC<CanvasViewportProps> = ({
  canvas,
  viewport,
  viewportRef,
  selectedNodeIds,
  selectedEdgeId,
  editingNodeId,
  editValue,
  connectionPreview,
  selectionBox,
  alignmentGuides,
  isPanning,
  isSpacePanning,
  onEditValueChange,
  getFileUrl,
  onOpenLink,
  onOpenFile,
  onNodePointerDown,
  onConnectionHandlePointerDown,
  onResizeHandlePointerDown,
  onNodeContextMenu,
  onNodeDoubleClick,
  onEdgePointerDown,
  onEdgeDoubleClick,
  onEdgeContextMenu,
  onBackgroundPointerDown,
  onBackgroundDoubleClick,
  onWheel,
  onDragOver,
  onDrop,
  onEditCommit,
  onEditCancel,
}) => {
  const nodes = canvas.nodes;
  const edges = canvas.edges;
  const transform = useMemo(
    () => `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`,
    [viewport],
  );
  const miniMap = useMemo(() => {
    if (nodes.length === 0) {
      return null;
    }

    const nodeById = new Map(nodes.map((node) => [node.id, node]));
    const minX = Math.min(...nodes.map((node) => node.x));
    const minY = Math.min(...nodes.map((node) => node.y));
    const maxX = Math.max(...nodes.map((node) => node.x + node.width));
    const maxY = Math.max(...nodes.map((node) => node.y + node.height));
    const padding = 96;
    const viewWidth = 168;
    const viewHeight = 108;
    const bounds = {
      x: minX - padding,
      y: minY - padding,
      width: Math.max(1, maxX - minX + padding * 2),
      height: Math.max(1, maxY - minY + padding * 2),
    };
    const scale = Math.min(
      (viewWidth - 12) / bounds.width,
      (viewHeight - 12) / bounds.height,
    );
    const offsetX = (viewWidth - bounds.width * scale) / 2;
    const offsetY = (viewHeight - bounds.height * scale) / 2;
    const project = (point: { x: number; y: number }) => ({
      x: offsetX + (point.x - bounds.x) * scale,
      y: offsetY + (point.y - bounds.y) * scale,
    });

    return {
      nodeById,
      project,
      scale,
      width: viewWidth,
      height: viewHeight,
    };
  }, [nodes]);

  return (
    <div
      ref={viewportRef}
      data-canvas-viewport
      className={[
        "relative h-full w-full overflow-hidden bg-[#F6F7FA] bg-[linear-gradient(#E4E7EC_1px,transparent_1px),linear-gradient(90deg,#E4E7EC_1px,transparent_1px)] bg-[size:32px_32px] text-slate-950",
        isPanning ? "cursor-grabbing" : isSpacePanning ? "cursor-grab" : "",
      ].join(" ")}
      onPointerDown={onBackgroundPointerDown}
      onDoubleClick={onBackgroundDoubleClick}
      onWheel={onWheel}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_20%,rgba(37,99,235,0.10),transparent_25%),radial-gradient(circle_at_78%_72%,rgba(15,118,110,0.08),transparent_28%),linear-gradient(180deg,rgba(255,255,255,0.76),rgba(246,247,250,0.70))]" />
      <div
        className="absolute left-0 top-0"
        style={{
          transform,
          transformOrigin: "0 0",
          width: 1,
          height: 1,
        }}
      >
        <svg className="absolute left-0 top-0 h-px w-px overflow-visible">
          {edges.map((edge) => (
            <CanvasEdgeComponent
              key={edge.id}
              edge={edge}
              nodes={nodes}
              isSelected={selectedEdgeId === edge.id}
              onPointerDown={onEdgePointerDown}
              onDoubleClick={onEdgeDoubleClick}
              onContextMenu={onEdgeContextMenu}
            />
          ))}

          {connectionPreview ? (
            <path
              d={buildEdgePath(connectionPreview.from, connectionPreview.to)}
              fill="none"
              stroke="#2563EB"
              strokeDasharray="6 6"
              strokeLinecap="round"
              strokeWidth={2}
            />
          ) : null}
        </svg>

        {nodes.map((node) => (
          <CanvasNodeComponent
            key={node.id}
            node={node}
            isEditing={editingNodeId === node.id}
            isSelected={selectedNodeIds.includes(node.id)}
            isConnectionTarget={connectionPreview?.targetNodeId === node.id}
            isSpacePanning={isSpacePanning || isPanning}
            showConnectionHandles={Boolean(
              selectedNodeIds.includes(node.id) ||
                connectionPreview ||
                editingNodeId === null,
            )}
            editValue={editingNodeId === node.id ? editValue : ""}
            getFileUrl={getFileUrl}
            onOpenLink={onOpenLink}
            onOpenFile={onOpenFile}
            onEditValueChange={onEditValueChange}
            onPointerDown={onNodePointerDown}
            onConnectionHandlePointerDown={onConnectionHandlePointerDown}
            onResizeHandlePointerDown={onResizeHandlePointerDown}
            onContextMenu={onNodeContextMenu}
            onDoubleClick={onNodeDoubleClick}
            onEditCommit={onEditCommit}
            onEditCancel={onEditCancel}
          />
        ))}

        {selectionBox ? (
          <div
            className="pointer-events-none absolute border border-blue-500 bg-blue-500/10"
            style={{
              left: selectionBox.x,
              top: selectionBox.y,
              width: selectionBox.width,
              height: selectionBox.height,
            }}
          />
        ) : null}

        {alignmentGuides.map((guide) =>
          guide.orientation === "vertical" ? (
            <div
              key={`${guide.orientation}-${guide.position}`}
              className="pointer-events-none absolute top-[-100000px] h-[200000px] w-px bg-blue-500/80 shadow-[0_0_0_1px_rgba(37,99,235,0.14)]"
              style={{ left: guide.position }}
            />
          ) : (
            <div
              key={`${guide.orientation}-${guide.position}`}
              className="pointer-events-none absolute left-[-100000px] h-px w-[200000px] bg-blue-500/80 shadow-[0_0_0_1px_rgba(37,99,235,0.14)]"
              style={{ top: guide.position }}
            />
          ),
        )}
      </div>

      {miniMap ? (
        <div className="pointer-events-none absolute bottom-3 left-3 z-10 overflow-hidden rounded-lg border border-slate-200 bg-white/88 shadow-sm backdrop-blur">
          <svg
            width={miniMap.width}
            height={miniMap.height}
            viewBox={`0 0 ${miniMap.width} ${miniMap.height}`}
            className="block"
          >
            <rect
              x="0"
              y="0"
              width={miniMap.width}
              height={miniMap.height}
              rx="8"
              fill="#F8FAFC"
            />
            {edges.map((edge) => {
              const fromNode = miniMap.nodeById.get(edge.fromNode);
              const toNode = miniMap.nodeById.get(edge.toNode);
              if (!fromNode || !toNode) {
                return null;
              }
              const from = miniMap.project(getNodeCenter(fromNode));
              const to = miniMap.project(getNodeCenter(toNode));
              return (
                <line
                  key={edge.id}
                  x1={from.x}
                  y1={from.y}
                  x2={to.x}
                  y2={to.y}
                  stroke={getCanvasStrokeColor(edge.color)}
                  strokeLinecap="round"
                  strokeWidth="1.2"
                  opacity="0.5"
                />
              );
            })}
            {nodes.map((node) => {
              const point = miniMap.project({ x: node.x, y: node.y });
              const fill =
                getCanvasFillColor(node.color) ||
                (node.type === "group" ? "#F1F5F9" : "#FFFFFF");
              return (
                <rect
                  key={node.id}
                  x={point.x}
                  y={point.y}
                  width={Math.max(4, node.width * miniMap.scale)}
                  height={Math.max(3, node.height * miniMap.scale)}
                  rx="2"
                  fill={fill}
                  stroke={node.type === "group" ? "#94A3B8" : "#CBD5E1"}
                  strokeWidth="1"
                  opacity={node.type === "group" ? 0.64 : 0.92}
                />
              );
            })}
          </svg>
          <div className="border-t border-slate-200 bg-white/70 px-2 py-1 text-[10px] font-medium text-slate-500">
            {nodes.length} 节点 / {edges.length} 连线
          </div>
        </div>
      ) : null}

      {isPanning ? (
        <div className="pointer-events-none absolute bottom-36 left-3 rounded-md border border-slate-200 bg-white/85 px-2.5 py-1 text-[11px] font-medium text-slate-500 shadow-sm backdrop-blur">
          正在移动画布
        </div>
      ) : null}
    </div>
  );
};
