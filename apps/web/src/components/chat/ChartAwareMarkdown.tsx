import { memo, useMemo, lazy, Suspense, type ReactNode } from "react";
import type { Components } from "react-markdown";

import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { MathMarkdownRenderer } from "./MathMarkdownRenderer";
import { SyntaxCodeBlock } from "@/components/layout/WorkspaceSidebar/preview/SyntaxCodeBlock";

const LazyWorkspaceArtifactRenderer = lazy(() =>
  import("@/components/artifacts/WorkspaceArtifactRenderer").then((m) => ({
    default: m.WorkspaceArtifactRenderer,
  })),
);

interface ChartAwareMarkdownProps {
  content: string;
  token?: string;
  sessionId?: string;
  paragraphClassName?: string;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
}

interface MarkdownSegment {
  type: "markdown" | "artifact";
  content?: string;
  src?: string;
  fileType?: string;
  alt?: string;
}

const ARTIFACT_DIRECTIVE_PATTERN =
  /:::aiasys-file\{([^}]*)\}[ \t]*(?:\r?\n:::[ \t]*)?/g;
const MARKDOWN_IMAGE_PATTERN = /!\[([^\]]*)\]\(([^)]+)\)/g;
const MARKDOWN_LINK_PATTERN = /\[([^\]]+)\]\(([^)]+)\)/g;

function normalizeMarkdown(value?: string): string {
  return String(value ?? "")
    .replace(/[\0]/g, "")
    .replace(/\r\n/g, "\n")
    .replace(
      /<img[^>]+src=["']([^"']+)["'][^>]*alt=["']([^"]*)["'][^>]*\/?>/gi,
      "![$2]($1)",
    )
    .replace(
      /<img[^>]+alt=["']([^"]*)["'][^>]*src=["']([^"']+)["'][^>]*\/?>/gi,
      "![$1]($2)",
    );
}

function parseDirectiveAttributes(raw: string): Record<string, string> {
  const attributes: Record<string, string> = {};
  const attributePattern = /([a-zA-Z0-9_-]+)\s*=\s*["']([^"']*)["']/g;

  for (const match of raw.matchAll(attributePattern)) {
    const [, key, value] = match;
    attributes[key] = value;
  }

  return attributes;
}

function isWorkspaceMarkdownReference(rawPath?: string): boolean {
  const normalizedPath = String(rawPath ?? "")
    .trim()
    .replace(/^<|>$/g, "")
    .split(/[?#]/)[0]
    .replace(/\\/g, "/")
    .toLowerCase();

  if (
    !normalizedPath.startsWith("/workspace/") &&
    !normalizedPath.startsWith("workspace/") &&
    !normalizedPath.startsWith("./workspace/")
  ) {
    return false;
  }

  return (
    normalizedPath.endsWith(".md") ||
    normalizedPath.endsWith(".markdown")
  );
}

function splitMarkdownSegments(content: string): MarkdownSegment[] {
  const segments: MarkdownSegment[] = [];
  const matches: Array<{
    index: number;
    length: number;
    segment: MarkdownSegment;
  }> = [];

  for (const match of content.matchAll(ARTIFACT_DIRECTIVE_PATTERN)) {
    const attributes = parseDirectiveAttributes(match[1] ?? "");
    matches.push({
      index: match.index ?? 0,
      length: match[0].length,
      segment: {
        type: "artifact",
        src: attributes.src,
        fileType: attributes.type,
        alt: attributes.alt,
      },
    });
  }

  for (const match of content.matchAll(MARKDOWN_IMAGE_PATTERN)) {
    matches.push({
      index: match.index ?? 0,
      length: match[0].length,
      segment: {
        type: "artifact",
        src: match[2]?.trim(),
        alt: match[1]?.trim(),
      },
    });
  }

  for (const match of content.matchAll(MARKDOWN_LINK_PATTERN)) {
    const index = match.index ?? 0;
    if (index > 0 && content[index - 1] === "!") {
      continue;
    }

    const src = match[2]?.trim();
    if (!isWorkspaceMarkdownReference(src)) {
      continue;
    }

    matches.push({
      index,
      length: match[0].length,
      segment: {
        type: "artifact",
        src,
        fileType: "markdown",
        alt: match[1]?.trim(),
      },
    });
  }

  matches.sort((left, right) => left.index - right.index);

  let lastIndex = 0;
  for (const match of matches) {
    if (match.index < lastIndex) {
      continue;
    }

    if (match.index > lastIndex) {
      segments.push({
        type: "markdown",
        content: content.slice(lastIndex, match.index),
      });
    }

    segments.push(match.segment);
    lastIndex = match.index + match.length;
  }

  if (lastIndex < content.length) {
    segments.push({
      type: "markdown",
      content: content.slice(lastIndex),
    });
  }

  return segments.filter((segment) => {
    if (segment.type === "artifact") {
      return Boolean(segment.src);
    }
    return Boolean(segment.content?.trim());
  });
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

export const ChartAwareMarkdown = memo(function ChartAwareMarkdown({
  content,
  token,
  sessionId,
  paragraphClassName,
  onOpenInMainCanvas,
}: ChartAwareMarkdownProps) {
  const normalizedContent = useMemo(() => normalizeMarkdown(content), [content]);
  const segments = useMemo(
    () => splitMarkdownSegments(normalizedContent),
    [normalizedContent],
  );
  const markdownComponents = useMemo<Components>(
    () => ({
      p: ({ children }) => (
        <div className={paragraphClassName ?? "mb-4 last:mb-0"}>{children}</div>
      ),
      code: ({
        className,
        children,
        inline,
        ...props
      }: {
        className?: string;
        children?: ReactNode;
        inline?: boolean;
      }) => {
        const match = /language-(\w+)/.exec(className || "");
        const code = String(children || "");
        const hasNewline = code.includes("\n");
        const isInline = inline || (!className && !hasNewline);

        if (isInline) {
          return (
            <code
              className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono"
              {...props}
            >
              {children}
            </code>
          );
        }

        return (
          <SyntaxCodeBlock
            code={code.replace(/\n$/, "")}
            language={match?.[1] || "text"}
          />
        );
      },
    }),
    [paragraphClassName],
  );

  return (
    <>
      {segments.map((segment, index) => {
        if (segment.type === "artifact" && segment.src) {
          return (
            <Suspense
              key={`artifact-${segment.src}-${segment.fileType ?? "auto"}-${index}`}
              fallback={
                <div className="not-prose my-4 rounded-xl border border-border bg-muted/20 px-4 py-3 text-xs text-muted-foreground">
                  正在加载工件预览...
                </div>
              }
            >
              <LazyWorkspaceArtifactRenderer
                artifactPath={segment.src}
                artifactType={segment.fileType}
                sessionId={sessionId}
                token={token}
                variant="chat"
                alt={segment.alt}
                onOpenInMainCanvas={onOpenInMainCanvas}
              />
            </Suspense>
          );
        }

        const markdownContent = segment.content ?? "";
        const Renderer = containsMathSyntax(markdownContent)
          ? MathMarkdownRenderer
          : MarkdownRenderer;

        return (
          <Renderer
            key={`markdown-${index}`}
            content={markdownContent}
            components={markdownComponents}
          />
        );
      })}
    </>
  );
});
