import { useAuthContext } from "@/contexts/AuthContext";
import type { ChatSegment } from "@/pages/WorkspacePage/types";
import { Brain, ChevronDown, Loader2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import { ChartAwareMarkdown } from "./ChartAwareMarkdown";

interface StreamingThoughtBlockProps {
  /**
   * 初始内容（用于非流式场景或恢复历史）
   */
  initialContent?: string;
  /**
   * 是否正在流式输出
   */
  isStreaming?: boolean;
  /**
   * 流式事件订阅器
   * 返回取消订阅的函数
   */
  subscribeToStream?: (
    onChunk: (chunk: string, isFinal: boolean) => void,
  ) => () => void;
  /**
   * 默认是否展开
   */
  defaultOpen?: boolean;
  onOpenInMainCanvas?: (file: PreviewFile) => void;
}

const normalizeMarkdown = (value?: string) =>
  String(value ?? "")
    .replace(/[\0]/g, "")
    .replace(/\r\n/g, "\n");

/**
 * 流式思考过程组件
 *
 * 特点：
 * 1. 自己维护内部 state，不依赖外部频繁更新
 * 2. 通过订阅模式接收流式数据
 * 3. 内部节流渲染，避免过于频繁的 DOM 更新
 */
export function StreamingThoughtBlock({
  initialContent = "",
  isStreaming = false,
  subscribeToStream,
  defaultOpen = true,
  onOpenInMainCanvas,
}: StreamingThoughtBlockProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const [content, setContent] = useState(initialContent);
  const [streaming, setStreaming] = useState(isStreaming);
  const { session } = useAuthContext();
  const token = session?.token;

  // 用于累积内容的 ref，避免闭包问题
  const contentRef = useRef(initialContent);
  const flushTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 清理内容中的特殊标记
  // 只清理 <think> 标签，保留 <code> 标签内容（后者是合法 Markdown/HTML）
  const cleanedContent = useMemo(() => {
    return normalizeMarkdown(content)
      .replace(/<\/?think>/g, "")
      .trim();
  }, [content]);

  // 节流刷新到 state
  const scheduleFlush = useCallback(() => {
    if (flushTimerRef.current) return;
    flushTimerRef.current = setTimeout(() => {
      flushTimerRef.current = null;
      setContent(contentRef.current);
    }, 50);
  }, []);

  // 立即刷新
  const flushNow = useCallback(() => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    setContent(contentRef.current);
  }, []);

  // 订阅流式事件
  useEffect(() => {
    if (!subscribeToStream) return;

    const handleChunk = (chunk: string, isFinal: boolean) => {
      contentRef.current += chunk;

      if (isFinal) {
        setStreaming(false);
        flushNow();
      } else {
        scheduleFlush();
      }
    };

    setStreaming(true);
    const unsubscribe = subscribeToStream(handleChunk);

    return () => {
      unsubscribe();
      if (flushTimerRef.current) {
        clearTimeout(flushTimerRef.current);
      }
    };
  }, [subscribeToStream, scheduleFlush, flushNow]);

  // 同步外部 isStreaming 状态
  useEffect(() => {
    setStreaming(isStreaming);
  }, [isStreaming]);

  // 同步初始内容
  useEffect(() => {
    if (initialContent && !subscribeToStream) {
      contentRef.current = initialContent;
      setContent(initialContent);
    }
  }, [initialContent, subscribeToStream]);

  if (!cleanedContent && !streaming) {
    return null;
  }

  return (
    <div className="mb-3 rounded-lg border border-border/60 bg-muted/20 overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="group flex w-full items-center gap-2.5 px-3.5 py-2.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
      >
        <div
          className={`flex items-center justify-center w-5 h-5 rounded-md flex-shrink-0 transition-colors ${streaming ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground group-hover:bg-muted-foreground/10"}`}
        >
          <Brain size={12} className={streaming ? "animate-pulse" : ""} />
        </div>
        <span className="font-medium">思考过程</span>
        <span className="text-[10px] text-muted-foreground/50 ml-1">
          {isOpen ? "点击折叠" : "点击展开"}
        </span>
        {streaming && (
          <Loader2 size={11} className="animate-spin text-primary ml-auto" />
        )}
        <div
          className={`flex items-center justify-center w-4 h-4 transition-transform ${isOpen ? "rotate-0" : "-rotate-90"} ${streaming ? "" : "ml-auto"}`}
        >
          <ChevronDown size={12} />
        </div>
      </button>

      {isOpen && (
        <div
          className="prose prose-sm max-w-none min-w-0 max-h-80 break-words overflow-y-auto border-t border-border/40 bg-muted/10 px-4 pb-3.5 pt-2 text-[13px] leading-relaxed text-muted-foreground/90 [overflow-wrap:anywhere] [&_p]:my-1.5"
        >
          <ChartAwareMarkdown
            content={cleanedContent || (streaming ? "..." : "")}
            token={token}
            paragraphClassName="my-1"
            onOpenInMainCanvas={onOpenInMainCanvas}
          />
        </div>
      )}
    </div>
  );
}

interface StreamingSegmentsRendererProps {
  /**
   * 当前的 segments 列表
   */
  segments: ChatSegment[];
  /**
   * 是否正在流式输出
   */
  isStreaming: boolean;
}

/**
 * 流式 Segments 渲染器
 *
 * 优化：对于 thought 类型使用 StreamingThoughtBlock 独立渲染
 */
export function StreamingSegmentsRenderer({
  segments,
  isStreaming,
}: StreamingSegmentsRendererProps) {
  // 合并连续的 thought segments
  const mergedSegments = useMemo(() => {
    const result: ChatSegment[] = [];
    let currentThought: ChatSegment | null = null;

    for (const seg of segments) {
      if (seg.type === "thought") {
        if (currentThought) {
          currentThought = {
            type: currentThought.type,
            content: currentThought.content + seg.content,
            toolName: currentThought.toolName,
            toolParams: currentThought.toolParams,
            isComplete: currentThought.isComplete,
          };
        } else {
          currentThought = { ...seg };
        }
      } else {
        if (currentThought) {
          result.push(currentThought);
          currentThought = null;
        }
        result.push(seg);
      }
    }

    if (currentThought) {
      result.push(currentThought);
    }

    return result;
  }, [segments]);

  return (
    <div className="flex flex-col">
      {mergedSegments.map((seg, idx) => {
        const isLast = idx === mergedSegments.length - 1;

        if (seg.type === "thought") {
          return (
            <StreamingThoughtBlock
              key={`thought-${idx}`}
              initialContent={seg.content}
              isStreaming={isStreaming && isLast}
              defaultOpen={true}
            />
          );
        }

        // 其他类型由父组件处理
        return null;
      })}
    </div>
  );
}
