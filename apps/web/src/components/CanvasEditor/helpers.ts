import type { CanvasNode } from "./types";
import { isImageFile } from "@/utils/fileTreeUtils";

export function getEditableNodeText(node: CanvasNode): string {
  if (node.type === "file") {
    return node.file || "";
  }
  if (node.type === "link") {
    return node.url || "";
  }
  if (node.type === "group") {
    return node.label === "分组框" ? "分组" : node.label || "";
  }
  return node.text || "";
}

export function buildNodeTextPatch(
  node: CanvasNode,
  value: string,
): Partial<CanvasNode> {
  if (node.type === "file") {
    return { file: value };
  }
  if (node.type === "link") {
    return { url: value };
  }
  if (node.type === "group") {
    return { label: value };
  }
  return { text: value };
}

export function getFileNodeSize(
  fileName: string,
): { width: number; height: number } {
  return isImageFile(fileName)
    ? { width: 320, height: 220 }
    : { width: 300, height: 154 };
}

export function getContextMenuPosition(
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  const viewportWidth =
    typeof window === "undefined" ? 1024 : window.innerWidth;
  const viewportHeight =
    typeof window === "undefined" ? 768 : window.innerHeight;
  return {
    x: Math.min(Math.max(8, clientX), Math.max(8, viewportWidth - 272)),
    y: Math.min(Math.max(8, clientY), Math.max(8, viewportHeight - 420)),
  };
}

export function normalizeCanvasLinkUrl(rawUrl: string): string | null {
  const trimmed = rawUrl.trim();
  if (!trimmed || trimmed === "https://") {
    return null;
  }

  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;

  try {
    const parsed = new URL(candidate);
    return ["http:", "https:", "mailto:"].includes(parsed.protocol)
      ? parsed.toString()
      : null;
  } catch {
    return null;
  }
}

export function isKeyboardEditingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  const tagName = target.tagName.toLowerCase();
  return (
    tagName === "input" ||
    tagName === "textarea" ||
    tagName === "select" ||
    target.isContentEditable
  );
}

export function isCanvasControlTarget(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    Boolean(target.closest("button,input,textarea,select,[role='menuitem']"))
  );
}

export function clampNumber(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function countTextChars(text: string): number {
  return Array.from(text).length;
}

export function getPastedTextNodeSize(
  text: string,
): { width: number; height: number } {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const longestLine = Math.max(0, ...lines.map((line) => countTextChars(line)));
  const width = clampNumber(Math.round(longestLine * 8 + 40), 260, 560);
  const wrapChars = Math.max(18, Math.floor((width - 40) / 8));
  const visualLineCount = lines.reduce(
    (count, line) =>
      count + Math.max(1, Math.ceil(countTextChars(line) / wrapChars)),
    0,
  );

  return {
    width,
    height: clampNumber(visualLineCount * 22 + 42, 112, 360),
  };
}

export function clipboardHasFiles(clipboardData: DataTransfer): boolean {
  return (
    Array.from(clipboardData.files ?? []).length > 0 ||
    Array.from(clipboardData.items ?? []).some((item) => item.kind === "file")
  );
}
