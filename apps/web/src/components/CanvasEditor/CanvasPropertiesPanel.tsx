import React, { useRef } from "react";
import { PanelRight, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { CANVAS_COLOR_OPTIONS, getWorkspaceFileLabel } from "./canvasUtils";
import type { CanvasEdge, CanvasNode } from "./types";

interface CanvasPropertiesPanelProps {
  selectedNode: CanvasNode | null;
  selectedEdge: CanvasEdge | null;
  selectedNodeCount: number;
  onBeginNodeChange: (nodeId: string) => void;
  onBeginEdgeChange: (edgeId: string) => void;
  onUpdateNode: (
    nodeId: string,
    patch: Partial<CanvasNode>,
    options?: { recordHistory?: boolean },
  ) => void;
  onUpdateEdge: (
    edgeId: string,
    patch: Partial<CanvasEdge>,
    options?: { recordHistory?: boolean },
  ) => void;
  onClose: () => void;
}

function getNodePrimaryValue(node: CanvasNode): string {
  if (node.type === "file") {
    return node.file || "";
  }
  if (node.type === "link") {
    return node.url || "";
  }
  if (node.type === "group") {
    return node.label || "";
  }
  return node.text || "";
}

function getNodePrimaryLabel(node: CanvasNode): string {
  if (node.type === "file") {
    return "文件路径";
  }
  if (node.type === "link") {
    return "链接";
  }
  if (node.type === "group") {
    return "分组标题";
  }
  return "文本";
}

function getNodePrimaryPatch(
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

export const CanvasPropertiesPanel: React.FC<CanvasPropertiesPanelProps> = ({
  selectedNode,
  selectedEdge,
  selectedNodeCount,
  onBeginNodeChange,
  onBeginEdgeChange,
  onUpdateNode,
  onUpdateEdge,
  onClose,
}) => {
  const activeEditKeyRef = useRef<string | null>(null);

  if (!selectedNode && !selectedEdge) {
    return null;
  }

  const selectedColor = String(selectedNode?.color ?? selectedEdge?.color ?? "");
  const beginTrackedEdit = (key: string, begin: () => void) => {
    if (activeEditKeyRef.current === key) {
      return;
    }
    activeEditKeyRef.current = key;
    begin();
  };
  const endTrackedEdit = (key: string) => {
    if (activeEditKeyRef.current === key) {
      activeEditKeyRef.current = null;
    }
  };

  return (
    <aside
      className="absolute right-14 top-3 z-40 flex max-h-[calc(100%-1.5rem)] w-[320px] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white/95 text-slate-900 shadow-xl backdrop-blur"
      data-testid="canvas-properties-panel"
      onPointerDown={(event) => event.stopPropagation()}
      onDoubleClick={(event) => event.stopPropagation()}
    >
      <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2.5">
        <div className="flex min-w-0 items-center gap-2">
          <PanelRight className="h-4 w-4 shrink-0 text-slate-500" />
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold">
              {selectedNode
                ? selectedNodeCount > 1
                  ? `${selectedNodeCount} 个节点`
                  : getWorkspaceFileLabel(getNodePrimaryValue(selectedNode)) ||
                    "节点"
                : selectedEdge?.label || "连线"}
            </div>
            <div className="mt-0.5 text-[11px] text-slate-500">
              {selectedNode ? "节点属性" : "连线属性"}
            </div>
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          aria-label="关闭属性面板"
          onClick={onClose}
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
        {selectedNode ? (
          <>
            <section className="space-y-2">
              <Label htmlFor="canvas-node-primary">
                {getNodePrimaryLabel(selectedNode)}
              </Label>
              {selectedNode.type === "text" ? (
                <Textarea
                  id="canvas-node-primary"
                  value={getNodePrimaryValue(selectedNode)}
                  className="min-h-[132px] resize-none text-sm"
                  onFocus={() =>
                    beginTrackedEdit(`node:${selectedNode.id}:primary`, () =>
                      onBeginNodeChange(selectedNode.id),
                    )
                  }
                  onBlur={() => endTrackedEdit(`node:${selectedNode.id}:primary`)}
                  onChange={(event) =>
                    onUpdateNode(
                      selectedNode.id,
                      getNodePrimaryPatch(selectedNode, event.target.value),
                      { recordHistory: false },
                    )
                  }
                />
              ) : (
                <Input
                  id="canvas-node-primary"
                  value={getNodePrimaryValue(selectedNode)}
                  onFocus={() =>
                    beginTrackedEdit(`node:${selectedNode.id}:primary`, () =>
                      onBeginNodeChange(selectedNode.id),
                    )
                  }
                  onBlur={() => endTrackedEdit(`node:${selectedNode.id}:primary`)}
                  onChange={(event) =>
                    onUpdateNode(
                      selectedNode.id,
                      getNodePrimaryPatch(selectedNode, event.target.value),
                      { recordHistory: false },
                    )
                  }
                />
              )}
            </section>

            {selectedNode.type === "file" ? (
              <section className="space-y-2">
                <Label htmlFor="canvas-node-subpath">内部位置</Label>
                <Input
                  id="canvas-node-subpath"
                  value={selectedNode.subpath || ""}
                  placeholder="#标题、?page=2 或其它片段"
                  onFocus={() =>
                    beginTrackedEdit(`node:${selectedNode.id}:subpath`, () =>
                      onBeginNodeChange(selectedNode.id),
                    )
                  }
                  onBlur={() => endTrackedEdit(`node:${selectedNode.id}:subpath`)}
                  onChange={(event) =>
                    onUpdateNode(
                      selectedNode.id,
                      {
                        subpath: event.target.value || undefined,
                      },
                      { recordHistory: false },
                    )
                  }
                />
              </section>
            ) : null}

          </>
        ) : null}

        {selectedEdge ? (
          <>
            <section className="space-y-2">
              <Label htmlFor="canvas-edge-label">标签</Label>
              <Input
                id="canvas-edge-label"
                value={selectedEdge.label || ""}
                placeholder="连线说明"
                onFocus={() =>
                  beginTrackedEdit(`edge:${selectedEdge.id}:label`, () =>
                    onBeginEdgeChange(selectedEdge.id),
                  )
                }
                onBlur={() => endTrackedEdit(`edge:${selectedEdge.id}:label`)}
                onChange={(event) =>
                  onUpdateEdge(
                    selectedEdge.id,
                    {
                      label: event.target.value || undefined,
                    },
                    { recordHistory: false },
                  )
                }
              />
            </section>
            <section className="space-y-2">
              <Label>箭头</Label>
              <Select
                value={selectedEdge.toEnd === "none" ? "none" : "arrow"}
                onValueChange={(value) =>
                  onUpdateEdge(selectedEdge.id, {
                    toEnd: value === "none" ? "none" : "arrow",
                  })
                }
              >
                <SelectTrigger className="h-9" aria-label="连线箭头">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="arrow">显示</SelectItem>
                  <SelectItem value="none">隐藏</SelectItem>
                </SelectContent>
              </Select>
            </section>
          </>
        ) : null}

        <section className="space-y-2">
          <Label>颜色</Label>
          <div className="flex flex-wrap gap-1.5">
            {CANVAS_COLOR_OPTIONS.map((option) => (
              <button
                key={option.value || "default-panel"}
                type="button"
                title={option.value ? option.label : "默认"}
                aria-label={option.value ? `设置为${option.label}色` : "清除颜色"}
                className={`h-6 w-6 rounded-full border border-slate-300 transition-transform hover:scale-110 ${
                  selectedColor === option.value
                    ? "ring-2 ring-blue-500 ring-offset-1"
                    : ""
                }`}
                style={{ backgroundColor: option.hex }}
                onClick={() => {
                  if (selectedNode) {
                    onUpdateNode(selectedNode.id, {
                      color: option.value || undefined,
                    });
                  } else if (selectedEdge) {
                    onUpdateEdge(selectedEdge.id, {
                      color: option.value || undefined,
                    });
                  }
                }}
              />
            ))}
          </div>
        </section>
      </div>
    </aside>
  );
};
