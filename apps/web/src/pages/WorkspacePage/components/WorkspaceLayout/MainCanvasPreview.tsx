import { useEffect, useMemo, useState } from "react";
import { Download, FileText, Info, Maximize2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  FilePreviewPanel,
  type PreviewFile,
} from "@/components/layout/WorkspaceSidebar/preview";
import { useAuthContext } from "@/contexts/AuthContext";
import {
  getPreviewCategoryLabel,
  getPreviewTypeLabel,
} from "@/utils/filePreviewRegistry";
import { CanvasActionMenu } from "@/components/workspace/CanvasActionMenu";
import { isGenericallyEditable } from "@/utils/workspaceFileEditing";
import type { WorkspaceFile } from "@/types/task";

interface MainCanvasPreviewProps {
  file: PreviewFile;
  sessionId?: string | null;
  onClose: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
  onReadFileContent?: (filename: string) => Promise<string | null>;
  workspaceId?: string;
  workspaceFiles?: WorkspaceFile[];
  onOpenWorkspaceFile?: (filename: string) => void;
  onOpenPreviewFile?: (file: PreviewFile) => void;
  onEditFile?: (file: PreviewFile) => void;
}

function getFileExtension(fileName: string): string {
  const extension = fileName.split(".").pop();
  return extension ? extension.toUpperCase() : "FILE";
}

