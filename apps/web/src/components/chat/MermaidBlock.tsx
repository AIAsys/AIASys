import React, { useEffect, useMemo, useRef, useState } from "react";
import DOMPurify from "dompurify";
import type { Components } from "react-markdown";

interface MermaidBlockProps {
  code: string;
}

export const MermaidBlock = React.memo(function MermaidBlock({
  code,
}: MermaidBlockProps) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const lastCodeRef = useRef<string | null>(null);

  useEffect(() => {
    if (lastCodeRef.current === code) return;
    lastCodeRef.current = code;

    const render = async () => {
      try {
        const mermaid = await import("mermaid");
        mermaid.default.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "strict",
        });
        const id = `mermaid-${Math.random().toString(36).slice(2, 11)}`;
        const { svg: renderedSvg } = await mermaid.default.render(
          id,
          code.trim(),
        );
        setSvg(DOMPurify.sanitize(renderedSvg));
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Mermaid 渲染失败");
        setSvg("");
      }
    };

    render();
  }, [code]);

  if (error) {
    return (
      <div className="my-2 rounded-md border border-red-200 bg-red-50 p-3">
        <p className="text-xs text-red-600 mb-1">Mermaid 语法错误</p>
        <pre className="text-xs text-red-800 whitespace-pre-wrap">{error}</pre>
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="my-2 flex items-center justify-center rounded-md bg-muted p-4 text-muted-foreground">
        <span className="text-sm">渲染图表中...</span>
      </div>
    );
  }

  return (
    <div
      className="my-2 flex justify-center overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
});

type MarkdownCodeProps = React.HTMLAttributes<HTMLElement> & {
  children?: React.ReactNode;
  className?: string;
  inline?: boolean;
  node?: unknown;
};

function getCodeLanguage(className?: string): string {
  const match = /language-(\w+)/.exec(className || "");
  return match?.[1] || "";
}

function readCodeText(children: React.ReactNode): string {
  return String(children || "").replace(/\n$/, "");
}

export function withMermaidSupport(baseComponents?: Components): Components {
  const BaseCode = baseComponents?.code as
    | React.ComponentType<MarkdownCodeProps>
    | undefined;

  return {
    ...baseComponents,
    code: (props: MarkdownCodeProps) => {
      const { className, children, inline, node: _node, ...htmlProps } = props;
      const language = getCodeLanguage(className);
      const code = readCodeText(children);

      if (language === "mermaid" && !inline) {
        return <MermaidBlock code={code} />;
      }

      if (BaseCode) {
        return <BaseCode {...props} />;
      }

      return (
        <code
          className={className}
          title={htmlProps.title}
          aria-label={htmlProps["aria-label"]}
        >
          {children}
        </code>
      );
    },
  };
}

/**
 * Hook 版本：用 useMemo 缓存 withMermaidSupport 的结果，避免每次渲染都生成
 * 全新的 Components 对象导致 ReactMarkdown 完整重解析（流式输出卡顿主因）。
 *
 * 调用方需保证传入的 `components` 引用稳定（已 useMemo 化或为 undefined）。
 */
export function useMermaidComponents(components?: Components): Components {
  return useMemo(() => withMermaidSupport(components), [components]);
}
