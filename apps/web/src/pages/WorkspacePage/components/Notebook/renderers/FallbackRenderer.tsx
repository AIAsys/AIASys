import type { MimeRendererProps } from "./types";

export function FallbackRenderer({ data, mimeType }: MimeRendererProps) {
  const preview = typeof data === "string" ? data : JSON.stringify(data);
  const truncated =
    preview.length > 500 ? preview.slice(0, 500) + "\n... (truncated)" : preview;

  return (
    <div className="rounded-xl border border-border bg-muted/40 px-4 py-3 text-xs">
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {mimeType}
      </div>
      <pre className="whitespace-pre-wrap font-mono text-muted-foreground">
        {truncated}
      </pre>
    </div>
  );
}
