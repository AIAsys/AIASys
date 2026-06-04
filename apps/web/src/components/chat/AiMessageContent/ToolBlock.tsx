/**
 * ToolBlock - 工具调用/输出块
 *
 * 可折叠显示工具调用详情
 */
import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useAiMessageContext } from "./context";
import { ChartAwareMarkdown } from "../ChartAwareMarkdown";

interface ToolBlockProps {
  title: string;
  content: string;
  defaultOpen?: boolean;
}

const normalizeMarkdown = (value?: string) =>
  String(value ?? "")
    .replace(/[\0]/g, "")
    .replace(/\r\n/g, "\n");

export function ToolBlock({
  title,
  content,
  defaultOpen = false,
}: ToolBlockProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const safeContent = useMemo(() => normalizeMarkdown(content), [content]);
  const {
    meta: { token, sessionId, onOpenWorkspaceArtifact },
  } = useAiMessageContext();

  return (
    <div className="my-2 mx-3 group">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
      >
        <div className="flex items-center justify-center w-4 h-4 rounded bg-muted group-hover:bg-accent transition-colors">
          {isOpen ? <ChevronDown size={10} /> : <ChevronRight size={10} />}
        </div>
        <span>{title}</span>
      </button>

      {isOpen && (
        <div className="prose prose-sm mt-1.5 ml-2 max-w-none min-w-0 break-words border-l-2 border-border/50 pl-3 text-[12px] leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
          <ChartAwareMarkdown
            content={safeContent}
            token={token}
            sessionId={sessionId}
            paragraphClassName="my-1"
            onOpenInMainCanvas={onOpenWorkspaceArtifact}
          />
        </div>
      )}
    </div>
  );
}
