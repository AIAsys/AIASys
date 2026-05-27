import type { OutputRendererProps } from "./types";

function toOutputText(payload: unknown): string {
  if (Array.isArray(payload)) {
    return payload.map((item) => String(item)).join("\n");
  }
  return String(payload ?? "");
}

export function ErrorRenderer({ output }: OutputRendererProps) {
  const traceback = Array.isArray(output.traceback)
    ? output.traceback.map((item) => String(item)).join("\n")
    : toOutputText(output.traceback);

  return (
    <div className="rounded-xl border border-error/20 bg-error-container px-4 py-3 text-xs text-error">
      <div className="font-semibold">{String(output.ename || output.name || "Error")}</div>
      {output.evalue ? (
        <div className="mt-1 font-mono opacity-90">{String(output.evalue)}</div>
      ) : null}
      {traceback ? (
        <pre className="mt-2 whitespace-pre-wrap font-mono">{traceback}</pre>
      ) : null}
    </div>
  );
}
