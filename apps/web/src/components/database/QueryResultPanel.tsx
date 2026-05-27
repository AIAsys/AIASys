import { Badge } from "@/components/ui/badge";
import type {
  RuntimeDatabaseExecuteResponse,
  RuntimeDatabaseQueryResponse,
} from "@/types/databaseConnectors";

type QueryResultState =
  | { type: "query"; data: RuntimeDatabaseQueryResponse }
  | { type: "execute"; data: RuntimeDatabaseExecuteResponse }
  | null;

function formatCellValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "NULL";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

interface QueryResultPanelProps {
  result: QueryResultState;
}

export function QueryResultPanel({ result }: QueryResultPanelProps) {
  return (
    <div className="min-h-0 flex-1 flex flex-col overflow-hidden">
      <div className="min-h-0 flex-1 overflow-auto">
        {!result ? (
          <div className="flex h-full items-center justify-center px-6 text-center text-[12px] text-muted-foreground">
            执行 SQL 后结果将显示在这里。
          </div>
        ) : null}

        {result?.type === "execute" ? (
          <div className="p-3">
            <p className="text-[12px] text-foreground">
              {result.data.message || "执行完成"}
            </p>
          </div>
        ) : null}

        {result?.type === "query" ? (
          <div className="p-3">
            {result.data.columns.length === 0 ? (
              <div className="px-4 py-6 text-center text-[11px] text-muted-foreground">
                查询已执行，但当前结果没有可展示的列。
              </div>
            ) : (
              <div className="overflow-auto">
                <table
                  className="w-full text-left text-[11px]"
                  style={{ tableLayout: "auto" }}
                >
                  <thead className="sticky top-0 bg-muted/60">
                    <tr>
                      {result.data.columns.map((column, colIdx) => (
                        <th
                          key={`h-${colIdx}`}
                          className="border-b border-border px-2 py-1.5 font-medium text-muted-foreground whitespace-nowrap"
                        >
                          {column}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {result.data.rows.map((row, index) => (
                      <tr
                        key={`${index}-${row.length}`}
                        className="border-b border-border/60 last:border-b-0"
                      >
                        {result.data.columns.map((_column, columnIndex) => (
                          <td
                            key={`c${columnIndex}-r${index}`}
                            className="px-2 py-1.5 align-top font-mono text-[10px] text-foreground max-w-[240px] truncate"
                            title={formatCellValue(row[columnIndex])}
                          >
                            {formatCellValue(row[columnIndex])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ) : null}
      </div>

      {result ? (
        <div className="flex-shrink-0 border-t border-border px-3 py-1.5 flex items-center gap-3 text-[11px] text-muted-foreground bg-muted/20">
          {result.type === "query" ? (
            <>
              <span className="flex items-center gap-1">
                <span className="font-medium text-foreground">
                  {result.data.row_count}
                </span>
                <span>行</span>
              </span>
              {result.data.applied_limit !== null ? (
                <span className="flex items-center gap-1">
                  <span>limit</span>
                  <span className="font-medium text-foreground">
                    {result.data.applied_limit}
                  </span>
                </span>
              ) : null}
              {result.data.truncated ? (
                <Badge variant="outline" className="text-[10px] h-5">
                  结果已截断
                </Badge>
              ) : null}
            </>
          ) : (
            <span className="flex items-center gap-1">
              <span className="font-medium text-foreground">
                {result.data.affected_rows}
              </span>
              <span>行受影响</span>
            </span>
          )}
          {result.data.duration_ms !== null ? (
            <span className="ml-auto flex items-center gap-1">
              <span>{result.data.duration_ms} ms</span>
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