function normalizeFilePath(value?: string | null): string {
  if (!value) {
    return "";
  }

  let normalized = value.trim();
  try {
    const parsed = new URL(normalized, window.location.origin);
    normalized = parsed.pathname;
  } catch {
    normalized = normalized.split("?")[0]?.split("#")[0] ?? normalized;
  }

  try {
    normalized = decodeURIComponent(normalized);
  } catch {
    normalized = normalized.trim();
  }

  return normalized
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/^\.\//, "")
    .replace(/^workspace\//, "")
    .replace(/^global\//, "")
    .trim();
}

function basename(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  return normalized.split("/").filter(Boolean).pop() ?? normalized;
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "未记录";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function formatFileSize(size?: number | null): string {
  if (!Number.isFinite(size ?? NaN) || !size || size <= 0) {
    return "未知大小";
  }
  const units = ["B", "KB", "MB", "GB"];
  let value = size;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function getScopeLabel(file: PreviewFile): string {
  return file.meta?._globalResource ? "全局工作区" : "当前工作区";
}

function getReadablePath(file: PreviewFile): string {
  const metaPath = file.meta?.relative_path;
  const logicalPath =
    typeof metaPath === "string" && metaPath.trim()
      ? metaPath
      : file.name;
  return normalizeFilePath(logicalPath) || file.name;
}

function DetailRow({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div
        className="mt-1 truncate font-medium text-foreground"
        title={value || "未记录"}
      >
        {value || "未记录"}
      </div>
    </div>
  );
}

export function MainCanvasPreview({
  file,
  sessionId,
  onClose,
  closeLabel = "关闭标签",
  onSplitRight,
  onSplitDown,
  onReadFileContent,
  workspaceId,
  workspaceFiles = [],
  onOpenWorkspaceFile,
  onOpenPreviewFile,
  onEditFile,
}: MainCanvasPreviewProps) {
  const { session } = useAuthContext();
  const token = session?.token;
  const fileTypeLabel = getPreviewTypeLabel(file.type);
  const fileCategoryLabel = getPreviewCategoryLabel(file.type);
  const extension = getFileExtension(file.name);
  const [isDetailsOpen, setIsDetailsOpen] = useState(false);
  const [toolbarEl, setToolbarEl] = useState<HTMLDivElement | null>(null);
  const [immersiveToolbarEl, setImmersiveToolbarEl] =
    useState<HTMLDivElement | null>(null);
  const [isImmersiveOpen, setIsImmersiveOpen] = useState(false);
  const readablePath = getReadablePath(file);
  const fileName = basename(readablePath);
  const scopeLabel = getScopeLabel(file);
  const canEditFile =
    isGenericallyEditable(file.name) &&
    Boolean(sessionId || file.meta?._globalResource);
  const nearbyFiles = useMemo(
    () =>
      workspaceFiles
        .filter((item) => normalizeFilePath(item.name) !== readablePath)
        .slice(0, 6),
    [workspaceFiles, readablePath],
  );

  useEffect(() => {
    if (!isImmersiveOpen) {
      return;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsImmersiveOpen(false);
        setIsDetailsOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isImmersiveOpen]);

  const openImmersivePreview = () => {
    setIsDetailsOpen(false);
    setIsImmersiveOpen(true);
  };

  const detailsPanel = (
    <aside className="absolute bottom-3 right-3 top-3 z-20 flex w-[min(360px,calc(100%-1.5rem))] flex-col overflow-hidden rounded-xl border border-border bg-white shadow-2xl">
      <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="text-sm font-semibold text-foreground">
            文件信息
          </div>
          <div className="mt-0.5 truncate text-[11px] text-muted-foreground">
            {readablePath}
          </div>
        </div>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 w-8 rounded-lg p-0"
          aria-label="关闭文件信息"
          onClick={() => setIsDetailsOpen(false)}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        <div className="space-y-4">
          <section className="rounded-xl border border-border bg-muted/60 p-4">
            <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Info className="h-4 w-4 text-muted-foreground" />
              本地属性
            </div>
            <div className="mt-3 space-y-3 text-sm">
              <DetailRow label="文件名" value={fileName} />
              <DetailRow label="路径" value={readablePath} />
              <DetailRow label="所在位置" value={scopeLabel} />
              <DetailRow
                label="类型"
                value={`${fileCategoryLabel} · ${fileTypeLabel}`}
              />
              <DetailRow label="大小" value={formatFileSize(file.size)} />
              <DetailRow
                label="修改时间"
                value={formatDateTime(file.mtime)}
              />
              <DetailRow
                label="本机路径"
                value={file.absolute_path || "未提供"}
              />
            </div>
          </section>

          <section className="rounded-xl border border-border bg-white p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-foreground">
                  当前列表
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground">
                  {workspaceFiles.length} 个文件
                </div>
              </div>
            </div>
            <div className="mt-3 space-y-2">
              {nearbyFiles.length > 0 ? (
                nearbyFiles.map((entry) => (
                  <button
                    key={entry.name}
                    type="button"
                    onClick={() => onOpenWorkspaceFile?.(entry.name)}
                    className="block w-full rounded-lg border border-border bg-white px-3 py-2 text-left transition-colors hover:bg-muted/60"
                  >
                    <div className="truncate text-[12px] font-semibold text-foreground">
                      {entry.name}
                    </div>
                    <div className="mt-1 flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{formatFileSize(entry.size)}</span>
                      <span>{formatDateTime(entry.mtime)}</span>
                    </div>
                  </button>
                ))
              ) : (
                <div className="rounded-lg border border-dashed border-border px-3 py-3 text-[12px] text-muted-foreground">
                  当前列表里没有其他可切换文件。
                </div>
              )}
            </div>
          </section>

          {file.downloadUrl || file.url ? (
            <a
              href={file.downloadUrl || file.url}
              download={fileName}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border bg-white px-3 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted"
            >
              <Download className="h-4 w-4" />
              下载文件
            </a>
          ) : null}
        </div>
      </div>
    </aside>
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-white">
      <div className="border-b border-border bg-white px-4 py-3">
        <div className="flex min-w-0 flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-[220px] flex-1 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/60 text-muted-foreground">
              <FileText className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <h2
                className="truncate text-base font-semibold text-foreground"
                title={fileName}
              >
                {fileName}
              </h2>
              <div
                className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground"
                title={readablePath}
              >
                {scopeLabel} / {readablePath}
              </div>
              <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {fileCategoryLabel}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {fileTypeLabel}
                </Badge>
                <Badge
                  variant="outline"
                  className="hidden rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground 2xl:inline-flex"
                >
                  {extension}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {formatFileSize(file.size)}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {canEditFile ? "可编辑" : "只读"}
                </Badge>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div ref={setToolbarEl} className="flex items-center gap-2" />
            <CanvasActionMenu
              onClose={onClose}
              closeLabel={closeLabel}
              onSplitRight={onSplitRight}
              onSplitDown={onSplitDown}
              onShowInfo={() => setIsDetailsOpen((open) => !open)}
              infoActive={isDetailsOpen}
              customItems={[
                {
                  label: "沉浸预览",
                  icon: <Maximize2 className="h-3.5 w-3.5" />,
                  onClick: openImmersivePreview,
                  active: isImmersiveOpen,
                },
              ]}
            />
          </div>
        </div>
      </div>

      <main className="relative min-h-0 flex-1 overflow-hidden bg-white">
        <FilePreviewPanel
          file={file}
          token={token}
          sessionId={sessionId}
          onReadFileContent={onReadFileContent}
          workspaceId={workspaceId}
          workspaceFiles={workspaceFiles}
          onOpenWorkspaceFile={onOpenWorkspaceFile}
          onOpenPreviewFile={onOpenPreviewFile}
          onRequestImmersivePreview={openImmersivePreview}
          toolbarContainer={toolbarEl}
          onEditFile={onEditFile}
        />

        {isDetailsOpen && !isImmersiveOpen ? detailsPanel : null}
      </main>

      {isImmersiveOpen ? (
        <div
          className="fixed inset-0 z-[200] flex flex-col overflow-hidden bg-white text-foreground"
          data-testid="immersive-file-preview"
          role="dialog"
          aria-modal="true"
          aria-label={`沉浸预览 ${fileName}`}
        >
          <div className="flex min-h-[60px] shrink-0 items-center justify-between gap-4 border-b border-border bg-white px-5 py-3">
            <div className="flex min-w-0 flex-1 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-border bg-muted/60 text-muted-foreground">
                <FileText className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="truncate text-sm font-semibold text-foreground" title={fileName}>
                  {fileName}
                </h2>
                <div
                  className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground"
                  title={readablePath}
                >
                  {scopeLabel} / {readablePath}
                </div>
              </div>
              <div className="hidden items-center gap-1.5 lg:flex">
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {fileTypeLabel}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {formatFileSize(file.size)}
                </Badge>
                <Badge
                  variant="outline"
                  className="rounded-md border-border bg-white px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {canEditFile ? "可编辑" : "只读"}
                </Badge>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <div ref={setImmersiveToolbarEl} className="flex items-center gap-2" />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-8 rounded-lg px-2 text-xs"
                onClick={() => setIsDetailsOpen((open) => !open)}
              >
                文件信息
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-8 rounded-lg px-2 text-xs"
                aria-label="退出沉浸预览"
                onClick={() => {
                  setIsImmersiveOpen(false);
                  setIsDetailsOpen(false);
                }}
              >
                退出
              </Button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            <FilePreviewPanel
              file={file}
              token={token}
              sessionId={sessionId}
              onReadFileContent={onReadFileContent}
              workspaceId={workspaceId}
              workspaceFiles={workspaceFiles}
              onOpenWorkspaceFile={onOpenWorkspaceFile}
              onOpenPreviewFile={onOpenPreviewFile}
              toolbarContainer={immersiveToolbarEl}
              onEditFile={onEditFile}
            />
          </div>
          {isDetailsOpen ? detailsPanel : null}
        </div>
      ) : null}
    </div>
  );
}
