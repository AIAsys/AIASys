import { AlertCircle, Download, Loader2, Presentation } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api/httpClient";

interface PptPreviewProps {
  url: string;
  downloadUrl?: string;
  fileName: string;
}

type PreviewStatus = "loading" | "ready" | "unsupported" | "error";

function getExtension(fileName: string) {
  return fileName.split(".").pop()?.toLowerCase() ?? "";
}

function resolvePreviewSize(container: HTMLElement | null) {
  const availableWidth = Math.max(320, (container?.clientWidth ?? 960) - 32);
  const width = Math.min(availableWidth, 1120);
  return {
    width,
    height: Math.round(width * 9 / 16),
  };
}

export function PptPreview({ url, downloadUrl, fileName }: PptPreviewProps) {
  const viewportRef = useRef<HTMLDivElement | null>(null);
  const previewRef = useRef<HTMLDivElement | null>(null);
  const destroyRef = useRef<(() => void) | null>(null);
  const [status, setStatus] = useState<PreviewStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const extension = getExtension(fileName);
    if (extension !== "pptx") {
      setStatus("unsupported");
      setError(null);
      previewRef.current?.replaceChildren();
      destroyRef.current?.();
      destroyRef.current = null;
      return;
    }

    if (!url) {
      setStatus("error");
      setError("缺少文件地址");
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    const loadPresentation = async () => {
      setStatus("loading");
      setError(null);
      destroyRef.current?.();
      destroyRef.current = null;
      previewRef.current?.replaceChildren();

      try {
        const response = await apiFetch(url, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const arrayBuffer = await response.arrayBuffer();
        if (cancelled) {
          return;
        }

        const previewContainer = previewRef.current;
        if (!previewContainer) {
          return;
        }

        const { init } = await import("pptx-preview");
        if (cancelled) {
          return;
        }

        const { width, height } = resolvePreviewSize(viewportRef.current);
        const previewer = init(previewContainer, {
          width,
          height,
          mode: "slide",
        });
        destroyRef.current = () => previewer.destroy();

        await previewer.preview(arrayBuffer);

        if (!cancelled) {
          setStatus("ready");
        }
      } catch (err) {
        if (controller.signal.aborted || cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : "加载失败");
        setStatus("error");
      }
    };

    void loadPresentation();

    const preview = previewRef.current;
    return () => {
      cancelled = true;
      controller.abort();
      destroyRef.current?.();
      destroyRef.current = null;
      preview?.replaceChildren();
    };
  }, [fileName, url]);

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center justify-between border-b border-border bg-background px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Presentation className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
          <span
            className="truncate text-xs font-mono text-muted-foreground"
            title={fileName}
          >
            {fileName}
          </span>
        </div>
        <a
          href={downloadUrl || url}
          download={fileName}
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          title="下载 PPT 文件"
        >
          <Download className="h-3.5 w-3.5" />
        </a>
      </div>

      <div
        ref={viewportRef}
        className="relative min-h-0 flex-1 overflow-auto bg-muted/10 p-4"
      >
        <div
          ref={previewRef}
          className="mx-auto min-h-[260px] max-w-[1160px] [&_.pptx-preview-wrapper]:!mx-auto"
        />

        {status === "loading" ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/80 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span className="text-sm">加载 PPT 预览中...</span>
          </div>
        ) : null}

        {status === "unsupported" ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <Presentation className="h-7 w-7" />
            </div>
            <div className="text-sm font-medium text-foreground">
              旧版 PPT 文件暂不能在线预览
            </div>
            <div className="mt-2 max-w-sm text-xs leading-5 text-muted-foreground">
              当前支持 `.pptx` 文件预览。此文件可以下载后查看。
            </div>
          </div>
        ) : null}

        {status === "error" ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-error-container text-error">
              <AlertCircle className="h-7 w-7" />
            </div>
            <div className="text-sm font-medium text-foreground">
              PPT 预览加载失败
            </div>
            <div className="mt-2 max-w-sm break-all text-xs leading-5 text-muted-foreground">
              {error || "请下载后查看。"}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
