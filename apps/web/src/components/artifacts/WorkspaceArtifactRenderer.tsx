import { Suspense, lazy, memo, useMemo, useState } from "react";
import {
  Download,
  Eye,
  FileText,
  Link2,
  Maximize2,
  Presentation,
} from "lucide-react";

import { MarkdownImage } from "@/components/chat/MarkdownImage";
import {
  getPreviewUrlOptions,
  inferPreviewType,
  type PreviewFile,
  type WorkspaceRenderableFileType,
} from "@/utils/filePreviewRegistry";
import {
  inferWorkspaceRenderableFileType,
  resolveWorkspaceDownloadUrl,
  resolveWorkspaceFileUrl,
  workspacePathToFilename,
} from "@/utils/workspaceFiles";
import { CsvArtifactRenderer } from "./CsvArtifactRenderer";

const LazyEChartsArtifactRenderer = lazy(() =>
  import("@/components/charts/EChartsArtifactRenderer/index").then((module) => ({
    default: module.EChartsArtifactRenderer,
  })),
);

export type WorkspaceArtifactType = WorkspaceRenderableFileType;

interface WorkspaceArtifactRendererProps {
  artifactPath: string;
  artifactType?: string;
  sessionId?: string;
  token?: string;
  variant?: "chat" | "workspace";
  className?: string;
  alt?: string;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
  onOpenInBrowserTab?: (path: string) => void;
}

function normalizeArtifactType(
  artifactType: string | undefined,
  artifactPath: string,
): WorkspaceArtifactType | null {
  return inferWorkspaceRenderableFileType(artifactPath, artifactType);
}

function ArtifactActionBar({
  previewFile,
  onOpenInMainCanvas,
  openLabel = "查看详情",
}: {
  previewFile: PreviewFile;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
  openLabel?: string;
}) {
  return (
    <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
      {onOpenInMainCanvas ? (
        <button
          type="button"
          onClick={() => onOpenInMainCanvas(previewFile)}
          className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
        >
          <Maximize2 className="h-3.5 w-3.5" />
          {openLabel}
        </button>
      ) : null}
      <a
        href={previewFile.downloadUrl || previewFile.url}
        download={previewFile.name}
        className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
      >
        <Download className="h-3.5 w-3.5" />
        下载
      </a>
    </div>
  );
}

function ArtifactWrapper({
  children,
  previewFile,
  onOpenInMainCanvas,
}: {
  children: React.ReactNode;
  previewFile?: PreviewFile | null;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
}) {
  return (
    <div className="not-prose my-4 space-y-2">
      {children}
      {previewFile ? (
        <ArtifactActionBar
          previewFile={previewFile}
          onOpenInMainCanvas={onOpenInMainCanvas}
        />
      ) : null}
    </div>
  );
}

function PdfArtifactCard({
  previewFile,
  onOpenInMainCanvas,
}: {
  previewFile: PreviewFile;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
}) {
  const [showInlinePreview, setShowInlinePreview] = useState(false);
  const viewerUrl = `${previewFile.url}#toolbar=0&navpanes=0&view=FitH`;

  return (
    <div className="not-prose my-4 rounded-xl border border-border bg-muted/10 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="rounded-lg bg-background p-2 text-muted-foreground">
            <FileText className="h-4 w-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-foreground">
              {previewFile.name}
            </div>
            <div className="mt-1 text-xs leading-5 text-muted-foreground">
              PDF 默认按轻量卡片展示，避免聊天区直接加载重预览。需要时可以切换成内嵌预览。
            </div>
          </div>
        </div>
        <div className="flex flex-shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={() => setShowInlinePreview(false)}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
              !showInlinePreview
                ? "border-primary/30 bg-primary/10 text-primary"
                : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
            }`}
          >
            <Link2 className="h-3.5 w-3.5" />
            标题卡片
          </button>
          <button
            type="button"
            onClick={() => setShowInlinePreview(true)}
            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11px] font-medium transition-colors ${
              showInlinePreview
                ? "border-primary/30 bg-primary/10 text-primary"
                : "border-border bg-background text-muted-foreground hover:border-primary/30 hover:bg-primary/10 hover:text-primary"
            }`}
          >
            <Eye className="h-3.5 w-3.5" />
            内嵌预览
          </button>
        </div>
      </div>

      {showInlinePreview ? (
        <div className="mt-3 overflow-hidden rounded-xl border border-border bg-background">
          <iframe
            src={viewerUrl}
            title={previewFile.name}
            className="h-[420px] w-full border-0"
          />
        </div>
      ) : null}

      <ArtifactActionBar
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      />
    </div>
  );
}

function MarkdownArtifactCard({
  previewFile,
  onOpenInMainCanvas,
}: {
  previewFile: PreviewFile;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
}) {
  return (
    <div className="not-prose my-4 rounded-xl border border-border bg-muted/10 px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-background p-2 text-muted-foreground">
          <FileText className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-foreground">
            {previewFile.name}
          </div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            Markdown 文档按轻量卡片展示，点击查看详情后在主画布阅读完整内容。
          </div>
        </div>
      </div>

      <ArtifactActionBar
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      />
    </div>
  );
}

