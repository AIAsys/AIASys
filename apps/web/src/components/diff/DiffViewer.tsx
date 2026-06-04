import { useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Eye, EyeOff } from "lucide-react";

export type DiffStatus = "added" | "deleted" | "modified" | "unchanged" | "skipped";

interface DiffViewerProps {
  unifiedDiff?: string | null;
  leftLabel?: string | null;
  rightLabel?: string | null;
  status?: DiffStatus;
  canShowContent?: boolean;
  skipReason?: string | null;
  currentExists?: boolean;
  emptyMessage?: string;
  className?: string;
}

type DiffRowType = "file" | "hunk" | "added" | "deleted" | "context" | "meta";

interface DiffRow {
  key: string;
  type: DiffRowType;
  oldLine: number | null;
  newLine: number | null;
  content: string;
}

const HUNK_RE = /^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/;

function parseUnifiedDiff(diff: string): DiffRow[] {
  const normalized = diff.endsWith("\n") ? diff.slice(0, -1) : diff;
  if (!normalized) return [];

  const rows: DiffRow[] = [];
  let oldLine: number | null = null;
  let newLine: number | null = null;

  normalized.split("\n").forEach((line, index) => {
    const hunkMatch = HUNK_RE.exec(line);
    if (hunkMatch) {
      oldLine = Number(hunkMatch[1]);
      newLine = Number(hunkMatch[2]);
      rows.push({
        key: `${index}-hunk`,
        type: "hunk",
        oldLine: null,
        newLine: null,
        content: line,
      });
      return;
    }

    if (line.startsWith("---") || line.startsWith("+++")) {
      rows.push({
        key: `${index}-file`,
        type: "file",
        oldLine: null,
        newLine: null,
        content: line,
      });
      return;
    }

    if (line.startsWith("\\ No newline")) {
      rows.push({
        key: `${index}-meta`,
        type: "meta",
        oldLine: null,
        newLine: null,
        content: line,
      });
      return;
    }

    if (line.startsWith("+")) {
      rows.push({
        key: `${index}-added`,
        type: "added",
        oldLine: null,
        newLine,
        content: line,
      });
      if (newLine !== null) newLine += 1;
      return;
    }

    if (line.startsWith("-")) {
      rows.push({
        key: `${index}-deleted`,
        type: "deleted",
        oldLine,
        newLine: null,
        content: line,
      });
      if (oldLine !== null) oldLine += 1;
      return;
    }

    rows.push({
      key: `${index}-context`,
      type: "context",
      oldLine,
      newLine,
      content: line,
    });
    if (oldLine !== null) oldLine += 1;
    if (newLine !== null) newLine += 1;
  });

  return rows;
}

function rowClassName(type: DiffRowType) {
  switch (type) {
    case "added":
      return "bg-success-container/40 text-success";
    case "deleted":
      return "bg-error-container/40 text-error";
    case "hunk":
      return "bg-tertiary-container/45 text-on-tertiary-container";
    case "file":
    case "meta":
      return "bg-muted/60 text-muted-foreground";
    default:
      return "text-foreground";
  }
}

function statusLabel(status: DiffStatus | undefined) {
  switch (status) {
    case "added":
      return "新增";
    case "deleted":
      return "删除";
    case "modified":
      return "修改";
    case "unchanged":
      return "未变化";
    case "skipped":
      return "跳过";
    default:
      return "差异";
  }
}

export function DiffViewer({
  unifiedDiff,
  leftLabel,
  rightLabel,
  status,
  canShowContent = true,
  skipReason,
  currentExists = true,
  emptyMessage = "没有内容差异",
  className,
}: DiffViewerProps) {
  const [showContext, setShowContext] = useState(true);
  const allRows = useMemo(() => parseUnifiedDiff(unifiedDiff ?? ""), [unifiedDiff]);
  const contextRowCount = useMemo(
    () => allRows.filter((r) => r.type === "context").length,
    [allRows]
  );
  const rows = useMemo(() => {
    if (showContext) return allRows;
    const withoutContext = allRows.filter((r) => r.type !== "context");
    // 过滤掉后面没有 added/deleted 的孤立 hunk 头
    return withoutContext.filter((row, index) => {
      if (row.type !== "hunk") return true;
      for (let i = index + 1; i < withoutContext.length; i++) {
        const next = withoutContext[i];
        if (next.type === "hunk") break;
        if (next.type === "added" || next.type === "deleted") return true;
      }
      return false;
    });
  }, [allRows, showContext]);
  const canRenderDiff = canShowContent && rows.length > 0;
  const hasContext = contextRowCount > 0;

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col overflow-hidden rounded-md border border-border bg-background",
        className,
      )}
      data-testid="diff-viewer"
    >
      <div className="flex min-h-11 items-center justify-between gap-3 border-b border-border bg-muted/30 px-3 py-2">
        <div className="grid min-w-0 flex-1 grid-cols-2 gap-3 text-[11px]">
          <div className="min-w-0">
            <div className="text-muted-foreground">左侧</div>
            <div className="truncate font-mono text-foreground">{leftLabel || "left"}</div>
          </div>
          <div className="min-w-0">
            <div className="text-muted-foreground">右侧</div>
            <div className="truncate font-mono text-foreground">{rightLabel || "right"}</div>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {hasContext && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="h-6 gap-1 px-1.5 text-[11px] text-muted-foreground hover:text-foreground"
              onClick={() => setShowContext((v) => !v)}
            >
              {showContext ? (
                <EyeOff className="h-3 w-3" />
              ) : (
                <Eye className="h-3 w-3" />
              )}
              {showContext ? "折叠" : "展开"}
            </Button>
          )}
          <span className="shrink-0 rounded-md bg-secondary-container px-2 py-1 text-[11px] font-medium text-on-secondary-container">
            {statusLabel(status)}
          </span>
        </div>
      </div>

      {!currentExists ? (
        <div className="border-b border-warning/30 bg-warning-container/30 px-3 py-2 text-xs text-on-warning-container">
          当前文件不存在
        </div>
      ) : null}

      {!canShowContent ? (
        <div className="px-3 py-4 text-xs text-muted-foreground">
          {skipReason || "当前文件不能展示内容差异"}
        </div>
      ) : canRenderDiff ? (
        <div className="min-h-0 flex-1 overflow-auto font-mono text-xs leading-5">
          {!showContext && hasContext && (
            <div className="border-b border-border/40 bg-muted/20 px-3 py-1.5 text-[11px] text-muted-foreground">
              已隐藏 {contextRowCount} 行未变更内容
            </div>
          )}
          {rows.map((row) => (
            <div
              key={row.key}
              className={cn(
                "grid min-w-full grid-cols-[56px_56px_minmax(0,1fr)] border-b border-border/40",
                rowClassName(row.type),
              )}
            >
              <div className="select-none border-r border-border/40 px-2 text-right text-muted-foreground">
                {row.oldLine ?? ""}
              </div>
              <div className="select-none border-r border-border/40 px-2 text-right text-muted-foreground">
                {row.newLine ?? ""}
              </div>
              <div className="min-w-0 whitespace-pre-wrap break-words px-2">
                {row.content || " "}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="px-3 py-4 text-xs text-muted-foreground">{emptyMessage}</div>
      )}
    </div>
  );
}
