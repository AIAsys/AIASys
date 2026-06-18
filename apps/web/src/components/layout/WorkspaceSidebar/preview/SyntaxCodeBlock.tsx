import React, { useCallback, useState } from "react";
import PrismSyntaxHighlighter from "react-syntax-highlighter/dist/esm/prism-light";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import jsx from "react-syntax-highlighter/dist/esm/languages/prism/jsx";
import markdown from "react-syntax-highlighter/dist/esm/languages/prism/markdown";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import { Copy, Check, X } from "lucide-react";
import { writeTextToClipboard } from "@/utils/clipboardText";
import { useSafeTimeout } from "@/hooks/useSafeTimeout";

PrismSyntaxHighlighter.registerLanguage("bash", bash);
PrismSyntaxHighlighter.registerLanguage("css", css);
PrismSyntaxHighlighter.registerLanguage("javascript", javascript);
PrismSyntaxHighlighter.registerLanguage("json", json);
PrismSyntaxHighlighter.registerLanguage("jsx", jsx);
PrismSyntaxHighlighter.registerLanguage("markdown", markdown);
PrismSyntaxHighlighter.registerLanguage("markup", markup);
PrismSyntaxHighlighter.registerLanguage("python", python);
PrismSyntaxHighlighter.registerLanguage("sql", sql);
PrismSyntaxHighlighter.registerLanguage("tsx", tsx);
PrismSyntaxHighlighter.registerLanguage("typescript", typescript);
PrismSyntaxHighlighter.registerLanguage("yaml", yaml);

const EXT_TO_LANGUAGE: Record<string, string> = {
  bat: "bash",
  css: "css",
  htm: "markup",
  html: "markup",
  js: "javascript",
  json: "json",
  jsx: "jsx",
  md: "markdown",
  py: "python",
  sh: "bash",
  sql: "sql",
  ts: "typescript",
  tsx: "tsx",
  xml: "markup",
  yml: "yaml",
  yaml: "yaml",
};

const LANGUAGE_LABEL: Record<string, string> = {
  bash: "Bash",
  css: "CSS",
  javascript: "JavaScript",
  json: "JSON",
  jsx: "JSX",
  markdown: "Markdown",
  markup: "HTML",
  python: "Python",
  sql: "SQL",
  tsx: "TSX",
  typescript: "TypeScript",
  yaml: "YAML",
  text: "Plain Text",
};

interface SyntaxCodeBlockProps {
  code: string;
  fileName?: string;
  language?: string;
  showLineNumbers?: boolean;
  wrapLines?: boolean;
  customStyle?: React.CSSProperties;
}

function resolveLanguage(
  fileName?: string,
  explicitLanguage?: string,
): string | undefined {
  if (explicitLanguage) {
    return explicitLanguage;
  }
  if (!fileName) {
    return undefined;
  }
  const ext = fileName.split(".").pop()?.toLowerCase();
  return ext ? EXT_TO_LANGUAGE[ext] : undefined;
}

export const SyntaxCodeBlock: React.FC<SyntaxCodeBlockProps> = ({
  code,
  fileName,
  language,
  showLineNumbers = false,
  wrapLines = true,
  customStyle,
}) => {
  const resolvedLang = resolveLanguage(fileName, language) || "text";
  const displayLang = LANGUAGE_LABEL[resolvedLang] || resolvedLang;
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const setSafeTimeout = useSafeTimeout();

  const handleCopy = useCallback(async () => {
    const result = await writeTextToClipboard(code);
    if (result.ok) {
      setCopied(true);
      setCopyError(false);
      setSafeTimeout(() => setCopied(false), 2000);
    } else {
      // 复制失败：短暂显示错误状态，提示用户手动复制
      setCopyError(true);
      setCopied(false);
      setSafeTimeout(() => setCopyError(false), 2000);
    }
  }, [code, setSafeTimeout]);

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-border/40 shadow-sm">
      {/* 标题栏：macOS 风格 */}
      <div className="flex items-center gap-3 bg-[#2d2d2d] px-4 py-2">
        {/* 三个彩色圆点 */}
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full bg-[#ff5f56] ring-1 ring-black/10" />
          <span className="h-3 w-3 rounded-full bg-[#ffbd2e] ring-1 ring-black/10" />
          <span className="h-3 w-3 rounded-full bg-[#27c93f] ring-1 ring-black/10" />
        </div>

        {/* 语言标签 */}
        <span className="ml-1 text-[11px] font-medium tracking-wide text-white/50">
          {displayLang}
        </span>

        {/* 右侧占位 */}
        <div className="flex-1" />

        {/* 复制按钮 */}
        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-[11px] text-white/40 transition-colors hover:bg-white/10 hover:text-white/70"
          title="复制代码"
        >
          {copied ? (
            <>
              <Check size={12} />
              <span>已复制</span>
            </>
          ) : copyError ? (
            <>
              <X size={12} />
              <span>复制失败</span>
            </>
          ) : (
            <>
              <Copy size={12} />
              <span>复制</span>
            </>
          )}
        </button>
      </div>

      {/* 代码区域 */}
      <div className="bg-[#1e1e1e]">
        <PrismSyntaxHighlighter
          language={resolvedLang}
          style={vscDarkPlus}
          showLineNumbers={showLineNumbers}
          wrapLines={wrapLines}
          customStyle={{
            margin: 0,
            padding: "1rem 1.25rem",
            fontSize: "13px",
            lineHeight: "1.7",
            background: "transparent",
            ...customStyle,
          }}
        >
          {code}
        </PrismSyntaxHighlighter>
      </div>
    </div>
  );
};
