import { useMemo } from "react";
import type { MimeRendererProps } from "./types";

function toOutputText(payload: unknown): string {
  if (Array.isArray(payload)) {
    return payload.map((item) => String(item)).join("");
  }
  return String(payload ?? "");
}

export function HtmlRenderer({ data }: MimeRendererProps) {
  const html = useMemo(() => toOutputText(data), [data]);

  if (!html.trim()) {
    return null;
  }

  // 用 sandboxed iframe 隔离 HTML 输出，避免样式/脚本污染主页面
  const srcDoc = html;

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-background">
      <iframe
        srcDoc={srcDoc}
        sandbox="allow-scripts"
        className="w-full min-h-[120px]"
        style={{ border: "none" }}
        title="Notebook HTML output"
      />
    </div>
  );
}
