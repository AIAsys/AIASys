import React, { Suspense, useCallback, useMemo } from "react";
import {
  ExternalLink,
  FileText,
  Image as ImageIcon,
  Link2,
  Maximize2,
  SquareDashed,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { createWorkspaceMarkdownComponents } from "@/components/markdown/WorkspaceMarkdownComponents";
import { isImageFile } from "@/utils/fileTreeUtils";
import type { WorkspaceMarkdownLinkScope } from "@/utils/workspaceMarkdownLinks";
import { getCanvasFillColor, getWorkspaceFileLabel } from "./canvasUtils";
import type { CanvasNode, CanvasNodeSide, CanvasResizeHandle } from "./types";

interface CanvasNodeProps {
  node: CanvasNode;
  isEditing: boolean;
  isSelected: boolean;
  isConnectionTarget: boolean;
  isSpacePanning: boolean;
  showConnectionHandles: boolean;
  editValue: string;
  getFileUrl?: (fileName: string) => string;
  onEditValueChange: (value: string) => void;
  onPointerDown: (event: React.PointerEvent, nodeId: string) => void;
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
  onContextMenu: (event: React.MouseEvent, nodeId: string) => void;
  onDoubleClick: (nodeId: string) => void;
  onOpenLink: (url: string) => void;
  onOpenFile: (
    fileName: string,
    options?: { scope?: WorkspaceMarkdownLinkScope; suffix?: string },
  ) => void;
  onEditCommit: () => void;
  onEditCancel: () => void;
}

const nodeColorClasses: Record<string, string> = {
  "1": "border-red-200 dark:border-red-800 text-red-950 dark:text-red-200",
  "2": "border-orange-200 dark:border-orange-800 text-orange-950 dark:text-orange-200",
  "3": "border-yellow-200 dark:border-yellow-800 text-yellow-950 dark:text-yellow-200",
  "4": "border-teal-200 dark:border-teal-800 text-teal-950 dark:text-teal-200",
  "5": "border-sky-200 dark:border-sky-800 text-sky-950 dark:text-sky-200",
  "6": "border-violet-200 dark:border-violet-800 text-violet-950 dark:text-violet-200",
};

function getNodeDisplayText(node: CanvasNode): string {
  if (node.type === "file") {
    return node.file || "未选择文件";
  }
  if (node.type === "link") {
    return node.url || "未填写链接";
  }
  if (node.type === "group") {
    return !node.label || node.label === "分组框" ? "分组" : node.label;
  }
  return node.text || "";
}

function getNodeTypeLabel(node: CanvasNode): string {
  if (node.type === "file") {
    return "文件";
  }
  if (node.type === "link") {
    return "链接";
  }
  if (node.type === "group") {
    return "分组";
  }
  return "文本";
}

function getNodeIcon(node: CanvasNode) {
  if (node.type === "file") {
    return node.file && isImageFile(node.file) ? ImageIcon : FileText;
  }
  if (node.type === "link") {
    return Link2;
  }
  if (node.type === "group") {
    return SquareDashed;
  }
  return null;
}

function getFileExtensionLabel(fileName: string): string {
  const extension = fileName.split(".").pop()?.trim();
  return extension ? extension.slice(0, 6).toUpperCase() : "FILE";
}

function getLinkHost(url: string): string {
  try {
    const parsed = new URL(url);
    return parsed.hostname.replace(/^www\./, "") || "链接";
  } catch {
    return "链接";
  }
}

const resizeHandleClasses: Record<CanvasResizeHandle, string> = {
  nw: "left-0 top-0 -translate-x-1/2 -translate-y-1/2 cursor-nwse-resize",
  n: "left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 cursor-ns-resize",
  ne: "right-0 top-0 -translate-y-1/2 translate-x-1/2 cursor-nesw-resize",
  e: "right-0 top-1/2 -translate-y-1/2 translate-x-1/2 cursor-ew-resize",
  se: "bottom-0 right-0 translate-x-1/2 translate-y-1/2 cursor-nwse-resize",
  s: "bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2 cursor-ns-resize",
  sw: "bottom-0 left-0 -translate-x-1/2 translate-y-1/2 cursor-nesw-resize",
  w: "left-0 top-1/2 -translate-x-1/2 -translate-y-1/2 cursor-ew-resize",
};

const connectionHandleClasses: Record<CanvasNodeSide, string> = {
  top: "left-1/2 top-0 -translate-x-1/2 -translate-y-[calc(50%+8px)]",
  right: "right-0 top-1/2 -translate-y-1/2 translate-x-[calc(50%+8px)]",
  bottom: "bottom-0 left-1/2 -translate-x-1/2 translate-y-[calc(50%+8px)]",
  left: "left-0 top-1/2 -translate-x-[calc(50%+8px)] -translate-y-1/2",
};

const MarkdownRenderer = React.lazy(() =>
  import("@/components/chat/MarkdownRenderer").then((module) => ({
    default: module.MarkdownRenderer,
  })),
);

const MathMarkdownRenderer = React.lazy(() =>
  import("@/components/chat/MathMarkdownRenderer").then((module) => ({
    default: module.MathMarkdownRenderer,
  })),
);

function stopWheelWhenScrollable(event: React.WheelEvent<HTMLElement>) {
  const element = event.currentTarget;
  if (
    element.scrollHeight > element.clientHeight ||
    element.scrollWidth > element.clientWidth
  ) {
    event.stopPropagation();
  }
}

function containsMathSyntax(content: string): boolean {
  return (
    content.includes("$$") ||
    content.includes("\\(") ||
    content.includes("\\[") ||
    content.includes("\\begin{") ||
    /(^|[^\\])\$(?!\s)([\s\S]*?)(?<!\s)\$/.test(content)
  );
}

export const CanvasNodeComponent: React.FC<CanvasNodeProps> = React.memo(
  ({
    node,
    isEditing,
    isSelected,
    isConnectionTarget,
    isSpacePanning,
    showConnectionHandles,
    editValue,
    getFileUrl,
    onEditValueChange,
    onPointerDown,
    onConnectionHandlePointerDown,
    onResizeHandlePointerDown,
    onContextMenu,
    onDoubleClick,
    onOpenLink,
    onOpenFile,
    onEditCommit,
    onEditCancel,
  }) => {
    const Icon = getNodeIcon(node);
    const displayText = getNodeDisplayText(node);
    const isGroup = node.type === "group";
    const isImageNode = node.type === "file" && Boolean(node.file) && isImageFile(node.file || "");
    const imageUrl = isImageNode && node.file ? getFileUrl?.(node.file) : "";
    const fillColor = getCanvasFillColor(node.color);
    const colorClass =
      nodeColorClasses[String(node.color || "")] || "border-slate-200 text-slate-950";
    const showHeader = node.type === "file" || node.type === "link";
    const handleOpenMarkdownPath = useCallback(
      (
        path: string,
        scope: WorkspaceMarkdownLinkScope,
        suffix?: string,
      ) => {
        onOpenFile(path, { scope, suffix });
      },
      [onOpenFile],
    );
    const markdownComponents = useMemo(
      () =>
        createWorkspaceMarkdownComponents({
          onOpenWorkspacePath: handleOpenMarkdownPath,
          baseComponents: {
            img: ({ src, alt }) => {
              const label = alt || src || "图片";
              return (
                <span className="rounded bg-slate-900/5 px-1.5 py-0.5 text-[11px] font-medium text-slate-500">
                  图片：{label}
                </span>
              );
            },
          },
          linkClassName: "text-blue-700 hover:text-blue-800",
        }),
      [handleOpenMarkdownPath],
    );
    const MarkdownContent = containsMathSyntax(displayText)
      ? MathMarkdownRenderer
      : MarkdownRenderer;

    return (
      <div
        data-canvas-node-id={node.id}
        className={cn(
          "group absolute select-none rounded-[8px] border shadow-sm transition-[box-shadow,border-color,background-color]",
          isGroup
            ? "border-dashed border-slate-300 dark:border-slate-600 text-slate-700 dark:text-slate-300 shadow-none"
            : colorClass,
          !fillColor && !isGroup && "bg-white dark:bg-gray-900",
          !fillColor && isGroup && "bg-slate-50/70 dark:bg-gray-900/70",
          isSelected && "border-blue-500 shadow-md ring-2 ring-blue-500/20",
          isConnectionTarget && "border-blue-600 ring-4 ring-blue-500/20",
          !isEditing && (isSpacePanning ? "cursor-grab" : "cursor-move"),
        )}
        style={{
          left: node.x,
          top: node.y,
          width: node.width,
          height: node.height,
          backgroundColor: fillColor || undefined,
        }}
        onPointerDown={(event) => onPointerDown(event, node.id)}
        onContextMenu={(event) => onContextMenu(event, node.id)}
        onDoubleClick={(event) => {
          event.stopPropagation();
          onDoubleClick(node.id);
        }}
      >
        {isSelected && !isEditing ? (
          <div className="pointer-events-none absolute inset-0 z-20">
            {(Object.keys(resizeHandleClasses) as CanvasResizeHandle[]).map(
              (handle) => (
                <button
                  key={handle}
                  type="button"
                  aria-label="调整节点大小"
                  title="拖拽调整节点大小"
                  className={cn(
                    "pointer-events-auto absolute h-3 w-3 rounded-[3px] border border-blue-600 bg-white shadow-sm transition-transform hover:scale-125",
                    resizeHandleClasses[handle],
                  )}
                  onPointerDown={(event) =>
                    onResizeHandlePointerDown(event, node.id, handle)
                  }
                />
              ),
            )}
          </div>
        ) : null}
        {showConnectionHandles && !isEditing ? (
          <div className="pointer-events-none absolute inset-0 z-10 opacity-0 transition-opacity group-hover:opacity-100 data-[selected=true]:opacity-100" data-selected={isSelected || isConnectionTarget}>
            {(["top", "right", "bottom", "left"] as const).map((side) => {
              return (
                <button
                  key={side}
                  type="button"
                  aria-label="连接节点"
                  title="拖到另一个节点上建立连线"
                  className={cn(
                    "pointer-events-auto absolute h-4 w-4 rounded-full border-2 border-white bg-blue-600 shadow-sm transition-transform hover:scale-125",
                    connectionHandleClasses[side],
                  )}
                  onPointerDown={(event) =>
                    onConnectionHandlePointerDown(event, node.id, side)
                  }
                />
              );
            })}
          </div>
        ) : null}
        <div className="flex h-full flex-col overflow-hidden p-3">
          {showHeader ? (
            <div className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500 dark:text-slate-400">
              {Icon ? <Icon className="h-3.5 w-3.5" /> : null}
              <span>{getNodeTypeLabel(node)}</span>
            </div>
          ) : null}

          {isEditing ? (
            <textarea
              value={editValue}
              autoFocus
              className="scrollbar-thin min-h-0 flex-1 resize-none overflow-y-auto overscroll-contain rounded-md border border-blue-200 dark:border-blue-800 bg-white/90 dark:bg-gray-900/90 px-2 py-1.5 text-sm leading-5 text-slate-950 dark:text-gray-100 outline-none ring-2 ring-blue-500/10"
              onChange={(event) => onEditValueChange(event.target.value)}
              onBlur={onEditCommit}
              onPointerDown={(event) => event.stopPropagation()}
              onDoubleClick={(event) => event.stopPropagation()}
              onWheel={stopWheelWhenScrollable}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  onEditCommit();
                }
                if (event.key === "Escape") {
                  event.preventDefault();
                  onEditCancel();
                }
              }}
            />
          ) : isImageNode && imageUrl ? (
            <div className="relative min-h-0 flex-1 overflow-hidden rounded-md border border-black/5 bg-white/55">
              <img
                src={imageUrl}
                alt={node.file}
                className="h-full w-full object-cover"
                draggable={false}
              />
              <button
                type="button"
                className="pointer-events-auto absolute right-2 top-2 inline-flex h-7 w-7 items-center justify-center rounded-md bg-white/85 text-slate-600 shadow-sm backdrop-blur transition-colors hover:bg-blue-50 hover:text-blue-700"
                title="打开文件"
                aria-label="打开文件"
                onPointerDown={(event) => event.stopPropagation()}
                onDoubleClick={(event) => event.stopPropagation()}
                onClick={(event) => {
                  event.stopPropagation();
                  if (node.file) {
                    onOpenFile(node.file, { suffix: node.subpath });
                  }
                }}
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </button>
              <div className="pointer-events-none absolute inset-x-3 bottom-3 rounded-b-md bg-slate-950/65 px-2 py-1 text-[11px] font-medium text-white">
                <span className="line-clamp-1">
                  {getWorkspaceFileLabel(node.file || "")}
                </span>
              </div>
            </div>
          ) : node.type === "file" ? (
            <div className="min-h-0 flex-1 rounded-md border border-black/5 dark:border-white/10 bg-white/60 dark:bg-gray-900/60 px-3 py-2">
              <div className="flex items-start gap-2">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-slate-500 dark:text-slate-400" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-slate-900 dark:text-gray-100">
                    {getWorkspaceFileLabel(displayText)}
                  </div>
                  <div className="mt-1 line-clamp-3 break-all text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                    {displayText}
                  </div>
                  {node.subpath ? (
                    <div className="mt-1 truncate rounded bg-slate-900/5 dark:bg-white/10 px-1.5 py-0.5 text-[10px] font-medium text-slate-500 dark:text-slate-400">
                      {node.subpath}
                    </div>
                  ) : null}
                </div>
                <span className="shrink-0 rounded bg-slate-900/5 dark:bg-white/10 px-1.5 py-0.5 text-[10px] font-bold leading-4 text-slate-500 dark:text-slate-400">
                  {getFileExtensionLabel(displayText)}
                </span>
                <button
                  type="button"
                  className="pointer-events-auto -mr-1 -mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 dark:text-slate-400 transition-colors hover:bg-blue-50 dark:hover:bg-blue-900/30 hover:text-blue-700 dark:hover:text-blue-400"
                  title="打开文件"
                  aria-label="打开文件"
                  onPointerDown={(event) => event.stopPropagation()}
                  onDoubleClick={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenFile(displayText, { suffix: node.subpath });
                  }}
                >
                  <Maximize2 className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ) : node.type === "link" ? (
            <div className="min-h-0 flex-1 rounded-md border border-black/5 dark:border-white/10 bg-white/60 dark:bg-gray-900/60 px-3 py-2">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold text-slate-900 dark:text-gray-100">
                    {getLinkHost(displayText)}
                  </div>
                  <div className="mt-1 line-clamp-3 break-all text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                    {displayText}
                  </div>
                </div>
                <button
                  type="button"
                  className="pointer-events-auto -mr-1 -mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-500 dark:text-slate-400 transition-colors hover:bg-blue-50 dark:hover:bg-blue-900/30 hover:text-blue-700 dark:hover:text-blue-400"
                  title="打开链接"
                  aria-label="打开链接"
                  onPointerDown={(event) => event.stopPropagation()}
                  onDoubleClick={(event) => event.stopPropagation()}
                  onClick={(event) => {
                    event.stopPropagation();
                    onOpenLink(displayText);
                  }}
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>
          ) : isGroup ? (
            <div
              className="scrollbar-thin min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1 text-sm font-semibold leading-5 text-slate-600 dark:text-slate-400"
              onWheel={stopWheelWhenScrollable}
            >
              {displayText || "分组"}
            </div>
          ) : (
            <div
              className={cn(
                "scrollbar-thin min-h-0 flex-1 overflow-y-auto overscroll-contain break-words pr-1 text-sm leading-5",
                isGroup ? "text-slate-600" : "text-current",
              )}
              onWheel={stopWheelWhenScrollable}
            >
              {displayText ? (
                <Suspense
                  fallback={
                    <div className="whitespace-pre-wrap break-words">
                      {displayText}
                    </div>
                  }
                >
                  <div className="prose prose-sm max-w-none break-words text-current [overflow-wrap:anywhere] [&_*:first-child]:mt-0 [&_*:last-child]:mb-0 [&_pre]:max-w-full [&_pre]:rounded-md [&_pre]:px-2 [&_pre]:py-1.5 [&_pre]:text-[11px] [&_table]:text-[11px]">
                    <MarkdownContent
                      content={displayText}
                      components={markdownComponents}
                    />
                  </div>
                </Suspense>
              ) : (
                <span className="text-slate-400 dark:text-slate-500">双击编辑内容</span>
              )}
            </div>
          )}
        </div>
      </div>
    );
  },
);
