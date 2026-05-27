import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { withMermaidSupport } from "./MermaidBlock";

interface MarkdownRendererProps {
  content: string;
  components?: Components;
}

export function MarkdownRenderer({
  content,
  components,
}: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      components={withMermaidSupport(components)}
    >
      {content}
    </ReactMarkdown>
  );
}

export default MarkdownRenderer;
