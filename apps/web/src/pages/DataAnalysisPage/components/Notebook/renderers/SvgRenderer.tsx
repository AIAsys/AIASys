import { useMemo } from "react";
import type { MimeRendererProps } from "./types";

export function SvgRenderer({ data }: MimeRendererProps) {
  const svgSrc = useMemo(() => {
    const raw = typeof data === "string" ? data : "";
    if (!raw) return "";
    // 已经是 data URL 就直接用，否则包一层
    return raw.startsWith("data:") ? raw : `data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(raw)))}`;
  }, [data]);

  if (!svgSrc) {
    return (
      <div className="rounded-xl border border-border bg-muted px-4 py-3 text-xs text-muted-foreground">
        [空 SVG 数据]
      </div>
    );
  }

  return (
    <img
      src={svgSrc}
      alt="Notebook SVG output"
      className="max-w-full rounded-xl border border-border bg-white"
    />
  );
}
