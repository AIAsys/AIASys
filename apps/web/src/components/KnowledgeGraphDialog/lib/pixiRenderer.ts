import { BlurFilter, Container, Graphics, Text } from "pixi.js";
import type { GraphRenderNode } from "./graphConfig";
import type { GraphInteractionState } from "./graphInteractions";
import type { ForceLayoutState, ForceNode } from "./forceLayout";

const _haloBlurFilter = new BlurFilter({ strength: 8, quality: 2 });
const _emptyFilters: BlurFilter[] = [];

export interface PixiNodeView {
  node: GraphRenderNode;
  forceNode: ForceNode;
  root: Container;
  halo: Graphics;
  body: Graphics;
  label: Text;
}

export interface PixiEdgeView {
  id: string;
  sourceId: string;
  targetId: string;
  line: Graphics;
}

type Point = {
  x: number;
  y: number;
};

export function colorToNumber(color: string): number {
  return Number.parseInt(color.replace("#", ""), 16);
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

export function getNodeRadius(node: GraphRenderNode): number {
  return Math.max(10, node.data.size / 2);
}

export function getForceNodePosition(node: ForceNode): Point {
  return {
    x: typeof node.x === "number" ? node.x : 0,
    y: typeof node.y === "number" ? node.y : 0,
  };
}

export function createNodeViewGraphics(
  node: GraphRenderNode,
): { halo: Graphics; body: Graphics; label: Text } {
  const halo = new Graphics();
  const body = new Graphics();
  const label = new Text({
    text: node.data.label,
    anchor: { x: 0.5, y: 0 },
    style: {
      fontFamily: "Inter, system-ui, sans-serif",
      fontSize: 11,
      fontWeight: "600",
      fill: 0x0f172a,
      align: "center",
      wordWrap: true,
      wordWrapWidth: 160,
      lineHeight: 15,
      dropShadow: {
        color: 0xffffff,
        blur: 3,
        distance: 1,
        alpha: 0.92,
      },
    },
  });
  return { halo, body, label };
}

export function applyNodeViewStyle(
  nodeView: PixiNodeView,
  interactionState: GraphInteractionState,
  selectedNodeId: string | null,
  hoveredNodeId: string | null,
  sceneScale: number,
): void {
  const nodeId = nodeView.node.id;
  const isSelected = selectedNodeId === nodeId;
  const isHovered = hoveredNodeId === nodeId;
  const isMatched = interactionState.matchedNodeIds.has(nodeId);
  const isDimmed = interactionState.dimmedNodeIds.has(nodeId);
  const shouldShowLabel = isSelected || isHovered || isMatched || sceneScale >= 0.5;
  const radius = getNodeRadius(nodeView.node);
  const color = colorToNumber(nodeView.node.data.color);

  nodeView.root.alpha = isDimmed ? 0.22 : 1;
  nodeView.label.visible = shouldShowLabel;
  nodeView.label.alpha = isDimmed ? 0.3 : 1;

  nodeView.halo.clear();
  if (isSelected || isHovered || isMatched) {
    nodeView.halo
      .circle(0, 0, radius + (isSelected ? 11 : 8))
      .fill({
        color: isMatched ? 0x8b5cf6 : color,
        alpha: isSelected ? 0.22 : 0.16,
      });
    nodeView.halo.filters = [_haloBlurFilter];
  } else {
    nodeView.halo.filters = _emptyFilters;
  }

  nodeView.body.clear();
  nodeView.body
    .circle(0, 0, radius + 5)
    .fill({ color, alpha: isDimmed ? 0.1 : 0.18 })
    .circle(0, 0, radius)
    .fill({ color, alpha: 0.92 })
    .stroke({
      color: isSelected ? 0x111827 : isMatched ? 0x7c3aed : 0xcbd5e1,
      width: isSelected ? 2.6 : isMatched ? 2.2 : 1.2,
      alpha: isDimmed ? 0.32 : 0.92,
    });
}

export function renderGraphPositions(
  edgeViews: Map<string, PixiEdgeView>,
  nodeViews: Map<string, PixiNodeView>,
  forceLayout: ForceLayoutState | null,
): void {
  for (const edgeView of edgeViews.values()) {
    const source = forceLayout?.nodeById.get(edgeView.sourceId);
    const target = forceLayout?.nodeById.get(edgeView.targetId);
    if (!source || !target) {
      continue;
    }
    const sourcePosition = getForceNodePosition(source);
    const targetPosition = getForceNodePosition(target);
    edgeView.line.clear();
    edgeView.line
      .moveTo(sourcePosition.x, sourcePosition.y)
      .lineTo(targetPosition.x, targetPosition.y)
      .stroke({
        width: edgeView.line.alpha > 0.4 ? 1.55 : 1.05,
        color: 0x64748b,
        alpha: 1,
      });
  }

  for (const nodeView of nodeViews.values()) {
    const position = getForceNodePosition(nodeView.forceNode);
    nodeView.root.position.set(position.x, position.y);
    nodeView.label.position.set(
      position.x,
      position.y + getNodeRadius(nodeView.node) + 8,
    );
  }
}

export function applyEdgeVisualStates(
  edgeViews: Map<string, PixiEdgeView>,
  interactionState: GraphInteractionState,
): void {
  for (const edgeView of edgeViews.values()) {
    const isDimmed = interactionState.dimmedEdgeIds.has(edgeView.id);
    const isFocused = interactionState.focusEdgeIds.has(edgeView.id);
    const isSearch = interactionState.matchedEdgeIds.has(edgeView.id);
    edgeView.line.alpha = isDimmed ? 0.08 : isSearch ? 0.76 : isFocused ? 0.58 : 0.22;
  }
}
