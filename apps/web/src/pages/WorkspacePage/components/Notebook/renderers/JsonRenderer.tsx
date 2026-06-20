import { useMemo, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import type { MimeRendererProps } from "./types";

function JsonPreview({ data, depth = 0 }: { data: unknown; depth?: number }) {
  const [expanded, setExpanded] = useState(depth < 1);

  if (data === null) {
    return <span className="text-muted-foreground">null</span>;
  }
  if (typeof data === "boolean") {
    return <span className="text-primary">{String(data)}</span>;
  }
  if (typeof data === "number") {
    return <span className="text-primary">{String(data)}</span>;
  }
  if (typeof data === "string") {
    const preview = data.length > 120 ? `"${data.slice(0, 120)}..."` : `"${data}"`;
    return <span className="text-success">{preview}</span>;
  }
  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span className="text-muted-foreground">[]</span>;
    }
    return (
      <div>
        <button
          type="button"
          className="inline-flex items-center gap-0.5 text-xs hover:opacity-70"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          <span className="text-muted-foreground">[{data.length}]</span>
        </button>
        {expanded ? (
          <div className="ml-3 border-l border-border pl-2">
            {/* key={`json-${i}`} — JSON array items may not have stable id */}
            {data.map((item, i) => (
              <div key={`json-${i}`} className="py-0.5">
                <JsonPreview data={item} depth={depth + 1} />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  }
  if (typeof data === "object") {
    const entries = Object.entries(data as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className="text-muted-foreground">{"{}"}</span>;
    }
    return (
      <div>
        <button
          type="button"
          className="inline-flex items-center gap-0.5 text-xs hover:opacity-70"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3" />
          ) : (
            <ChevronRight className="h-3 w-3" />
          )}
          <span className="text-muted-foreground">{"{"}{entries.length}{"}"}</span>
        </button>
        {expanded ? (
          <div className="ml-3 border-l border-border pl-2">
            {entries.map(([key, value]) => (
              <div key={key} className="py-0.5">
                <span className="text-foreground">{key}:</span>{" "}
                <JsonPreview data={value} depth={depth + 1} />
              </div>
            ))}
          </div>
        ) : null}
      </div>
    );
  }
  return <span>{String(data)}</span>;
}

export function JsonRenderer({ data }: MimeRendererProps) {
  const parsed = useMemo(() => {
    if (typeof data === "string") {
      try {
        return JSON.parse(data);
      } catch {
        return data;
      }
    }
    return data;
  }, [data]);

  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-muted/50 px-4 py-3 text-xs font-mono">
      <JsonPreview data={parsed} />
    </div>
  );
}
