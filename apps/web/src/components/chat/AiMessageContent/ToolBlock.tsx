/**
 * ToolBlock - 工具调用/输出块
 *
 * 可折叠显示工具调用详情。错误模式下展开并显示引导按钮。
 */
import { useState, useMemo } from "react";
import { ChevronDown, ChevronRight, Settings2, RefreshCw } from "lucide-react";
import { useAiMessageContext } from "./context";
import { ChartAwareMarkdown } from "../ChartAwareMarkdown";

interface ToolBlockProps {
  title: string;
  content: string;
  defaultOpen?: boolean;
  isError?: boolean;
}

const normalizeMarkdown = (value?: string) =>
  String(value ?? "")
    .replace(/[\0]/g, "")
    .replace(/\r\n/g, "\n");

/** 检测错误内容是否与运行环境相关，用于决定是否显示引导按钮 */
const ENV_ERROR_PATTERNS = [
  /kernel/i,
  /jupyter/i,
  /python.*环境/i,
  /环境.*未/i,
  /runtime.*not/i,
  /sandbox/i,
  /venv/i,
  /pip install/i,
  /无法创建.*kernel/i,
  /未安装/i,
];

function isEnvironmentError(content: string): boolean {
  return ENV_ERROR_PATTERNS.some((p) => p.test(content));
}

export function ToolBlock({
  title,
  content,
  defaultOpen = false,
  isError = false,
}: ToolBlockProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const safeContent = useMemo(() => normalizeMarkdown(content), [content]);
  const {
    meta: { token, sessionId, onOpenWorkspaceArtifact, onOpenInBrowserTab, onOpenRuntimeTab, onRetryLastSubmit },
  } = useAiMessageContext();

  const showEnvGuide = isError && onOpenRuntimeTab && isEnvironmentError(safeContent);

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
        <div className="mt-1.5 ml-2 min-w-0 break-words border-l-2 border-border/50 pl-3 text-[12px] leading-relaxed text-muted-foreground [overflow-wrap:anywhere]">
          <div className="prose prose-sm max-w-none">
            <ChartAwareMarkdown
              content={safeContent}
              token={token}
              sessionId={sessionId}
              paragraphClassName="my-1"
              onOpenInMainCanvas={onOpenWorkspaceArtifact}
              onOpenInBrowserTab={onOpenInBrowserTab}
            />
          </div>
          {showEnvGuide ? (
            <button
              type="button"
              onClick={onOpenRuntimeTab}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted"
            >
              <Settings2 className="h-3 w-3" />
              配置运行环境
            </button>
          ) : null}
          {isError && onRetryLastSubmit ? (
            <button
              type="button"
              onClick={() => void onRetryLastSubmit()}
              className="mt-2 flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1.5 text-[11px] font-medium text-foreground transition-colors hover:bg-muted"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          ) : null}
        </div>
      )}
    </div>
  );
}
