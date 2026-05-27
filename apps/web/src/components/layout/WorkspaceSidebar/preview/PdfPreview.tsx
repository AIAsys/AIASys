import { Download, ExternalLink, FileText } from "lucide-react";

interface PdfPreviewProps {
  url: string;
  downloadUrl?: string;
  fileName: string;
}

export function PdfPreview({ url, downloadUrl, fileName }: PdfPreviewProps) {
  const viewerUrl = url ? `${url}#toolbar=0&navpanes=0&view=FitH` : "";

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
        <div className="flex items-center gap-1">
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="在新标签页打开"
          >
            <ExternalLink className="h-3.5 w-3.5" />
          </a>
          <a
            href={downloadUrl || url}
            download={fileName}
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="下载 PDF"
          >
            <Download className="h-3.5 w-3.5" />
          </a>
        </div>
      </div>

      <div className="min-h-0 flex-1 bg-muted/10">
        {viewerUrl ? (
          <iframe
            src={viewerUrl}
            title={fileName}
            className="h-full w-full border-0"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            当前 PDF 暂时无法预览
          </div>
        )}
      </div>
    </div>
  );
}
