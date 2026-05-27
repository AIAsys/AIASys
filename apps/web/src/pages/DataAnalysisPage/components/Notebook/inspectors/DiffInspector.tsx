import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { DiffViewer } from "@/components/diff/DiffViewer";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { NotebookDiffCellChange } from "@/types/notebook";

interface DiffInspectorProps {
  changes: NotebookDiffCellChange[];
  metadataChanged: boolean;
  onSelectCell: (cellId: string) => void;
}

export function DiffInspector({
  changes,
  metadataChanged,
  onSelectCell,
}: DiffInspectorProps) {
  const [expandedCellId, setExpandedCellId] = useState<string | null>(null);

  return (
    <div className="space-y-2">
      <div className="rounded-xl border border-border px-3 py-3 text-xs text-muted-foreground">
        Metadata 变化：{metadataChanged ? "已变化" : "无变化"}
      </div>
      {changes.length > 0 ? (
        changes.map((change) => {
          const isExpanded = expandedCellId === change.cell_id;
          const hasDiff =
            change.status === "changed" &&
            change.unified_diff &&
            change.unified_diff.length > 0;

          return (
            <div
              key={`${change.cell_id}-${change.status}`}
              className="rounded-xl border border-border transition-colors hover:border-primary/40 hover:bg-muted/30"
            >
              <div
                className="flex cursor-pointer items-center justify-between gap-3 px-3 py-3"
                onClick={() => onSelectCell(change.cell_id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    onSelectCell(change.cell_id);
                  }
                }}
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-foreground">
                    {change.source_preview || change.cell_id}
                  </div>
                  <div className="mt-1 text-xs text-muted-foreground">
                    {change.changed_fields.length > 0
                      ? `变更字段：${change.changed_fields.join(", ")}`
                      : "结构变化"}
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {hasDiff && (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-[11px] font-medium text-primary hover:bg-primary/10"
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedCellId(
                          isExpanded ? null : change.cell_id
                        );
                      }}
                    >
                      {isExpanded ? (
                        <ChevronUp className="h-3 w-3" />
                      ) : (
                        <ChevronDown className="h-3 w-3" />
                      )}
                      差异
                    </button>
                  )}
                  <Badge variant="outline">{change.status}</Badge>
                </div>
              </div>

              {isExpanded && hasDiff && (
                <div className="border-t border-border px-3 pb-3 pt-2">
                  <DiffViewer
                    unifiedDiff={change.unified_diff}
                    leftLabel="session"
                    rightLabel="workspace"
                    status="modified"
                    className="max-h-[360px]"
                  />
                </div>
              )}
            </div>
          );
        })
      ) : (
        <div className="rounded-xl border border-dashed border-border/60 px-3 py-4 text-xs text-muted-foreground">
          当前会话副本与工作区共享基线没有差异。
        </div>
      )}
    </div>
  );
}
