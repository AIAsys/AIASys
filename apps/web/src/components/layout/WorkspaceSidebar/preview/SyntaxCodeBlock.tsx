import React from "react";
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
  return (
    <PrismSyntaxHighlighter
      language={resolveLanguage(fileName, language)}
      style={vscDarkPlus}
      showLineNumbers={showLineNumbers}
      wrapLines={wrapLines}
      customStyle={customStyle}
    >
      {code}
    </PrismSyntaxHighlighter>
  );
};
