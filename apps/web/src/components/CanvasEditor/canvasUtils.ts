import type {
  CanvasDocument,
  CanvasEdge,
  CanvasNode,
  CanvasNodeSide,
  CanvasSelectionBox,
} from "./types";

export { WORKSPACE_FILE_DRAG_MIME } from "@/utils/workspaceFileDrag";

export const CANVAS_COLOR_OPTIONS = [
  { value: "", label: "默认", hex: "#FFFFFF" },
  { value: "1", label: "红", hex: "#FEE4E2" },
  { value: "2", label: "橙", hex: "#FEF0C7" },
  { value: "3", label: "黄", hex: "#FEF7C3" },
  { value: "4", label: "绿", hex: "#CCFBF1" },
  { value: "5", label: "蓝", hex: "#D1E9FF" },
  { value: "6", label: "紫", hex: "#EDE9FE" },
] as const;

const CANVAS_COLOR_MAP: Record<string, string> = {
  "1": "#FEE4E2",
  "2": "#FEF0C7",
  "3": "#FEF7C3",
  "4": "#CCFBF1",
  "5": "#D1E9FF",
  "6": "#EDE9FE",
};

const CANVAS_STROKE_COLOR_MAP: Record<string, string> = {
  "1": "#B42318",
  "2": "#B54708",
  "3": "#B88200",
  "4": "#0F766E",
  "5": "#026AA2",
  "6": "#7C3AED",
};

interface CanvasLike {
  [key: string]: unknown;
  nodes?: unknown;
  edges?: unknown;
}

export function createCanvasId(prefix: "node" | "edge"): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function toNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

