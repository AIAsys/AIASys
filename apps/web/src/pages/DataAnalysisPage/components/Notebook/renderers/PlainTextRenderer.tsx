import type { MimeRendererProps } from "./types";

function toOutputText(payload: unknown): string {
  if (Array.isArray(payload)) {
    return payload.map((item) => String(item)).join("");
  }
  return String(payload ?? "");
}

export function PlainTextRenderer({ data }: MimeRendererProps) {
  return (
    <pre className="overflow-x-auto rounded-xl bg-muted px-4 py-3 text-xs text-foreground">
      {toOutputText(data)}
    </pre>
  );
}
