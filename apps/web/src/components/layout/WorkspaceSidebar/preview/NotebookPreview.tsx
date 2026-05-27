import React, { Suspense, useMemo } from "react";
import DOMPurify from "dompurify";
import { ImageLightbox } from "@/components/ui/image-lightbox";
import type { NotebookRuntimeStateResponse } from "@/types/notebook";

const LazyMarkdownRenderer = React.lazy(() =>
  import("@/components/chat/MarkdownRenderer").then((module) => ({
    default: module.MarkdownRenderer,
  })),
);

const LazyMathMarkdownRenderer = React.lazy(() =>
  import("@/components/chat/MathMarkdownRenderer").then((module) => ({
    default: module.MathMarkdownRenderer,
  })),
);

const LazySyntaxCodeBlock = React.lazy(() =>
  import("./SyntaxCodeBlock").then((module) => ({
    default: module.SyntaxCodeBlock,
  })),
);

interface NotebookCell {
  cell_type: "code" | "markdown" | "raw";
  source: string | string[];
  outputs?: NotebookOutput[];
  execution_count?: number | null;
}

interface NotebookOutput {
  output_type: "stream" | "execute_result" | "display_data" | "error";
  text?: string | string[];
  data?: {
    "text/plain"?: string | string[];
    "image/png"?: string;
    "image/jpeg"?: string;
    "text/html"?: string | string[];
    [key: string]: unknown;
  };
  traceback?: string[];
  name?: string; // for stream
}

interface NotebookData {
  cells: NotebookCell[];
  metadata: Record<string, unknown>;
  nbformat: number;
  nbformat_minor: number;
}

