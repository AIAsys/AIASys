import React, { useRef, useEffect } from "react";
import {
  BringToFront,
  Copy,
  Link2,
  Palette,
  SendToBack,
  Trash2,
  Type,
} from "lucide-react";
import { CANVAS_COLOR_OPTIONS } from "./canvasUtils";
import type { CanvasContextMenu } from "./useCanvasHandlers";

interface ContextMenuProps {
  contextMenu: CanvasContextMenu;
  contextMenuTitle: string;
  selectedNodeCount: number;
  canEditNode: boolean;
  contextEdgeArrowShown: boolean;
  onEditNode: (nodeId: string) => void;
  onDuplicateNodes: () => void;
  onReorderNodes: (direction: "front" | "back") => void;
  onApplyColor: (color: string) => void;
  onEditEdgeLabel: (edgeId: string) => void;
  onToggleEdgeArrow: (edgeId: string) => void;
  onDelete: () => void;
  onClose: () => void;
}

export const CanvasContextMenuComponent: React.FC<ContextMenuProps> = ({
  contextMenu,
  contextMenuTitle,
  canEditNode,
  contextEdgeArrowShown,
  onEditNode,
  onDuplicateNodes,
  onReorderNodes,
  onApplyColor,
  onEditEdgeLabel,
  onToggleEdgeArrow,
  onDelete,
  onClose,
}) => {
  const contextMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const handlePointerDown = (event: PointerEvent) => {
      if (
        contextMenuRef.current?.contains(event.target as Node)
      ) {
        return;
      }
      onClose();
    };
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [onClose]);

  return (
    <div
      ref={contextMenuRef}
      role="menu"
      className="fixed z-[70] w-64 overflow-hidden rounded-xl border border-slate-200 bg-white p-1 text-sm text-slate-700 shadow-xl"
      style={{ left: contextMenu.x, top: contextMenu.y }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      <div className="border-b border-slate-100 px-2 py-2">
        <div className="truncate text-xs font-semibold text-slate-950">
          {contextMenuTitle}
        </div>
        <div className="mt-0.5 text-[11px] text-slate-500">
          {contextMenu.kind === "node" ? "节点操作" : "连线操作"}
        </div>
      </div>

      {contextMenu.kind === "node" && canEditNode ? (
        <>
          <button
            type="button"
            role="menuitem"
            className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-100"
            onClick={() => {
              onEditNode(contextMenu.nodeId);
              onClose();
            }}
          >
            <Type className="h-3.5 w-3.5 text-slate-500" />
            编辑内容
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-100"
            onClick={onDuplicateNodes}
          >
            <Copy className="h-3.5 w-3.5 text-slate-500" />
            复制节点
          </button>
          <div className="mt-1 border-t border-slate-100 pt-1">
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-100"
              onClick={() => onReorderNodes("front")}
            >
              <BringToFront className="h-3.5 w-3.5 text-slate-500" />
              置于顶层
            </button>
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-100"
              onClick={() => onReorderNodes("back")}
            >
              <SendToBack className="h-3.5 w-3.5 text-slate-500" />
              置于底层
            </button>
          </div>
          <div className="mt-1 border-t border-slate-100 px-2 py-2">
            <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold text-slate-500">
              <Palette className="h-3.5 w-3.5" />
              颜色
            </div>
            <div className="flex flex-wrap gap-1">
              {CANVAS_COLOR_OPTIONS.map((option) => (
                <button
                  key={option.value || "default-menu"}
                  type="button"
                  title={option.value ? option.label : "清除颜色"}
                  className="h-5 w-5 rounded-full border border-slate-300 transition-transform hover:scale-110"
                  style={{ backgroundColor: option.hex }}
                  onClick={() => {
                    onApplyColor(option.value);
                    onClose();
                  }}
                />
              ))}
            </div>
          </div>
          <div className="mt-1 border-t border-slate-100 pt-1">
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-red-700 transition-colors hover:bg-red-50"
              onClick={() => {
                onClose();
                onDelete();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除选中节点
            </button>
          </div>
        </>
      ) : null}

      {contextMenu.kind === "edge" ? (
        <>
          <button
            type="button"
            role="menuitem"
            className="mt-1 flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-100"
            onClick={() => onEditEdgeLabel(contextMenu.edgeId)}
          >
            <Link2 className="h-3.5 w-3.5 text-slate-500" />
            编辑标签
          </button>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition-colors hover:bg-slate-100"
            onClick={() => onToggleEdgeArrow(contextMenu.edgeId)}
          >
            <Link2 className="h-3.5 w-3.5 text-slate-500" />
            {contextEdgeArrowShown ? "隐藏箭头" : "显示箭头"}
          </button>
          <div className="mt-1 border-t border-slate-100 px-2 py-2">
            <div className="mb-1 flex items-center gap-1 text-[11px] font-semibold text-slate-500">
              <Palette className="h-3.5 w-3.5" />
              颜色
            </div>
            <div className="flex flex-wrap gap-1">
              {CANVAS_COLOR_OPTIONS.map((option) => (
                <button
                  key={option.value || "default-edge-menu"}
                  type="button"
                  title={option.value ? option.label : "清除颜色"}
                  className="h-5 w-5 rounded-full border border-slate-300 transition-transform hover:scale-110"
                  style={{ backgroundColor: option.hex }}
                  onClick={() => {
                    onApplyColor(option.value);
                    onClose();
                  }}
                />
              ))}
            </div>
          </div>
          <div className="mt-1 border-t border-slate-100 pt-1">
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs text-red-700 transition-colors hover:bg-red-50"
              onClick={() => {
                onClose();
                onDelete();
              }}
            >
              <Trash2 className="h-3.5 w-3.5" />
              删除连线
            </button>
          </div>
        </>
      ) : null}
    </div>
  );
};
