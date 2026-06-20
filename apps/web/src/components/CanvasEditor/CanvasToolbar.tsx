import React from "react";
import {
  AlignHorizontalSpaceAround,
  AlignVerticalSpaceAround,
  Circle,
  FilePlus2,
  Fullscreen,
  Image as ImageIcon,
  Link2,
  Maximize2,
  Network,
  Palette,
  Redo2,
  RotateCcw,
  Save,
  SquareDashed,
  Trash2,
  Type,
  Undo2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { CANVAS_COLOR_OPTIONS } from "./canvasUtils";
import type { SaveState } from "./useCanvasHandlers";
import type { CanvasNode, CanvasEdge } from "./types";

interface CanvasToolbarProps {
  canDelete: boolean;
  saveState: SaveState;
  viewportScale: number;
  selectedNode: CanvasNode | null;
  selectedEdge: CanvasEdge | null;
  selectedColor: string;
  parseError: string | null;
  saveError: string | null;
  showConnectionPreview: boolean;
  hasSaveTarget: boolean;
  canUndo: boolean;
  canRedo: boolean;
  onAddTextNode: () => void;
  onAddFileNode: () => void;
  onAddImageNode: () => void;
  onAddLinkNode: () => void;
  onAddGroupNode: () => void;
  onDeleteSelected: () => void;
  onSave: () => void;
  onUndo: () => void;
  onRedo: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetZoom: () => void;
  onFitView: () => void;
  onAutoLayout: (mode: "horizontal" | "vertical" | "radial") => void;
  onRequestImmersivePreview?: () => void;
  onApplyColor: (color: string) => void;
}

export const CanvasToolbar: React.FC<CanvasToolbarProps> = ({
  canDelete,
  saveState,
  viewportScale,
  selectedNode,
  selectedEdge,
  selectedColor,
  parseError,
  saveError,
  showConnectionPreview,
  hasSaveTarget,
  canUndo,
  canRedo,
  onAddTextNode,
  onAddFileNode,
  onAddImageNode,
  onAddLinkNode,
  onAddGroupNode,
  onDeleteSelected,
  onSave,
  onUndo,
  onRedo,
  onZoomIn,
  onZoomOut,
  onResetZoom,
  onFitView,
  onAutoLayout,
  onRequestImmersivePreview,
  onApplyColor,
}) => {
  const saveLabel =
    saveState === "saving"
      ? "保存中"
      : saveState === "dirty"
        ? "未保存"
        : saveState === "error"
          ? "保存失败"
          : saveState === "saved"
            ? "已保存"
            : "就绪";

  return (
    <>
      {/* Left toolbar: add node buttons */}
      <div className="absolute left-3 top-3 z-30 flex flex-col items-center gap-1 rounded-lg border border-slate-200 dark:border-gray-700 bg-white/92 dark:bg-gray-900/92 p-1 shadow-sm backdrop-blur">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="添加文本节点"
          onClick={onAddTextNode}
        >
          <Type className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="添加文档节点"
          onClick={onAddFileNode}
        >
          <FilePlus2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="添加图片节点"
          onClick={onAddImageNode}
        >
          <ImageIcon className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="添加链接节点"
          onClick={onAddLinkNode}
        >
          <Link2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="添加分组"
          onClick={onAddGroupNode}
        >
          <SquareDashed className="h-3.5 w-3.5" />
        </Button>
        <div className="my-1 h-px w-5 bg-slate-200" />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="撤销"
          aria-label="撤销"
          disabled={!canUndo}
          onClick={onUndo}
        >
          <Undo2 className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="重做"
          aria-label="重做"
          disabled={!canRedo}
          onClick={onRedo}
        >
          <Redo2 className="h-3.5 w-3.5" />
        </Button>
        <div className="my-1 h-px w-5 bg-slate-200" />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="横向整理"
          aria-label="横向整理"
          onClick={() => onAutoLayout("horizontal")}
        >
          <AlignHorizontalSpaceAround className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="纵向整理"
          aria-label="纵向整理"
          onClick={() => onAutoLayout("vertical")}
        >
          <AlignVerticalSpaceAround className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="中心发散整理"
          aria-label="中心发散整理"
          onClick={() => onAutoLayout("radial")}
        >
          <Network className="h-3.5 w-3.5" />
        </Button>
        <div className="my-1 h-px w-5 bg-slate-200" />
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title="删除选中项"
          disabled={!canDelete}
          onClick={onDeleteSelected}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
        {hasSaveTarget && (
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            title="保存"
            onClick={onSave}
          >
            <Save className="h-3.5 w-3.5" />
          </Button>
        )}
        {onRequestImmersivePreview ? (
          <>
            <div className="my-1 h-px w-5 bg-slate-200" />
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              title="沉浸预览"
              aria-label="沉浸预览"
              data-testid="canvas-immersive-preview-button"
              onClick={onRequestImmersivePreview}
            >
              <Fullscreen className="h-3.5 w-3.5" />
            </Button>
          </>
        ) : null}
      </div>

      {/* Save status badge */}
      <div className="absolute right-3 top-3 z-10 flex items-center gap-2 rounded-lg border border-slate-200 dark:border-gray-700 bg-white/90 dark:bg-gray-900/90 px-2.5 py-1.5 text-[11px] font-medium text-slate-500 dark:text-slate-400 shadow-sm backdrop-blur">
        <Circle
          className={cn(
            "h-2.5 w-2.5 fill-current",
            saveState === "error"
              ? "text-red-500"
              : saveState === "dirty" || saveState === "saving"
                ? "text-amber-500"
                : "text-teal-600",
          )}
        />
        <span>{saveLabel}</span>
      </div>

      {/* Zoom controls */}
      <div className="absolute right-3 top-1/2 z-30 flex -translate-y-1/2 flex-col overflow-hidden rounded-lg border border-slate-200 dark:border-gray-700 bg-white/92 dark:bg-gray-900/92 shadow-sm backdrop-blur">
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-none border-b border-slate-100 dark:border-gray-800"
          title="放大"
          onClick={onZoomIn}
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-none border-b border-slate-100 dark:border-gray-800"
          title="重置缩放"
          onClick={onResetZoom}
        >
          <RotateCcw className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-none border-b border-slate-100 dark:border-gray-800"
          title="适配画布"
          aria-label="适配画布"
          onClick={onFitView}
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-9 w-9 rounded-none"
          title="缩小"
          onClick={onZoomOut}
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <div
          data-testid="canvas-zoom-label"
          className="border-t border-slate-100 dark:border-gray-800 px-1.5 py-1 text-center text-[10px] font-medium tabular-nums text-slate-500 dark:text-slate-400"
        >
          {Math.round(viewportScale * 100)}%
        </div>
      </div>

      {/* Color palette */}
      {selectedNode || selectedEdge ? (
        <div className="absolute right-14 top-1/2 z-30 flex -translate-y-1/2 flex-col items-center gap-1 rounded-lg border border-slate-200 dark:border-gray-700 bg-white/92 dark:bg-gray-900/92 px-1.5 py-2 shadow-sm backdrop-blur">
          <Palette className="mb-0.5 h-3.5 w-3.5 text-slate-500" />
          {CANVAS_COLOR_OPTIONS.map((option) => (
            <button
              key={option.value || "default"}
              type="button"
              title={
                option.value ? `设置为${option.label}色` : "清除颜色"
              }
              className={cn(
                "h-4 w-4 rounded-full border border-slate-300 transition-transform hover:scale-110",
                String(selectedColor || "") === option.value &&
                  "ring-2 ring-blue-500 ring-offset-1",
              )}
              style={{ backgroundColor: option.hex }}
              onClick={() => onApplyColor(option.value)}
            />
          ))}
        </div>
      ) : null}

      {/* Error banner */}
      {parseError || saveError ? (
        <div className="absolute left-16 right-28 top-3 z-20 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-800 shadow-sm">
          {saveError || parseError}
        </div>
      ) : null}

      {/* Connection preview badge */}
      {showConnectionPreview ? (
        <div className="absolute bottom-3 right-3 z-10 flex items-center gap-2 rounded-lg border border-blue-200 dark:border-blue-800 bg-white/90 dark:bg-gray-900/90 px-2.5 py-1.5 text-[11px] font-medium text-blue-700 dark:text-blue-400 shadow-sm backdrop-blur">
          <Link2 className="h-3.5 w-3.5" />
          <span>连线中</span>
        </div>
      ) : null}
    </>
  );
};
