export type CanvasNodeType = "text" | "file" | "link" | "group";
export type CanvasNodeSide = "top" | "right" | "bottom" | "left";
export type CanvasEdgeEnd = "none" | "arrow";
export type CanvasResizeHandle =
  | "nw"
  | "n"
  | "ne"
  | "e"
  | "se"
  | "s"
  | "sw"
  | "w";

export interface CanvasNode {
  id: string;
  type: CanvasNodeType;
  x: number;
  y: number;
  width: number;
  height: number;
  text?: string;
  file?: string;
  subpath?: string;
  url?: string;
  label?: string;
  color?: string | number;
  background?: string;
  backgroundStyle?: "cover" | "ratio" | "repeat";
  custom?: Record<string, unknown>;
}

export type CanvasNodeDraft = Omit<CanvasNode, "id" | "x" | "y">;

export interface CanvasEdge {
  id: string;
  fromNode: string;
  fromSide?: CanvasNodeSide;
  fromEnd?: CanvasEdgeEnd;
  toNode: string;
  toSide?: CanvasNodeSide;
  toEnd?: CanvasEdgeEnd;
  color?: string | number;
  label?: string;
  custom?: Record<string, unknown>;
}

export interface CanvasDocument {
  nodes: CanvasNode[];
  edges: CanvasEdge[];
  custom?: Record<string, unknown>;
}

export interface CanvasViewportState {
  x: number;
  y: number;
  scale: number;
}

export interface CanvasConnectionPreview {
  fromNodeId: string;
  fromSide: CanvasNodeSide;
  from: { x: number; y: number };
  to: { x: number; y: number };
  targetNodeId?: string;
}

export interface CanvasSelectionBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CanvasAlignmentGuide {
  orientation: "horizontal" | "vertical";
  position: number;
}

export const EMPTY_CANVAS_DOCUMENT: CanvasDocument = {
  nodes: [],
  edges: [],
};