export function isCssColorValue(value: unknown): value is string {
  return (
    typeof value === "string" &&
    (/^#[0-9a-f]{3}([0-9a-f]{3})?$/i.test(value.trim()) ||
      /^rgba?\(/i.test(value.trim()) ||
      /^hsla?\(/i.test(value.trim()))
  );
}

export function getCanvasFillColor(color: string | number | undefined): string | null {
  const key = String(color || "");
  if (!key) {
    return null;
  }
  return CANVAS_COLOR_MAP[key] || (isCssColorValue(key) ? key : null);
}

export function getCanvasStrokeColor(color: string | number | undefined): string {
  const key = String(color || "");
  return CANVAS_STROKE_COLOR_MAP[key] || (isCssColorValue(key) ? key : "#667085");
}

export function getWorkspaceFileLabel(fileName: string): string {
  return fileName.split("/").filter(Boolean).pop() || fileName;
}

function normalizeNode(node: unknown): CanvasNode | null {
  if (!node || typeof node !== "object") {
    return null;
  }
  const source = node as Partial<CanvasNode>;
  if (!source.id || typeof source.id !== "string") {
    return null;
  }

  const type = source.type || "text";
  if (!["text", "file", "link", "group"].includes(type)) {
    return null;
  }

  return {
    ...source,
    id: source.id,
    type,
    x: toNumber(source.x, 0),
    y: toNumber(source.y, 0),
    width: toNumber(source.width, type === "group" ? 360 : 260),
    height: toNumber(source.height, type === "group" ? 220 : 132),
  };
}

function normalizeEdge(edge: unknown): CanvasEdge | null {
  if (!edge || typeof edge !== "object") {
    return null;
  }
  const source = edge as Partial<CanvasEdge>;
  if (
    !source.id ||
    typeof source.id !== "string" ||
    !source.fromNode ||
    typeof source.fromNode !== "string" ||
    !source.toNode ||
    typeof source.toNode !== "string"
  ) {
    return null;
  }

  return {
    ...source,
    id: source.id,
    fromNode: source.fromNode,
    toNode: source.toNode,
    toEnd: source.toEnd || "arrow",
  };
}

export function normalizeCanvasDocument(input: CanvasDocument | CanvasLike | null | undefined): CanvasDocument {
  const nodes: CanvasNode[] = [];
  const edges: CanvasEdge[] = [];
  const nodeIds = new Set<string>();
  const edgeIds = new Set<string>();
  const source =
    input && typeof input === "object"
      ? (input as Record<string, unknown>)
      : {};
  const rawNodes = Array.isArray(input?.nodes) ? input.nodes : [];
  const rawEdges = Array.isArray(input?.edges) ? input.edges : [];

  rawNodes.forEach((node) => {
    const normalized = normalizeNode(node);
    if (!normalized || nodeIds.has(normalized.id)) {
      return;
    }
    nodeIds.add(normalized.id);
    nodes.push(normalized);
  });

  rawEdges.forEach((edge) => {
    const normalized = normalizeEdge(edge);
    if (
      !normalized ||
      edgeIds.has(normalized.id) ||
      !nodeIds.has(normalized.fromNode) ||
      !nodeIds.has(normalized.toNode)
    ) {
      return;
    }
    edgeIds.add(normalized.id);
    edges.push(normalized);
  });

  return { ...source, nodes, edges };
}

export function parseCanvasContent(content?: string | null): {
  canvas: CanvasDocument;
  error: string | null;
} {
  if (!content?.trim()) {
    return { canvas: { nodes: [], edges: [] }, error: null };
  }

  try {
    const parsed = JSON.parse(content) as CanvasLike;
    return {
      canvas: normalizeCanvasDocument(parsed),
      error: null,
    };
  } catch {
    return {
      canvas: { nodes: [], edges: [] },
      error: "画布文件不是有效的 JSON，保存会写入新的标准画布内容。",
    };
  }
}

export function stringifyCanvasDocument(canvas: CanvasDocument): string {
  return `${JSON.stringify(normalizeCanvasDocument(canvas), null, 2)}\n`;
}

export function getNodeCenter(node: CanvasNode): { x: number; y: number } {
  return {
    x: node.x + node.width / 2,
    y: node.y + node.height / 2,
  };
}

export function getNodeSidePoint(
  node: CanvasNode,
  side: CanvasNodeSide,
): { x: number; y: number } {
  switch (side) {
    case "top":
      return { x: node.x + node.width / 2, y: node.y };
    case "right":
      return { x: node.x + node.width, y: node.y + node.height / 2 };
    case "bottom":
      return { x: node.x + node.width / 2, y: node.y + node.height };
    case "left":
      return { x: node.x, y: node.y + node.height / 2 };
  }
}

export function findNodeAtPoint(
  nodes: CanvasNode[],
  point: { x: number; y: number },
  ignoredNodeId?: string,
): CanvasNode | null {
  for (let index = nodes.length - 1; index >= 0; index -= 1) {
    const node = nodes[index];
    if (node.id === ignoredNodeId) {
      continue;
    }
    const isInside =
      point.x >= node.x &&
      point.x <= node.x + node.width &&
      point.y >= node.y &&
      point.y <= node.y + node.height;
    if (isInside) {
      return node;
    }
  }
  return null;
}

export function normalizeCanvasSelectionBox(
  start: { x: number; y: number },
  end: { x: number; y: number },
): CanvasSelectionBox {
  const x = Math.min(start.x, end.x);
  const y = Math.min(start.y, end.y);
  return {
    x,
    y,
    width: Math.abs(end.x - start.x),
    height: Math.abs(end.y - start.y),
  };
}

export function nodeIntersectsSelectionBox(
  node: CanvasNode,
  box: CanvasSelectionBox,
): boolean {
  const right = box.x + box.width;
  const bottom = box.y + box.height;
  const nodeRight = node.x + node.width;
  const nodeBottom = node.y + node.height;

  return node.x < right && nodeRight > box.x && node.y < bottom && nodeBottom > box.y;
}

export function getBestConnectionSides(
  fromNode: CanvasNode,
  toNode: CanvasNode,
): { fromSide: CanvasNodeSide; toSide: CanvasNodeSide } {
  const from = getNodeCenter(fromNode);
  const to = getNodeCenter(toNode);
  const dx = to.x - from.x;
  const dy = to.y - from.y;

  if (Math.abs(dx) >= Math.abs(dy)) {
    return dx >= 0
      ? { fromSide: "right", toSide: "left" }
      : { fromSide: "left", toSide: "right" };
  }

  return dy >= 0
    ? { fromSide: "bottom", toSide: "top" }
    : { fromSide: "top", toSide: "bottom" };
}

export function buildEdgePath(
  from: { x: number; y: number },
  to: { x: number; y: number },
): string {
  const dx = Math.abs(to.x - from.x);
  const dy = Math.abs(to.y - from.y);
  const controlOffset = Math.max(80, Math.min(260, Math.max(dx, dy) * 0.45));
  const direction = to.x >= from.x ? 1 : -1;
  const c1x = from.x + controlOffset * direction;
  const c2x = to.x - controlOffset * direction;
  return `M ${from.x} ${from.y} C ${c1x} ${from.y}, ${c2x} ${to.y}, ${to.x} ${to.y}`;
}
