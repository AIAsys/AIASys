import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import { useMermaidComponents } from "./MermaidBlock";

import "katex/dist/katex.min.css";

interface MathMarkdownRendererProps {
  content: string;
  components?: Components;
}

export function MathMarkdownRenderer({
  content,
  components,
}: MathMarkdownRendererProps) {
  const mermaidComponents = useMermaidComponents(components);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath, remarkBreaks]}
      rehypePlugins={[rehypeKatex]}
      components={mermaidComponents}
    >
      {content}
    </ReactMarkdown>
  );
}

export default MathMarkdownRenderer;
