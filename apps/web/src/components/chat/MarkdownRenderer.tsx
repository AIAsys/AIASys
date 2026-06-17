import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { useMermaidComponents } from "./MermaidBlock";

interface MarkdownRendererProps {
  content: string;
  components?: Components;
}

export function MarkdownRenderer({
  content,
  components,
}: MarkdownRendererProps) {
  const mermaidComponents = useMermaidComponents(components);
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkBreaks]}
      components={mermaidComponents}
    >
      {content}
    </ReactMarkdown>
  );
}

export default MarkdownRenderer;
