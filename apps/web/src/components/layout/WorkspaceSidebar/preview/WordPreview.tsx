import { AlertCircle, Download, FileText, Loader2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api/httpClient";

interface WordPreviewProps {
  url: string;
  downloadUrl?: string;
  fileName: string;
}

type PreviewStatus = "loading" | "ready" | "unsupported" | "too-large" | "error";

const MAX_WORD_PREVIEW_SIZE = 25 * 1024 * 1024;

function getExtension(fileName: string) {
  return fileName.split(".").pop()?.toLowerCase() ?? "";
}

function formatFileSize(bytes: number) {
  if (bytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function WordPreview({ url, downloadUrl, fileName }: WordPreviewProps) {
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const styleRef = useRef<HTMLDivElement | null>(null);
  const [status, setStatus] = useState<PreviewStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [fileSize, setFileSize] = useState<number>(0);

  useEffect(() => {
    const extension = getExtension(fileName);
    if (extension !== "docx") {
      setStatus("unsupported");
      setError(null);
      setFileSize(0);
      bodyRef.current?.replaceChildren();
      styleRef.current?.replaceChildren();
      return;
    }

    if (!url) {
      setStatus("error");
      setError("缺少文件地址");
      setFileSize(0);
      return;
    }

    const controller = new AbortController();
    let cancelled = false;

    const loadDocument = async () => {
      setStatus("loading");
      setError(null);
      setFileSize(0);
      bodyRef.current?.replaceChildren();
      styleRef.current?.replaceChildren();

      try {
        const response = await apiFetch(url, { signal: controller.signal });
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const blob = await response.blob();
        if (cancelled) {
          return;
        }

        setFileSize(blob.size);
        if (blob.size > MAX_WORD_PREVIEW_SIZE) {
          setStatus("too-large");
          return;
        }

        const bodyContainer = bodyRef.current;
        if (!bodyContainer) {
          return;
        }

        const { renderAsync } = await import("docx-preview");
        if (cancelled) {
          return;
        }

        await renderAsync(blob, bodyContainer, styleRef.current ?? undefined, {
          className: "aiasys-docx",
          inWrapper: true,
          breakPages: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          ignoreLastRenderedPageBreak: false,
          renderHeaders: true,
          renderFooters: true,
          renderFootnotes: true,
          renderEndnotes: true,
          renderComments: false,
          renderAltChunks: true,
          useBase64URL: true,
        });

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

    void loadDocument();

    return () => {
      cancelled = true;
      controller.abort();
      bodyRef.current?.replaceChildren();
      styleRef.current?.replaceChildren();
    };
  }, [fileName, url]);

  return (
    <div className="flex h-full flex-col bg-background">
      <div className="flex items-center justify-between border-b border-border bg-background px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <FileText className="h-3.5 w-3.5 flex-shrink-0 text-muted-foreground" />
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
          title="下载 Word 文件"
        >
          <Download className="h-3.5 w-3.5" />
        </a>
      </div>

      <div className="relative min-h-0 flex-1 overflow-auto bg-muted/10 p-4">
        <div ref={styleRef} />
        <div
          ref={bodyRef}
          className="mx-auto max-w-[980px] overflow-hidden rounded-md bg-background text-foreground shadow-sm [&_.aiasys-docx-wrapper]:!bg-transparent [&_.aiasys-docx-wrapper]:!p-0"
        />

        {status === "loading" ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/80 text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span className="text-sm">加载 Word 预览中...</span>
          </div>
        ) : null}

        {status === "unsupported" ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <FileText className="h-7 w-7" />
            </div>
            <div className="text-sm font-medium text-foreground">
              旧版 Word 文件暂不能在线预览
            </div>
            <div className="mt-2 max-w-sm text-xs leading-5 text-muted-foreground">
              当前支持 `.docx` 文件预览。此文件可以下载后查看。
            </div>
          </div>
        ) : null}

        {status === "too-large" ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-warning-container text-warning">
              <AlertCircle className="h-7 w-7" />
            </div>
            <div className="text-sm font-medium text-foreground">
              文件过大，无法预览
            </div>
            <div className="mt-2 text-xs leading-5 text-muted-foreground">
              当前文件 {formatFileSize(fileSize)}，在线预览上限为{" "}
              {formatFileSize(MAX_WORD_PREVIEW_SIZE)}。
            </div>
          </div>
        ) : null}

        {status === "error" ? (
          <div className="flex h-full min-h-[260px] flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-xl bg-error-container text-error">
              <AlertCircle className="h-7 w-7" />
            </div>
            <div className="text-sm font-medium text-foreground">
              Word 预览加载失败
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
