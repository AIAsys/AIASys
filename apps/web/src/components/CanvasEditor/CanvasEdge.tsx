import React from "react";
import {
  buildEdgePath,
  getCanvasStrokeColor,
  getNodeSidePoint,
} from "./canvasUtils";
import type { CanvasEdge, CanvasNode } from "./types";

interface CanvasEdgeProps {
  edge: CanvasEdge;
  nodes: CanvasNode[];
  isSelected: boolean;
  onPointerDown: (event: React.PointerEvent, edgeId: string) => void;
  onDoubleClick: (edgeId: string) => void;
  onContextMenu: (event: React.MouseEvent, edgeId: string) => void;
}

function getEdgeColor(color: string | number | undefined, isSelected: boolean): string {
  if (isSelected) {
    return "#2563EB";
  }
  return getCanvasStrokeColor(color);
}

function getArrowheadPoints(
  tail: { x: number; y: number },
  tip: { x: number; y: number },
): string | null {
  const angle = Math.atan2(tip.y - tail.y, tip.x - tail.x);
  if (!Number.isFinite(angle)) {
    return null;
  }

  const length = 11;
  const width = 7;
  const baseX = tip.x - Math.cos(angle) * length;
  const baseY = tip.y - Math.sin(angle) * length;
  const perpX = Math.cos(angle + Math.PI / 2) * (width / 2);
  const perpY = Math.sin(angle + Math.PI / 2) * (width / 2);

  return [
    `${tip.x},${tip.y}`,
    `${baseX + perpX},${baseY + perpY}`,
    `${baseX - perpX},${baseY - perpY}`,
  ].join(" ");
}

function formatEdgeLabel(label: string): string {
  const normalized = label.trim();
  if (normalized.length <= 28) {
    return normalized;
  }
  return `${normalized.slice(0, 27)}...`;
}

function getEdgeLabelWidth(label: string): number {
  const visualLength = Array.from(label).reduce((total, char) => {
    return total + (char.charCodeAt(0) > 255 ? 12 : 7);
  }, 18);
  return Math.max(44, Math.min(220, visualLength));
}

export const CanvasEdgeComponent: React.FC<CanvasEdgeProps> = React.memo(
  ({ edge, nodes, isSelected, onPointerDown, onDoubleClick, onContextMenu }) => {
    const fromNode = nodes.find((node) => node.id === edge.fromNode);
    const toNode = nodes.find((node) => node.id === edge.toNode);
    if (!fromNode || !toNode) {
      return null;
    }

    const from = getNodeSidePoint(fromNode, edge.fromSide || "right");
    const to = getNodeSidePoint(toNode, edge.toSide || "left");
    const midX = (from.x + to.x) / 2;
    const midY = (from.y + to.y) / 2;
    const d = buildEdgePath(from, to);
    const stroke = getEdgeColor(edge.color, isSelected);
    const toArrowPoints =
      edge.toEnd === "none" ? null : getArrowheadPoints(from, to);
    const fromArrowPoints =
      edge.fromEnd === "arrow" ? getArrowheadPoints(to, from) : null;
    const displayLabel = edge.label ? formatEdgeLabel(edge.label) : "";
    const labelWidth = displayLabel ? getEdgeLabelWidth(displayLabel) : 0;

    return (
      <g
        data-canvas-edge-id={edge.id}
        onContextMenu={(event) => onContextMenu(event, edge.id)}
      >
        <path
          d={d}
          fill="none"
          stroke="transparent"
          strokeLinecap="round"
          strokeWidth={14}
          className="cursor-pointer"
          role="button"
          aria-label={`选择连线 ${edge.label || edge.id}`}
          tabIndex={0}
          onPointerDown={(event) => onPointerDown(event, edge.id)}
          onDoubleClick={(event) => {
            event.stopPropagation();
            onDoubleClick(edge.id);
          }}
        />
        <path
          d={d}
          fill="none"
          stroke={stroke}
          strokeLinecap="round"
          strokeWidth={isSelected ? 2.5 : 1.7}
          className="pointer-events-none"
        />
        {toArrowPoints ? (
          <polygon points={toArrowPoints} fill={stroke} className="pointer-events-none" />
        ) : null}
        {fromArrowPoints ? (
          <polygon points={fromArrowPoints} fill={stroke} className="pointer-events-none" />
        ) : null}
        {displayLabel ? (
          <g
            className="cursor-pointer"
            onPointerDown={(event) => onPointerDown(event, edge.id)}
            onDoubleClick={(event) => {
              event.stopPropagation();
              onDoubleClick(edge.id);
            }}
            onContextMenu={(event) => onContextMenu(event, edge.id)}
          >
            <rect
              x={midX - labelWidth / 2}
              y={midY - 21}
              width={labelWidth}
              height={18}
              rx={5}
              fill="#FFFFFF"
              stroke="#E4E7EC"
            />
            <text
              x={midX}
              y={midY - 8}
              textAnchor="middle"
              className="pointer-events-none fill-slate-600 text-[11px] font-medium"
            >
              {displayLabel}
            </text>
          </g>
        ) : null}
      </g>
    );
  },
);
