import { ImageLightbox } from "@/components/ui/image-lightbox";
import type { MimeRendererProps } from "./types";

export function ImageRenderer({ data, mimeType }: MimeRendererProps) {
  const raw = typeof data === "string" ? data : "";
  if (!raw) {
    return (
      <div className="rounded-xl border border-border bg-muted px-4 py-3 text-xs text-muted-foreground">
        [空图片数据]
      </div>
    );
  }

  const src = raw.startsWith("data:")
    ? raw
    : `data:${mimeType};base64,${raw}`;

  return (
    <ImageLightbox
      src={src}
      alt="Notebook output"
      className="max-w-full rounded-xl border border-border bg-white"
      triggerClassName="rounded-xl"
    />
  );
}
