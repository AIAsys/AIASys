import { Suspense, lazy } from "react";
import {
  ChevronDown,
  ChevronUp,
  Eye,
  Loader2,
  Play,
  Plus,
  SquarePen,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import type { NotebookCell, NotebookCellType } from "@/types/notebook";

import { NotebookOutputBlock } from "./renderers";

const LazyMarkdownRenderer = lazy(() =>
  import("@/components/chat/MarkdownRenderer").then((module) => ({
    default: module.MarkdownRenderer,
  })),
);

const LazyMathMarkdownRenderer = lazy(() =>
  import("@/components/chat/MathMarkdownRenderer").then((module) => ({
    default: module.MathMarkdownRenderer,
  })),
);

function containsMathSyntax(content: string): boolean {
  return (
    content.includes("$$") ||
    content.includes("\\(") ||
    content.includes("\\[") ||
    content.includes("\\begin{") ||
    /(^|[^\\])\$(?!\s)([\s\S]*?)(?<!\s)\$/.test(content)
  );
}

function MarkdownPreview({ content }: { content: string }) {
  if (containsMathSyntax(content)) {
    return (
      <Suspense
        fallback={<div className="whitespace-pre-wrap text-sm">{content}</div>}
      >
        <LazyMathMarkdownRenderer content={content} />
      </Suspense>
    );
  }

  return (
    <Suspense
      fallback={<div className="whitespace-pre-wrap text-sm">{content}</div>}
    >
      <LazyMarkdownRenderer content={content} />
    </Suspense>
  );
}

export interface NotebookCellCardProps {
  cell: NotebookCell;
  cellIndex: number;
  isFocused: boolean;
  isMarkdownPreview: boolean;
  isRunning: boolean;
  disableRunCell?: boolean;
  disableInsertCell?: boolean;
  disableMoveCell?: boolean;
  disableClearOutputs?: boolean;
  disableDeleteCell?: boolean;
  containerRef?: (node: HTMLDivElement | null) => void;
  onChangeCellType: (cellId: string, nextType: NotebookCellType) => void;
  onChangeSource: (cellId: string, source: string) => void;
  onToggleMarkdownPreview: (cellId: string) => void;
  onRunCell: (cellId: string) => void;
  onInsertCell: (
    referenceIndex: number,
    position: "before" | "after",
    type: NotebookCellType,
  ) => void;
  onMoveCell: (index: number, direction: "up" | "down") => void;
  onClearOutputs: (cellId: string) => void;
  onDeleteCell: (cellId: string) => void;
}

export function NotebookCellCard({
  cell,
  cellIndex,
  isFocused,
  isMarkdownPreview,
  isRunning,
  disableRunCell = false,
  disableInsertCell = false,
  disableMoveCell = false,
  disableClearOutputs = false,
  disableDeleteCell = false,
  containerRef,
  onChangeCellType,
  onChangeSource,
  onToggleMarkdownPreview,
  onRunCell,
  onInsertCell,
  onMoveCell,
  onClearOutputs,
  onDeleteCell,
}: NotebookCellCardProps) {
  return (
    <div
      ref={containerRef}
      className={cn(
        "rounded-2xl border bg-card shadow-sm transition-all",
        isFocused
          ? "border-primary ring-2 ring-primary/20"
          : "border-border/80",
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/60 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary">[{cell.execution_count ?? " "}]</Badge>
          <select
            className="h-8 rounded-md border border-input bg-background px-2 text-xs"
            value={cell.cell_type}
            onChange={(event) =>
              onChangeCellType(
                cell.cell_id,
                event.target.value as NotebookCellType,
              )
            }
          >
            <option value="code">Code</option>
            <option value="markdown">Markdown</option>
            <option value="raw">Raw</option>
          </select>
          <span className="text-xs text-muted-foreground">
            Cell {cellIndex + 1}
          </span>
          {cell.cell_type === "markdown" ? (
            <Button
              type="button"
              variant={isMarkdownPreview ? "default" : "outline"}
              size="sm"
              className="ml-1"
              onClick={() => onToggleMarkdownPreview(cell.cell_id)}
            >
              {isMarkdownPreview ? (
                <>
                  <SquarePen className="mr-1.5 h-3.5 w-3.5" />
                  编辑
                </>
              ) : (
                <>
                  <Eye className="mr-1.5 h-3.5 w-3.5" />
                  预览
                </>
              )}
            </Button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {cell.cell_type === "code" ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onRunCell(cell.cell_id)}
              disabled={disableRunCell}
            >
              {isRunning ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="mr-1.5 h-3.5 w-3.5" />
              )}
              运行 Cell
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onInsertCell(cellIndex, "before", cell.cell_type)}
            disabled={disableInsertCell}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            上方插入
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() => onInsertCell(cellIndex, "after", cell.cell_type)}
            disabled={disableInsertCell}
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            下方插入
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onMoveCell(cellIndex, "up")}
            disabled={disableMoveCell}
          >
            <ChevronUp className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onMoveCell(cellIndex, "down")}
            disabled={disableMoveCell}
          >
            <ChevronDown className="h-4 w-4" />
          </Button>
          {cell.cell_type === "code" ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onClearOutputs(cell.cell_id)}
              disabled={disableClearOutputs}
            >
              清空输出
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onDeleteCell(cell.cell_id)}
            disabled={disableDeleteCell}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <div className="space-y-3 px-4 py-4">
        {cell.cell_type === "markdown" && isMarkdownPreview ? (
          <div className="prose max-w-none px-2 py-2">
            <MarkdownPreview content={cell.source} />
          </div>
        ) : (
          <Textarea
            value={cell.source}
            onChange={(event) => onChangeSource(cell.cell_id, event.target.value)}
            className={
              cell.cell_type === "code"
                ? "min-h-[180px] resize-y font-mono text-[13px]"
                : "min-h-[140px] resize-y text-sm"
            }
          />
        )}

        {cell.outputs.length > 0 ? (
          <div className="space-y-3 rounded-2xl border border-border bg-muted/20 px-4 py-4">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
              Outputs
            </div>
            {cell.outputs.map((output, outputIndex) => (
              <NotebookOutputBlock
                key={`${cell.cell_id}-${outputIndex}`}
                output={output}
              />
            ))}
          </div>
        ) : cell.cell_type === "code" ? (
          <div className="rounded-2xl border border-dashed border-border/60 px-4 py-3 text-xs text-muted-foreground">
            当前 cell 还没有输出。
          </div>
        ) : null}
      </div>
    </div>
  );
}