function OfficeArtifactCard({
  previewFile,
  onOpenInMainCanvas,
  kind,
}: {
  previewFile: PreviewFile;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
  kind: "word" | "presentation";
}) {
  const Icon = kind === "presentation" ? Presentation : FileText;
  const label = kind === "presentation" ? "PPT" : "Word";

  return (
    <div className="not-prose my-4 rounded-xl border border-border bg-muted/10 px-4 py-3">
      <div className="flex items-start gap-3">
        <div className="rounded-lg bg-background p-2 text-muted-foreground">
          <Icon className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-foreground">
            {previewFile.name}
          </div>
          <div className="mt-1 text-xs leading-5 text-muted-foreground">
            {label} 文件按轻量卡片展示，点击查看详情后在主画布预览完整内容。
          </div>
        </div>
      </div>

      <ArtifactActionBar
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      />
    </div>
  );
}

function UnsupportedArtifact({
  artifactPath,
  artifactType,
  previewFile,
  onOpenInMainCanvas,
  onOpenInBrowserTab,
}: Pick<
  WorkspaceArtifactRendererProps,
  "artifactPath" | "artifactType" | "onOpenInMainCanvas" | "onOpenInBrowserTab"
> & {
  previewFile?: PreviewFile | null;
}) {
  const normalizedPath = artifactPath.replace(/\\/g, "/");
  const displayName = normalizedPath.split("/").pop() || normalizedPath;
  const isHtml = normalizedPath.endsWith(".html");

  return (
    <div className="not-prose my-4 rounded-xl border border-dashed border-border bg-muted/20 px-4 py-3 text-sm text-muted-foreground">
      <div>
        暂不支持在聊天正文中直接预览该文件类型：{displayName}
        {artifactType ? `（type=${artifactType}）` : "（缺少可识别的 type）"}
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-end gap-2">
        {previewFile && onOpenInMainCanvas ? (
          <button
            type="button"
            onClick={() => onOpenInMainCanvas(previewFile)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
          >
            <Maximize2 className="h-3.5 w-3.5" />
            查看详情
          </button>
        ) : null}
        {isHtml && onOpenInBrowserTab ? (
          <button
            type="button"
            onClick={() => onOpenInBrowserTab(normalizedPath)}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:border-accent/40 hover:bg-accent/10 hover:text-accent"
          >
            <Eye className="h-3.5 w-3.5" />
            在浏览器打开
          </button>
        ) : null}
        {previewFile ? (
          <a
            href={previewFile.downloadUrl || previewFile.url}
            download
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
          >
            <Download className="h-3.5 w-3.5" />
            下载原文件
          </a>
        ) : null}
      </div>
    </div>
  );
}

export const WorkspaceArtifactRenderer = memo(function WorkspaceArtifactRenderer({
  artifactPath,
  artifactType,
  sessionId,
  token,
  variant = "chat",
  className,
  alt,
  onOpenInMainCanvas,
  onOpenInBrowserTab,
}: WorkspaceArtifactRendererProps) {
  const resolvedType = normalizeArtifactType(artifactType, artifactPath);
  const previewFile = useMemo<PreviewFile | null>(() => {
    if (!resolvedType) {
      return null;
    }

    const fileName = workspacePathToFilename(artifactPath);
    if (!fileName) {
      return null;
    }
    const previewType = inferPreviewType(fileName, artifactType);

    return {
      name: fileName,
      url: resolveWorkspaceFileUrl(
        artifactPath,
        sessionId,
        token,
        getPreviewUrlOptions(previewType),
      ),
      downloadUrl: resolveWorkspaceDownloadUrl(artifactPath, sessionId, token),
      type: previewType,
    };
  }, [artifactPath, artifactType, resolvedType, sessionId, token]);

  if (resolvedType === "image") {
    return (
      <ArtifactWrapper
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      >
        <MarkdownImage
          src={artifactPath}
          alt={alt}
          token={token}
          sessionId={sessionId}
          className={className}
        />
      </ArtifactWrapper>
    );
  }

  if (resolvedType === "csv") {
    return (
      <ArtifactWrapper
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      >
        <CsvArtifactRenderer
          artifactPath={artifactPath}
          sessionId={sessionId}
          token={token}
          variant={variant}
          className={className}
        />
      </ArtifactWrapper>
    );
  }

  if (resolvedType === "echarts") {
    return (
      <ArtifactWrapper
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      >
        <Suspense
          fallback={
            <div className="rounded-xl border border-border bg-muted/20 px-4 py-6 text-xs text-muted-foreground">
              正在加载图表渲染器...
            </div>
          }
        >
          <LazyEChartsArtifactRenderer
            artifactPath={artifactPath}
            sessionId={sessionId}
            token={token}
            variant={variant}
            className={className}
          />
        </Suspense>
      </ArtifactWrapper>
    );
  }

  if (resolvedType === "pdf" && previewFile) {
    return (
      <PdfArtifactCard
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      />
    );
  }

  if (resolvedType === "markdown" && previewFile) {
    return (
      <MarkdownArtifactCard
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
      />
    );
  }

  if (
    (resolvedType === "word" || resolvedType === "presentation") &&
    previewFile
  ) {
    return (
      <OfficeArtifactCard
        previewFile={previewFile}
        onOpenInMainCanvas={onOpenInMainCanvas}
        kind={resolvedType}
      />
    );
  }

  return (
    <UnsupportedArtifact
      artifactPath={artifactPath}
      artifactType={artifactType}
      previewFile={previewFile}
      onOpenInMainCanvas={onOpenInMainCanvas}
      onOpenInBrowserTab={onOpenInBrowserTab}
    />
  );
});
