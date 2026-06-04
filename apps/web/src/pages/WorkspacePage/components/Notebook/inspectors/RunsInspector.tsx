import { Badge } from "@/components/ui/badge";
import type { NotebookExecutionRecord } from "@/types/notebook";

interface RunsInspectorProps {
  executionRecords: NotebookExecutionRecord[];
}

export function RunsInspector({ executionRecords }: RunsInspectorProps) {
  if (executionRecords.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 px-3 py-4 text-xs text-muted-foreground">
        当前 notebook 还没有执行记录。
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {executionRecords.map((record) => {
        const isCompleted = record.status === "completed";
        return (
          <div key={record.record_id} className="rounded-xl border border-border px-3 py-3">
            <div className="flex items-center justify-between gap-3">
              <div className="text-sm font-medium text-foreground">{record.record_id}</div>
              <Badge
                variant={isCompleted ? "secondary" : "outline"}
                className={isCompleted ? undefined : "border-error/20 text-error"}
              >
                {record.status}
              </Badge>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              Cell {record.cell_index != null ? record.cell_index + 1 : "?"}
              {record.execution_count != null ? ` · 执行序号 ${record.execution_count}` : ""}
            </div>
            {record.result_preview_text ? (
              <pre className="mt-2 overflow-x-auto rounded-lg bg-muted px-3 py-2 text-xs text-foreground">
                {record.result_preview_text}
              </pre>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}
