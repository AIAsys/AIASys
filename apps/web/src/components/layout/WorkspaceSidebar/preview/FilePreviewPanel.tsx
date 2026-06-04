/**
 * 文件预览面板
 * 根据文件类型分发到对应的预览渲染器
 */

import { BookOpen, Eye, FileText, History, Loader2, Pencil, Save } from "lucide-react";
import React, {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import { CodeMirrorEditor } from "@/components/editor/CodeMirrorEditor";
import { useWorkspaceMarkdownComponents } from "@/components/markdown/WorkspaceMarkdownComponents";
import { CanvasActionMenu } from "@/components/workspace/CanvasActionMenu";
import {
  getWorkspaceEditorLanguage,
  isGenericallyEditable,
} from "@/utils/workspaceFileEditing";
import type { Components } from "react-markdown";
import type { WorkspaceFile } from "@/types/task";
import type { WorkspaceMarkdownLinkScope } from "@/utils/workspaceMarkdownLinks";
import {
  createGlobalWorkspacePreviewFile,
  createWorkspacePreviewFile,
  resolveGlobalWorkspaceFileUrl,
  resolveWorkspaceFileUrl,
} from "@/utils/workspaceFiles";
import {
  getSupportedPreviewHint,
  shouldReadPreviewTextContent,
  type PreviewFile,
} from "@/utils/filePreviewRegistry";
import { getNotebookRuntimeState } from "@/lib/api/notebooks";
import type { NotebookRuntimeStateResponse } from "@/types/notebook";
import { MarkdownImage } from "../../../chat/MarkdownImage";
import { MermaidBlock } from "../../../chat/MermaidBlock";
import { CsvPreview } from "./CsvPreview";
import { DbFilePreview } from "./DbFilePreview";
import { PdfPreview } from "./PdfPreview";

const NotebookPreview = React.lazy(() =>
  import("./NotebookPreview").then((module) => ({
    default: module.NotebookPreview,
  })),
);

const XlsxPreview = React.lazy(() =>
  import("./XlsxPreview").then((module) => ({
    default: module.XlsxPreview,
  })),
);

const WordPreview = React.lazy(() =>
  import("./WordPreview").then((module) => ({
    default: module.WordPreview,
  })),
);

const PptPreview = React.lazy(() =>
  import("./PptPreview").then((module) => ({
    default: module.PptPreview,
  })),
);

const SyntaxCodeBlock = React.lazy(() =>
  import("./SyntaxCodeBlock").then((module) => ({
    default: module.SyntaxCodeBlock,
  })),
);

const MarkdownRenderer = React.lazy(() =>
  import("../../../chat/MarkdownRenderer").then((module) => ({
    default: module.MarkdownRenderer,
  })),
);

const MathMarkdownRenderer = React.lazy(() =>
  import("../../../chat/MathMarkdownRenderer").then((module) => ({
    default: module.MathMarkdownRenderer,
  })),
);

const CanvasEditor = React.lazy(() =>
  import("@/components/CanvasEditor/CanvasEditor").then((module) => ({
    default: module.CanvasEditor,
  })),
);

const EChartsArtifactRenderer = React.lazy(() =>
  import("@/components/charts/EChartsArtifactRenderer/index").then((module) => ({
    default: module.EChartsArtifactRenderer,
  })),
);

export type { PreviewFile } from "@/utils/filePreviewRegistry";

interface FilePreviewPanelProps {
  file: PreviewFile | null;
  token?: string;
  sessionId?: string | null;
  workspaceFiles?: WorkspaceFile[];
  onReadFileContent?: (filename: string) => Promise<string | null>;
  workspaceId?: string;
  onOpenWorkspaceFile?: (filename: string) => void;
  onOpenPreviewFile?: (file: PreviewFile) => void;
  onRequestImmersivePreview?: () => void;
  toolbarContainer?: HTMLElement | null;
  onEditFile?: (file: PreviewFile) => void;
  onOpenFileHistory?: (fileName: string) => void;
}

function containsMathSyntax(content: string): boolean {
  return (
    content.includes("$$") ||
    content.includes("\\(") ||
    content.includes("\\[") ||
    content.includes("\\begin{") ||
    /(^|[^\\])\$(?!\s)([\s\S]*?)(?<!\s)\$/.test(content)
  );
}

function stripMarkdownFrontMatter(content: string): string {
  const text = content.startsWith("\uFEFF") ? content.slice(1) : content;
  const opening = text.match(/^---[ \t]*\r?\n/);

  if (!opening) {
    return content;
  }

  const bodyStart = opening[0].length;
  const closing = text.slice(bodyStart).match(/\r?\n---[ \t]*(?:\r?\n|$)/);

  if (!closing || closing.index === undefined) {
    return content;
  }

  const bodyAfterFrontMatter = bodyStart + closing.index + closing[0].length;
  return text.slice(bodyAfterFrontMatter);
}

function appendMarkdownReferenceSuffix(url: string, suffix?: string): string {
  if (!suffix) {
    return url;
  }

  if (suffix.startsWith("#")) {
    return `${url}${suffix}`;
  }

  if (suffix.startsWith("?")) {
    const hashIndex = suffix.indexOf("#");
    const search = hashIndex >= 0 ? suffix.slice(1, hashIndex) : suffix.slice(1);
    const hash = hashIndex >= 0 ? suffix.slice(hashIndex) : "";
    const separator = url.includes("?") ? "&" : "?";
    return search ? `${url}${separator}${search}${hash}` : `${url}${hash}`;
  }

  return `${url}${suffix}`;
}

const FilePreviewPanelComponent: React.FC<FilePreviewPanelProps> = ({
  file,
  token,
  sessionId,
  workspaceFiles = [],
  onReadFileContent,
  workspaceId,
  onOpenWorkspaceFile,
  onOpenPreviewFile,
  onRequestImmersivePreview,
  toolbarContainer,
  onEditFile,
  onOpenFileHistory,
}) => {
  const [content, setContent] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editContent, setEditContent] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [sourceViewMode, setSourceViewMode] = useState<"source" | "reading">("reading");
  const [forceTextPreview, setForceTextPreview] = useState(false);
  const [isHtmlPreviewRendering, setIsHtmlPreviewRendering] = useState(false);
  const [notebookRuntimeState, setNotebookRuntimeState] = useState<NotebookRuntimeStateResponse | null>(null);
  const notebookPollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const previewKey = file ? `${file.type}:${file.name}` : "";
  const isGlobalResource = Boolean(file?.meta?._globalResource);
  const previewScope: WorkspaceMarkdownLinkScope = isGlobalResource
    ? "global"
    : "workspace";
  const canEditCurrentFile = Boolean(sessionId);
  const canEditGlobalFile = Boolean(
    isGlobalResource && ((file?.meta?.workspace_id as string) || workspaceId),
  );

  const markdownCodeComponents = useMemo<Components>(
    () => ({
      code: ({
        className,
        children,
        inline,
        ...props
      }: {
        className?: string;
        children?: React.ReactNode;
        inline?: boolean;
      }) => {
        const match = /language-(\w+)/.exec(className || "");
        const language = match?.[1] || "";
        const code = String(children || "");

        if (language === "mermaid") {
          return <MermaidBlock code={code} />;
        }

        const hasNewline = code.includes("\n");
        const isInline = inline || (!className && !hasNewline);

        if (isInline) {
          return (
            <code
              className="rounded bg-muted px-1.5 py-0.5 font-mono text-sm"
              {...props}
            >
              {children}
            </code>
          );
        }

        return (
          <Suspense
            fallback={
              <pre className="my-2 overflow-x-auto rounded-md bg-[#1e1e1e] p-3 text-sm text-primary-foreground">
                <code>{code.replace(/\n$/, "")}</code>
              </pre>
            }
          >
            <SyntaxCodeBlock
              code={code.replace(/\n$/, "")}
              language={language || "text"}
              customStyle={{
                margin: "0.5rem 0",
                borderRadius: "0.375rem",
                fontSize: "0.875rem",
              }}
            />
          </Suspense>
        );
      },
    }),
    [],
  );

  const resolveMarkdownImageSrc = useCallback(
    (
      path: string,
      scope: WorkspaceMarkdownLinkScope,
      suffix?: string,
    ): string | null => {
      const previewUrlOptions = {
        disposition: "inline" as const,
        preferDirectBackend: true,
      };

      if (scope === "global") {
        const globalWorkspaceId =
          (file?.meta?.workspace_id as string | undefined) || workspaceId;
        if (!globalWorkspaceId) {
          return null;
        }
        return appendMarkdownReferenceSuffix(
          resolveGlobalWorkspaceFileUrl(
            path,
            globalWorkspaceId,
            token,
            previewUrlOptions,
          ),
          suffix,
        );
      }

      if (!sessionId) {
        return null;
      }
      return appendMarkdownReferenceSuffix(
        resolveWorkspaceFileUrl(
          `/workspace/${path}`,
          sessionId,
          token,
          previewUrlOptions,
        ),
        suffix,
      );
    },
    [file?.meta, sessionId, token, workspaceId],
  );

  const handleOpenMarkdownPath = useCallback(
    (
      path: string,
      scope: WorkspaceMarkdownLinkScope,
      suffix?: string,
    ) => {
      const meta = suffix ? { subpath: suffix } : undefined;
      if (scope === "global") {
        const globalWorkspaceId =
          (file?.meta?.workspace_id as string | undefined) || workspaceId;
        if (!globalWorkspaceId) {
          return;
        }
        onOpenPreviewFile?.(
          createGlobalWorkspacePreviewFile(
            { name: path, meta },
            globalWorkspaceId,
            token,
          ),
        );
        return;
      }

      const previewFile = createWorkspacePreviewFile(
        { name: path, meta },
        sessionId,
        token,
      );
      if (onOpenPreviewFile) {
        onOpenPreviewFile(previewFile);
        return;
      }
      onOpenWorkspaceFile?.(path);
    },
    [
      file?.meta,
      onOpenPreviewFile,
      onOpenWorkspaceFile,
      sessionId,
      token,
      workspaceId,
    ],
  );

  const markdownComponents = useWorkspaceMarkdownComponents({
    currentFileName: file?.name,
    currentScope: previewScope,
    onOpenWorkspacePath: handleOpenMarkdownPath,
    resolveWorkspaceImageSrc: resolveMarkdownImageSrc,
    baseComponents: markdownCodeComponents,
  });

  // 切换文件时重置强制文本预览状态
  useEffect(() => {
    setForceTextPreview(false);
  }, [file?.name]);

  // notebook 预览时轮询 runtime state
  useEffect(() => {
    if (file?.type !== "notebook" || !sessionId) {
      setNotebookRuntimeState(null);
      if (notebookPollRef.current) {
        clearInterval(notebookPollRef.current);
        notebookPollRef.current = null;
      }
      return;
    }

    const poll = async () => {
      try {
        const state = await getNotebookRuntimeState(sessionId, file.name);
        setNotebookRuntimeState(state);
      } catch (err) {
        // 静默失败，不打扰用户预览
        console.error("获取 notebook runtime state 失败", err);
      }
    };

    poll();
    notebookPollRef.current = setInterval(poll, 10000);

    return () => {
      if (notebookPollRef.current) {
        clearInterval(notebookPollRef.current);
        notebookPollRef.current = null;
      }
    };
  }, [file?.type, file?.name, sessionId]);

  // 加载文本内容
  useEffect(() => {
    if (
      !file ||
      (!shouldReadPreviewTextContent(file.type) && !(file.type === "unknown" && forceTextPreview))
    ) {
      setContent(null);
      setError(null);
      setIsLoading(false);
      setIsHtmlPreviewRendering(false);
      return;
    }

    if (!isGlobalResource && !onReadFileContent) {
      setContent(null);
      setError(null);
      setIsLoading(false);
      setIsHtmlPreviewRendering(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setError(null);
    setIsHtmlPreviewRendering(false);

    const loadContent = async () => {
      try {
        let data: string | null = null;

        if (isGlobalResource) {
          const wsId = (file.meta?.workspace_id as string) || workspaceId;
          const assetPath = file.meta?.relative_path as string;
          if (wsId && assetPath) {
            const res = await apiRequest<{ content: string }>(
              API_ENDPOINTS.GLOBAL_WORKSPACE_CONTENT(wsId, assetPath),
            );
            data = res.content;
          }
        } else if (onReadFileContent) {
          data = await onReadFileContent(file.name);
        }

        if (cancelled) return;

        if (data !== null) {
          setIsHtmlPreviewRendering(file.type === "html");
          setContent(data);
          setEditContent(data);
          setHasUnsavedChanges(false);
          setSourceViewMode("reading");
          setError(null);
        } else {
          setContent(null);
          setEditContent(null);
          setHasUnsavedChanges(false);
          setSourceViewMode("reading");
          setIsHtmlPreviewRendering(false);
          setError("无法读取文件内容");
        }
      } catch (err) {
        if (cancelled) return;
        console.error(err);
        setContent(null);
        setIsHtmlPreviewRendering(false);
        setError("加载失败");
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    loadContent();

    return () => {
      cancelled = true;
    };
  }, [previewKey, file, isGlobalResource, onReadFileContent, forceTextPreview, workspaceId]);

  const persistFileContent = useCallback(async (nextContent: string) => {
    if (!file?.name) return;
    setIsSaving(true);
    try {
      let url: string;
      if (isGlobalResource) {
        const globalWorkspaceId =
          (file.meta?.workspace_id as string | undefined) || workspaceId;
        if (!globalWorkspaceId) return;
        const assetPath = (file.meta?.relative_path as string) || file.name;
        url = API_ENDPOINTS.GLOBAL_WORKSPACE_CONTENT_SAVE(
          globalWorkspaceId,
          assetPath,
        );
      } else {
        const currentWorkspaceId =
          (file.meta?.workspace_id as string | undefined) || workspaceId;
        if (!currentWorkspaceId) return;
        url = API_ENDPOINTS.WORKSPACE_FILE_CONTENT(
          currentWorkspaceId,
          file.name,
        );
      }
      await apiRequest<unknown>(url, {
        method: "PUT",
        body: { content: nextContent },
      });
      setContent(nextContent);
      setEditContent(nextContent);
      setHasUnsavedChanges(false);
    } catch (err) {
      const message = err instanceof Error ? err.message : "保存文件失败";
      setError(message);
      throw err;
    } finally {
      setIsSaving(false);
    }
  }, [isGlobalResource, file?.name, file?.meta, workspaceId]);

  /** 保存文件内容 */
  const handleSave = useCallback(async () => {
    if (!file?.name || editContent === null) return;
    await persistFileContent(editContent);
  }, [file?.name, editContent, persistFileContent]);

  // 空状态
  if (!file) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground/40 bg-muted/10">
        <div className="p-4 bg-muted/20 rounded-full mb-3">
          <Eye className="w-8 h-8 stroke-[1.5]" />
        </div>
        <p className="text-sm font-medium text-foreground/60">选择文件以预览</p>
        <p className="text-xs text-muted-foreground mt-1 font-mono">
          {getSupportedPreviewHint()}
        </p>
      </div>
    );
  }

  // 根据类型渲染
  const effectiveType = forceTextPreview ? "code" : file.type;
  switch (effectiveType) {
    case "image":
      return (
        <div className="h-full relative group flex items-center justify-center p-4 bg-muted">
          <MarkdownImage
            src={file.url}
            alt={file.name}
            token={token}
            className="max-w-full max-h-full w-auto h-auto shadow-none border-none object-contain"
            containerClassName="w-full h-full flex items-center justify-center my-0"
          />
        </div>
      );

    case "database":
      return (
        <div className="h-full overflow-hidden">
          <DbFilePreview
            fileName={file.name}
            sessionId={sessionId}
            scope={isGlobalResource ? "global" : "workspace"}
          />
        </div>
      );

    case "csv":
      return (
        <CsvPreview
          url={file.url}
          fileName={file.name}
          sessionId={sessionId}
          workspaceId={workspaceId}
          scope={
            isGlobalResource
              ? "global"
              : workspaceId
                ? "workspace"
                : sessionId
                  ? "session"
                  : "url"
          }
          assetPath={(file.meta?.relative_path as string | undefined) || file.name}
        />
      );

    case "xlsx":
      return (
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">加载 Excel 预览中...</span>
            </div>
          }
        >
          <XlsxPreview
            url={file.url}
            fileName={file.name}
            workspaceId={(file.meta?.workspace_id as string | undefined) || workspaceId}
            assetPath={(file.meta?.relative_path as string | undefined) || file.name}
          />
        </Suspense>
      );

    case "word":
      return (
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">加载 Word 预览中...</span>
            </div>
          }
        >
          <WordPreview
            url={file.url}
            downloadUrl={file.downloadUrl}
            fileName={file.name}
          />
        </Suspense>
      );

    case "presentation":
      return (
        <Suspense
          fallback={
            <div className="flex items-center justify-center h-full text-muted-foreground">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              <span className="text-sm">加载 PPT 预览中...</span>
            </div>
          }
        >
          <PptPreview
            url={file.url}
            downloadUrl={file.downloadUrl}
            fileName={file.name}
          />
        </Suspense>
      );

    case "pdf":
      return (
        <PdfPreview
          url={file.url}
          downloadUrl={file.downloadUrl}
          fileName={file.name}
        />
      );

    case "markdown": {
      const markdownPreviewContent = stripMarkdownFrontMatter(content || "");
      const Renderer = containsMathSyntax(markdownPreviewContent)
        ? MathMarkdownRenderer
        : MarkdownRenderer;

      const canEditMarkdown =
        isGenericallyEditable(file.name) &&
        (isGlobalResource ? canEditGlobalFile : canEditCurrentFile);

      const markdownToolbarCore = canEditMarkdown ? (
        <>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                hasUnsavedChanges ? "bg-warning" : "bg-success"
              }`}
            />
            <span className="text-[11px] text-muted-foreground">
              {hasUnsavedChanges ? "未保存" : "已保存"}
            </span>
          </div>
          <button
            onClick={() => {
              const nextMode = sourceViewMode === "source" ? "reading" : "source";
              setSourceViewMode(nextMode);
              setIsHtmlPreviewRendering(
                nextMode === "reading" && content !== null,
              );
            }}
            className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] border border-border bg-white hover:bg-muted/50 rounded text-foreground transition-colors"
          >
            {sourceViewMode === "source" ? (
              <>
                <BookOpen className="w-3 h-3" />
                阅读
              </>
            ) : (
              <>
                <Pencil className="w-3 h-3" />
                编辑
              </>
            )}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !hasUnsavedChanges}
            className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] bg-primary hover:bg-primary/90 disabled:bg-muted disabled:opacity-50 disabled:cursor-not-allowed rounded text-primary-foreground transition-colors"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                保存中
              </>
            ) : (
              <>
                <Save className="w-3 h-3" />
                保存
              </>
            )}
          </button>
          {onOpenFileHistory ? (
            <button
              onClick={() => onOpenFileHistory(file.name)}
              className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] border border-border bg-white hover:bg-muted/50 rounded text-foreground transition-colors"
              title="文件历史"
            >
              <History className="w-3 h-3" />
              历史
            </button>
          ) : null}
        </>
      ) : null;

      const markdownToolbar = canEditMarkdown ? (
        <>
          {markdownToolbarCore}
          <CanvasActionMenu
            onClose={() => {}}
            closeLabel="关闭预览"
          />
        </>
      ) : null;

      return (
        <div className="flex flex-col h-full bg-white overflow-hidden">
          {canEditMarkdown && !toolbarContainer && (
            <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-border shrink-0">
              {markdownToolbar}
            </div>
          )}
          {canEditMarkdown && toolbarContainer && createPortal(
            <div className="flex items-center gap-2">{markdownToolbarCore}</div>,
            toolbarContainer
          )}
          <div className="flex-1 overflow-hidden relative">
            {isLoading ? (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                <span className="text-sm">加载 Markdown 文档中...</span>
              </div>
            ) : error ? (
              <div className="absolute inset-0 flex items-center justify-center text-error">
                {error}
              </div>
            ) : canEditMarkdown && sourceViewMode === "source" ? (
              <CodeMirrorEditor
                value={editContent ?? content ?? ""}
                onChange={(value) => {
                  setEditContent(value);
                  setHasUnsavedChanges(value !== (content ?? ""));
                }}
                language="markdown"
                theme="light"
                className="h-full"
                ariaLabel={`编辑 ${file.name}`}
              />
            ) : (
              <Suspense
                fallback={
                  <pre className="m-0 whitespace-pre-wrap px-6 py-5 text-sm leading-6 text-foreground">
                    {markdownPreviewContent}
                  </pre>
                }
              >
                <div className="h-full overflow-y-auto prose prose-sm max-w-none break-words px-6 py-5 text-foreground [overflow-wrap:anywhere]">
                  <Renderer
                    content={markdownPreviewContent}
                    components={markdownComponents}
                  />
                </div>
              </Suspense>
            )}
          </div>
        </div>
      );
    }

    case "html": {
      const canEditHtml =
        isGenericallyEditable(file.name) &&
        (isGlobalResource ? canEditGlobalFile : canEditCurrentFile);

      const htmlToolbarCore = canEditHtml ? (
        <>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                hasUnsavedChanges ? "bg-warning" : "bg-success"
              }`}
            />
            <span className="text-[11px] text-muted-foreground">
              {hasUnsavedChanges ? "未保存" : "已保存"}
            </span>
          </div>
          <button
            onClick={() =>
              setSourceViewMode((prev) =>
                prev === "source" ? "reading" : "source"
              )
            }
            className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] border border-border bg-white hover:bg-muted/50 rounded text-foreground transition-colors"
          >
            {sourceViewMode === "source" ? (
              <>
                <Eye className="w-3 h-3" />
                阅读
              </>
            ) : (
              <>
                <Pencil className="w-3 h-3" />
                编辑
              </>
            )}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !hasUnsavedChanges}
            className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] bg-primary hover:bg-primary/90 disabled:bg-muted disabled:opacity-50 disabled:cursor-not-allowed rounded text-primary-foreground transition-colors"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                保存中
              </>
            ) : (
              <>
                <Save className="w-3 h-3" />
                保存
              </>
            )}
          </button>
          {onOpenFileHistory ? (
            <button
              onClick={() => onOpenFileHistory(file.name)}
              className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] border border-border bg-white hover:bg-muted/50 rounded text-foreground transition-colors"
              title="文件历史"
            >
              <History className="w-3 h-3" />
              历史
            </button>
          ) : null}
        </>
      ) : null;

      const htmlToolbar = canEditHtml ? (
        <>
          {htmlToolbarCore}
          <CanvasActionMenu
            onClose={() => {}}
            closeLabel="关闭预览"
          />
        </>
      ) : null;

      return (
        <div className="flex flex-col h-full bg-white overflow-hidden">
          {canEditHtml && !toolbarContainer && (
            <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-border shrink-0">
              {htmlToolbar}
            </div>
          )}
          {canEditHtml && toolbarContainer && createPortal(
            <div className="flex items-center gap-2">{htmlToolbarCore}</div>,
            toolbarContainer
          )}
          <div className="flex-1 overflow-hidden relative">
            {isLoading ? (
              <div className="absolute inset-0 flex items-center justify-center text-muted-foreground">
                <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                <span className="text-sm">加载 HTML 文档中...</span>
              </div>
            ) : error ? (
              <div className="absolute inset-0 flex items-center justify-center text-error">
                {error}
              </div>
            ) : canEditHtml && sourceViewMode === "source" ? (
              <CodeMirrorEditor
                value={editContent ?? content ?? ""}
                onChange={(value) => {
                  setEditContent(value);
                  setHasUnsavedChanges(value !== (content ?? ""));
                }}
                language="html"
                theme="light"
                className="h-full"
                ariaLabel={`编辑 ${file.name}`}
              />
            ) : (
              <>
                <iframe
                  srcDoc={content || ""}
                  className="w-full h-full border-0"
                  sandbox="allow-scripts"
                  title={file.name}
                  data-testid="html-preview-frame"
                  aria-busy={isHtmlPreviewRendering}
                  onLoad={() => setIsHtmlPreviewRendering(false)}
                />
                {isHtmlPreviewRendering ? (
                  <div
                    className="absolute inset-0 z-10 flex items-center justify-center bg-white/85 text-muted-foreground backdrop-blur-[1px]"
                    data-testid="html-preview-rendering"
                    role="status"
                    aria-live="polite"
                  >
                    <div className="flex items-center rounded-xl border border-border bg-white px-4 py-3 shadow-sm">
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                      <span className="text-sm">正在渲染 HTML 预览...</span>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>
        </div>
      );
    }

    case "notebook": {
      const notebookEditButton = (
        <button
          onClick={() => onEditFile?.(file)}
          className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] border border-border bg-white hover:bg-muted/50 rounded text-foreground transition-colors"
        >
          <Pencil className="w-3 h-3" />
          编辑
        </button>
      );
      return (
        <div className="flex flex-col h-full overflow-hidden">
          {Boolean(onEditFile) && !toolbarContainer && (
            <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-border shrink-0">
              <div className="flex items-center gap-2">
                {notebookEditButton}
              </div>
              <CanvasActionMenu onClose={() => {}} closeLabel="关闭预览" />
            </div>
          )}
          {Boolean(onEditFile) && toolbarContainer && createPortal(
            notebookEditButton,
            toolbarContainer,
          )}
          {isLoading ? (
            <div className="flex-1 flex items-center justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex-1 flex items-center justify-center text-error">
              {error}
            </div>
          ) : content ? (
            <Suspense
              fallback={
                <div className="flex-1 flex items-center justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
                </div>
              }
            >
              <NotebookPreview content={content} fileName={file.name} runtimeState={notebookRuntimeState} />
            </Suspense>
          ) : null}
        </div>
      );
    }

    case "chart":
      return (
        <div className="h-full overflow-hidden">
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              <span className="text-sm">加载图表预览中...</span>
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center text-error">
              {error}
            </div>
          ) : content ? (
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center text-muted-foreground">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  <span className="text-sm">正在加载图表渲染器...</span>
                </div>
              }
            >
              <EChartsArtifactRenderer
                artifactContent={content}
                artifactPath={`/workspace/${file.name}`}
                token={token}
                variant="workspace"
              />
            </Suspense>
          ) : null}
        </div>
      );

    case "canvas":
      return (
        <div className="h-full overflow-hidden">
          {isLoading ? (
            <div className="flex h-full items-center justify-center text-muted-foreground">
              <Loader2 className="mr-2 h-5 w-5 animate-spin" />
              <span className="text-sm">加载画布中...</span>
            </div>
          ) : error ? (
            <div className="flex h-full items-center justify-center text-error">{error}</div>
          ) : (
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center text-muted-foreground">
                  <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                  <span className="text-sm">初始化画布编辑器...</span>
                </div>
              }
            >
              <CanvasEditor
                initialContent={content || undefined}
                workspaceId={workspaceId}
                filePath={file.name}
                sessionId={sessionId}
                token={token}
                workspaceFiles={workspaceFiles}
                onOpenWorkspaceFile={onOpenWorkspaceFile}
                onOpenPreviewFile={onOpenPreviewFile}
                onRequestImmersivePreview={onRequestImmersivePreview}
                onSave={setContent}
                onPersistContent={isGlobalResource ? persistFileContent : undefined}
              />
            </Suspense>
          )}
        </div>
      );

    case "video":
      return (
        <div className="h-full flex items-center justify-center bg-black p-4">
          <video
            controls
            src={file.url}
            className="max-w-full max-h-full"
            controlsList="nodownload"
          >
            您的浏览器不支持视频播放
          </video>
        </div>
      );

    case "audio":
      return (
        <div className="h-full flex flex-col items-center justify-center bg-white p-6">
          <div className="w-full max-w-md">
            <h3 className="text-sm font-medium text-foreground mb-4 text-center break-all">
              {file.name}
            </h3>
            <audio
              controls
              src={file.url}
              className="w-full"
              controlsList="nodownload"
            >
              您的浏览器不支持音频播放
            </audio>
          </div>
        </div>
      );

    case "code": {
      const canEdit =
        isGenericallyEditable(file.name) &&
        (isGlobalResource ? canEditGlobalFile : canEditCurrentFile);
      const isEditingCode = canEdit && sourceViewMode === "source";

      const codeToolbarCore = canEdit ? (
        <>
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                hasUnsavedChanges ? "bg-warning" : "bg-success"
              }`}
            />
            <span className="text-[11px] text-muted-foreground">
              {hasUnsavedChanges ? "未保存" : "已保存"}
            </span>
          </div>
          <button
            onClick={() =>
              setSourceViewMode((prev) =>
                prev === "source" ? "reading" : "source"
              )
            }
            className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] border border-border bg-white hover:bg-muted/50 rounded text-foreground transition-colors"
          >
            {sourceViewMode === "source" ? (
              <>
                <BookOpen className="w-3 h-3" />
                阅读
              </>
            ) : (
              <>
                <Pencil className="w-3 h-3" />
                编辑
              </>
            )}
          </button>
          <button
            onClick={handleSave}
            disabled={isSaving || !hasUnsavedChanges}
            className="flex items-center gap-1 px-2.5 py-0.5 text-[11px] bg-primary hover:bg-primary/90 disabled:bg-muted disabled:opacity-50 disabled:cursor-not-allowed rounded text-primary-foreground transition-colors"
          >
            {isSaving ? (
              <>
                <Loader2 className="w-3 h-3 animate-spin" />
                保存中
              </>
            ) : (
              <>
                <Save className="w-3 h-3" />
                保存
              </>
            )}
          </button>
        </>
      ) : null;

      const codeToolbar = canEdit ? (
        <>
          {codeToolbarCore}
          <CanvasActionMenu
            onClose={() => {}}
            closeLabel="关闭预览"
          />
        </>
      ) : null;

      return (
        <div className="flex flex-col h-full bg-white text-foreground overflow-hidden">
          {canEdit && !toolbarContainer && (
            <div className="flex items-center justify-between px-3 py-1.5 bg-white border-b border-border shrink-0">
              {codeToolbar}
            </div>
          )}
          {canEdit && toolbarContainer && createPortal(
            <div className="flex items-center gap-2">{codeToolbarCore}</div>,
            toolbarContainer
          )}
          <div className="flex-1 overflow-hidden relative">
            {isLoading ? (
              <div className="absolute inset-0 flex items-center justify-center">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : error ? (
              <div className="absolute inset-0 flex flex-col items-center justify-center text-muted-foreground">
                <span className="text-sm">{error}</span>
              </div>
            ) : (
              <CodeMirrorEditor
                value={editContent ?? content ?? ""}
                onChange={
                  isEditingCode
                    ? (value) => {
                        setEditContent(value);
                        setHasUnsavedChanges(value !== (content ?? ""));
                      }
                    : undefined
                }
                language={getWorkspaceEditorLanguage(file.name)}
                readOnly={!isEditingCode}
                theme="light"
                className="h-full"
                ariaLabel={`${isEditingCode ? "编辑" : "只读预览"} ${file.name}`}
              />
            )}
          </div>
        </div>
      );
    }

    default:
      return (
        <div className="flex h-full flex-col bg-white">
          <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
            <div className="w-16 h-16 bg-muted rounded-xl flex items-center justify-center mb-4 shadow-sm">
              <FileText className="w-8 h-8 text-muted-foreground/50" />
            </div>
            <h3 className="text-sm font-medium text-foreground mb-1 break-all max-w-full">
              {file.name}
            </h3>
            <p className="text-xs text-muted-foreground mb-4">
              此文件格式暂不支持在线预览
            </p>
            <button
              type="button"
              onClick={() => setForceTextPreview(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium border border-border bg-white hover:bg-muted/50 rounded-md transition-colors text-foreground"
            >
              <FileText className="w-3.5 h-3.5" />
              以纯文本打开
            </button>
          </div>
        </div>
      );
  }
};

function arePreviewPropsEqual(
  prevProps: FilePreviewPanelProps,
  nextProps: FilePreviewPanelProps,
) {
  return (
    prevProps.file?.name === nextProps.file?.name &&
    prevProps.file?.type === nextProps.file?.type &&
    prevProps.file?.url === nextProps.file?.url &&
    prevProps.token === nextProps.token &&
    prevProps.sessionId === nextProps.sessionId &&
    prevProps.workspaceFiles === nextProps.workspaceFiles &&
    prevProps.onReadFileContent === nextProps.onReadFileContent &&
    prevProps.workspaceId === nextProps.workspaceId &&
    prevProps.onOpenWorkspaceFile === nextProps.onOpenWorkspaceFile &&
    prevProps.onOpenPreviewFile === nextProps.onOpenPreviewFile &&
    prevProps.onRequestImmersivePreview === nextProps.onRequestImmersivePreview &&
    prevProps.toolbarContainer === nextProps.toolbarContainer &&
    prevProps.onEditFile === nextProps.onEditFile &&
    prevProps.onOpenFileHistory === nextProps.onOpenFileHistory
  );
}

export const FilePreviewPanel = React.memo(
  FilePreviewPanelComponent,
  arePreviewPropsEqual,
);
