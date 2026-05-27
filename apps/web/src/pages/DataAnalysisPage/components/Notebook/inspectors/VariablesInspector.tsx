import { Badge } from "@/components/ui/badge";
import type { NotebookVariableSummary } from "@/types/notebook";

interface VariablesInspectorProps {
  variables: NotebookVariableSummary[];
}

export function VariablesInspector({ variables }: VariablesInspectorProps) {
  if (variables.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-border/60 px-3 py-4 text-xs text-muted-foreground">
        当前 kernel 还没有可展示的用户变量。
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {variables.map((variable) => (
        <div key={variable.name} className="rounded-xl border border-border px-3 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-foreground">{variable.name}</div>
            <Badge variant="outline">{variable.type_name}</Badge>
          </div>
          <div className="mt-1 text-xs text-muted-foreground">
            {variable.module_name || "builtins"}
            {variable.size != null ? ` · size=${variable.size}` : ""}
            {variable.shape != null
              ? ` · shape=${Array.isArray(variable.shape) ? variable.shape.join("x") : String(variable.shape)}`
              : ""}
          </div>
          {variable.preview ? (
            <pre className="mt-2 overflow-x-auto rounded-lg bg-muted px-3 py-2 text-xs text-foreground">
              {variable.preview}
            </pre>
          ) : null}
        </div>
      ))}
    </div>
  );
}
