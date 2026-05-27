import { AlertCircle, Loader2, Play, ShieldAlert, SquareTerminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import Editor from "react-simple-code-editor";
import Prism from "prismjs";
import "prismjs/components/prism-sql";

function highlightCode(code: string) {
  return Prism.highlight(code, Prism.languages.sql, "sql");
}

interface SqlQueryPanelProps {
  sql: string;
  onSqlChange: (sql: string) => void;
  queryLimitInput: string;
  onLimitChange: (limit: string) => void;
  runningAction: "query" | "execute" | null;
  canExecute: boolean;
  disabled: boolean;
  error: string | null;
  onRunQuery: () => void;
  onRunExecute: () => void;
}

export function SqlQueryPanel({
  sql,
  onSqlChange,
  queryLimitInput,
  onLimitChange,
  runningAction,
  canExecute,
  disabled,
  error,
  onRunQuery,
  onRunExecute,
}: SqlQueryPanelProps) {
  return (
    <div className="flex-shrink-0 border-b border-border p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <SquareTerminal className="h-4 w-4 text-muted-foreground" />
          <span className="text-[12px] font-medium">SQL</span>
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          <Input
            value={queryLimitInput}
            onChange={(e) => onLimitChange(e.target.value)}
            inputMode="numeric"
            placeholder="100"
            className="h-7 w-12 text-[11px]"
            title="查询行数上限"
          />
          <Button
            size="sm"
            className="h-7 shrink-0 whitespace-nowrap px-2 text-[11px]"
            onClick={onRunQuery}
            disabled={disabled || runningAction !== null}
          >
            {runningAction === "query" ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
            ) : (
              <Play className="h-3.5 w-3.5 mr-1" />
            )}
            查询
          </Button>
          {canExecute && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 shrink-0 whitespace-nowrap px-2 text-[11px]"
              onClick={onRunExecute}
              disabled={disabled || runningAction !== null}
            >
              {runningAction === "execute" ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
              ) : (
                <ShieldAlert className="h-3.5 w-3.5 mr-1" />
              )}
              写入
            </Button>
          )}
        </div>
      </div>

      <div
        className="relative rounded border border-border bg-muted/30"
        style={{ minHeight: "150px" }}
      >
        <Editor
          value={sql}
          onValueChange={onSqlChange}
          highlight={highlightCode}
          padding={12}
          className="font-mono text-[12px] leading-5"
          textareaClassName="focus:outline-none bg-transparent"
          preClassName="language-sql m-0 p-0 bg-transparent min-h-[150px]"
          placeholder="例如：SELECT * FROM your_table LIMIT 20;"
          style={{
            fontFamily:
              'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
            fontSize: 12,
            lineHeight: "20px",
            minHeight: "150px",
          }}
        />
      </div>

      {error ? (
        <div className="rounded border border-destructive/30 bg-destructive/5 px-2.5 py-1.5 text-[12px] text-destructive">
          <div className="flex items-start gap-1.5">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{error}</span>
          </div>
        </div>
      ) : null}
    </div>
  );
}
