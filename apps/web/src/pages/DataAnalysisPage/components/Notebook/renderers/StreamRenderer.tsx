import type { OutputRendererProps } from "./types";

function toOutputText(payload: unknown): string {
  if (Array.isArray(payload)) {
    return payload.map((item) => String(item)).join("");
  }
  return String(payload ?? "");
}

export function StreamRenderer({ output }: OutputRendererProps) {
  return (
    <pre className="overflow-x-auto rounded-xl bg-foreground px-4 py-3 text-xs text-primary-foreground">
      {toOutputText(output.text)}
    </pre>
  );
}