interface NotebookPreviewProps {
  content: string; // Raw JSON string
  fileName: string;
  runtimeState?: NotebookRuntimeStateResponse | null;
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

interface ErrorOutput extends NotebookOutput {
  name: string;
  evalue?: string;
  traceback?: string[];
}

export const NotebookPreview: React.FC<NotebookPreviewProps> = ({
  content,
  fileName,
  runtimeState,
}) => {
  const notebook = useMemo<NotebookData | null>(() => {
    try {
      return JSON.parse(content);
    } catch (e) {
      console.error("Failed to parse notebook JSON", e);
      return null;
    }
  }, [content]);

  if (!notebook) {
    return <div className="p-4 text-error">Invalid Notebook Format</div>;
  }

  const renderSource = (source: string | string[]) => {
    return Array.isArray(source) ? source.join("") : source;
  };

  const sanitizeHtml = (html: string) => {
    return DOMPurify.sanitize(html, {
      ALLOWED_TAGS: [
        "div", "span", "p", "br", "a", "img", "table", "thead", "tbody",
        "tr", "th", "td", "ul", "ol", "li", "b", "strong", "i", "em",
        "u", "s", "del", "code", "pre", "h1", "h2", "h3", "h4", "h5",
        "h6", "blockquote", "hr", "sub", "sup", "svg", "path", "circle",
        "rect", "line", "g",
      ],
      ALLOWED_ATTR: [
        "href", "src", "alt", "title", "class", "width", "height",
        "target", "colspan", "rowspan", "d", "fill", "stroke",
        "viewBox", "xmlns",
      ],
    });
  };

  return (
    <div className="flex flex-col h-full bg-background dark:bg-foreground overflow-y-auto custom-scrollbar">
      <div className="flex items-center px-4 py-2 border-b border-border bg-muted/20">
        <span className="text-xs font-mono text-muted-foreground truncate font-medium">
          {fileName}
        </span>
      </div>
      {runtimeState && (
        <div className="flex items-center justify-between px-4 py-1.5 border-b border-border bg-muted/50">
          <div className="flex items-center gap-2">
            <div
              className={`w-2 h-2 rounded-full ${
                runtimeState.kernel_active
                  ? runtimeState.runtime_busy
                    ? "bg-amber-500 animate-pulse"
                    : "bg-green-500"
                  : "bg-gray-400"
              }`}
            />
            <span className="text-xs text-muted-foreground">
              {runtimeState.kernel_active
                ? runtimeState.runtime_busy
                  ? "运行中"
                  : "空闲"
                : "未启动"}
            </span>
          </div>
          {runtimeState.runtime_summary?.status_label && (
            <span className="text-[11px] text-muted-foreground/70">
              {runtimeState.runtime_summary.status_label}
            </span>
          )}
        </div>
      )}

      <div className="p-8 max-w-4xl mx-auto w-full space-y-6 pb-20">
        {notebook.cells.map((cell, index) => (
          <div key={index} className="group relative">
            {/* Cell Input */}
            <div className="flex gap-2">
              {/* Execution Count */}
              <div className="w-16 flex-shrink-0 text-right pt-2 font-mono text-xs text-muted-foreground/50 select-none">
                {cell.cell_type === "code" &&
                  `[${cell.execution_count || " "}]`}
              </div>

              <div className="flex-1 min-w-0">
                {cell.cell_type === "markdown" ? (
                  <div className="prose dark:prose-invert max-w-none text-sm p-2 bg-transparent">
                    {containsMathSyntax(renderSource(cell.source)) ? (
                      <Suspense
                        fallback={
                          <div className="whitespace-pre-wrap">
                            {renderSource(cell.source)}
                          </div>
                        }
                      >
                        <LazyMathMarkdownRenderer
                          content={renderSource(cell.source)}
                        />
                      </Suspense>
                    ) : (
                      <Suspense
                        fallback={
                          <div className="whitespace-pre-wrap">
                            {renderSource(cell.source)}
                          </div>
                        }
                      >
                        <LazyMarkdownRenderer content={renderSource(cell.source)} />
                      </Suspense>
                    )}
                  </div>
                ) : cell.cell_type === "code" ? (
                  <div className="rounded-md border border-border overflow-hidden bg-[#1e1e1e]">
                    <Suspense
                      fallback={
                        <pre className="overflow-x-auto p-4 text-[13px] text-primary-foreground">
                          {renderSource(cell.source)}
                        </pre>
                      }
                    >
                      <LazySyntaxCodeBlock
                        code={renderSource(cell.source)}
                        language="python"
                        wrapLines={true}
                        customStyle={{
                          margin: 0,
                          padding: "1rem",
                          fontSize: "13px",
                          backgroundColor: "transparent",
                        }}
                      />
                    </Suspense>
                  </div>
                ) : (
                  <pre className="text-xs bg-muted p-2 rounded">
                    {renderSource(cell.source)}
                  </pre>
                )}

                {/* Outputs */}
                {cell.cell_type === "code" &&
                  cell.outputs &&
                  cell.outputs.length > 0 && (
                    <div className="mt-2 space-y-2">
                      {cell.outputs.map((output, outIndex) => (
                        <div key={outIndex} className="text-sm overflow-x-auto">
                          {output.output_type === "stream" && (
                            <pre className="font-mono text-xs whitespace-pre-wrap p-2 text-foreground/80">
                              {renderSource(output.text || "")}
                            </pre>
                          )}

                          {(output.output_type === "execute_result" ||
                            output.output_type === "display_data") &&
                            output.data && (
                              <div>
                                {output.data["image/png"] ? (
                                  <ImageLightbox
                                    src={`data:image/png;base64,${output.data["image/png"].trim()}`}
                                    alt="Output image"
                                    wrapElement="span"
                                    zoomMargin={24}
                                    className="max-w-full h-auto bg-white rounded-md cursor-zoom-in"
                                  />
                                ) : output.data["image/jpeg"] ? (
                                  <ImageLightbox
                                    src={`data:image/jpeg;base64,${output.data["image/jpeg"].trim()}`}
                                    alt="Output image"
                                    wrapElement="span"
                                    zoomMargin={24}
                                    className="max-w-full h-auto bg-white rounded-md cursor-zoom-in"
                                  />
                                ) : output.data["text/html"] ? (
                                  <div
                                    dangerouslySetInnerHTML={{
                                      __html: sanitizeHtml(
                                        renderSource(output.data["text/html"]),
                                      ),
                                    }}
                                  />
                                ) : output.data["text/plain"] ? (
                                  <pre className="font-mono text-xs whitespace-pre-wrap p-2 text-foreground/80">
                                    {renderSource(output.data["text/plain"])}
                                  </pre>
                                ) : null}
                              </div>
                            )}

                          {output.output_type === "error" && (
                            <div className="bg-error/10 text-error dark:text-error p-2 rounded text-xs font-mono whitespace-pre-wrap border border-error/20">
                              <div className="font-bold">
                                {output.name}:{" "}
                                {output.text || (output as ErrorOutput).evalue}
                              </div>
                              {(output as ErrorOutput).traceback && (
                                <div className="mt-1 opacity-80">
                                  {(output as ErrorOutput).traceback!.join(
                                    "\n",
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
