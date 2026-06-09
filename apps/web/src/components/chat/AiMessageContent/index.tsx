/**
 * AiMessageContent - AI 消息内容组件
 *
 * 重构为 Explicit Variants + Context 模式：
 * - 拆分为独立的子组件
 * - 通过 Context 共享状态
 * - 避免 props 过多
 *
 * 设计原则：
 * 1. 三个区域独立：思考区、工具区、回答区
 * 2. 每种类型的内容累积显示，不会相互覆盖
 * 3. 支持流式更新和历史恢复
 */
import { memo, useMemo } from "react";

import type { ChatSegment, WorkerRecord } from "@/pages/WorkspacePage/types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import {
  AiMessageContext,
  type AiMessageActions,
  type AiMessageMeta,
  type AiMessageState,
} from "./context";
import { LoadingPlaceholder } from "./LoadingPlaceholder";
import { StoppedIndicator } from "./StoppedIndicator";
import { WorkerIndicators } from "./WorkerIndicators";
import { ToolBlock } from "./ToolBlock";
import { StreamingThoughtBlock } from "../StreamingThoughtBlock";
import { ChartAwareMarkdown } from "../ChartAwareMarkdown";

// 导出 Context 和子组件
export { AiMessageContext, useAiMessageContext } from "./context";
export { LoadingPlaceholder } from "./LoadingPlaceholder";
export { StoppedIndicator } from "./StoppedIndicator";
export { ToolBlock } from "./ToolBlock";
export { FinalAnswerBlock } from "./FinalAnswerBlock";
export { WorkerIndicators } from "./WorkerIndicators";

export interface AiMessageContentProps {
  /**
   * 最终答案内容（来自后端 message.content）
   */
  content?: string;
  /**
   * 分段内容：思考、工具调用、最终回答
   */
  segments?: ChatSegment[];
  /**
   * 是否正在流式输出
   */
  isStreaming: boolean;
  /**
   * 是否已终止
   */
  isStopped?: boolean;
  /**
   * Worker 状态记录
   */
  workerRecords?: WorkerRecord[];
  /**
   * Worker 点击回调
   */
  onWorkerClick?: (workerName: string) => void;
  /**
   * 查看工具调用详情回调 - 包含触发元素位置用于悬浮窗定位
   */
  onViewToolDetails?: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  /**
   * 关联的任务 ID
   */
  taskId?: string;
  /**
   * 会话 ID（用于加载工作区图片）
   */
  sessionId?: string;
  /**
   * 在主画布打开工作区产物
   */
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
  /**
   * 是否在消息流中内联显示工具执行结果（默认 false，结果通过弹窗查看）
   */
  showToolOutputs?: boolean;
}

// 从 segments 中分离出内容类型
function useSegmentData(segments?: ChatSegment[]) {
  return useMemo(() => {
    const thoughts: ChatSegment[] = [];
    const tools: ChatSegment[] = [];
    const texts: ChatSegment[] = [];
    const thinks: ChatSegment[] = [];
    const monitors: ChatSegment[] = [];
    const turns: ChatSegment[] = [];

    if (segments && segments.length > 0) {
      for (const seg of segments) {
        if (seg.type === "text") {
          texts.push(seg);
        } else if (seg.type === "thought") {
          thoughts.push(seg);
        } else if (seg.type === "think") {
          thinks.push(seg);
        } else if (seg.type === "tool_call" || seg.type === "tool_output") {
          tools.push(seg);
        } else if (seg.type === "monitor") {
          monitors.push(seg);
        } else if (seg.type === "turn") {
          turns.push(seg);
        }
      }
    }

    return { thoughts, tools, texts, thinks, monitors, turns };
  }, [segments]);
}

// Provider 组件
interface AiMessageProviderProps {
  children: React.ReactNode;
  state: AiMessageState;
  actions: AiMessageActions;
  meta: AiMessageMeta;
}

function AiMessageProvider({
  children,
  state,
  actions,
  meta,
}: AiMessageProviderProps) {
  return (
    <AiMessageContext value={{ state, actions, meta }}>
      {children}
    </AiMessageContext>
  );
}

// 主组件
export const AiMessageContent = memo(function AiMessageContent({
  content,
  segments,
  isStreaming,
  isStopped,
  workerRecords,
  onWorkerClick,
  onViewToolDetails,
  sessionId,
  taskId,
  onOpenWorkspaceArtifact,
  showToolOutputs = false,
}: AiMessageContentProps) {
  const {
    thoughts: thoughtSegments,
    tools,
    texts,
    thinks,
    monitors,
    turns,
  } = useSegmentData(segments);
  const workerActivities = workerRecords ?? [];

  // 合并连续的思考内容
  const mergedThoughtContent = useMemo(() => {
    return thoughtSegments.map((t) => t.content).join("");
  }, [thoughtSegments]);

  // 合并回答内容
  const mergedFinalAnswer = useMemo(() => {
    return texts.map((t) => t.content).join("");
  }, [texts]);

  // 判断内容是否为空（考虑 content 字段和 segments）
  const hasContent = content && content.trim().length > 0;
  const isEmpty =
    !hasContent &&
    !mergedThoughtContent &&
    thinks.length === 0 &&
    tools.length === 0 &&
    !mergedFinalAnswer &&
    texts.length === 0 &&
    monitors.length === 0 &&
    turns.length === 0 &&
    (!segments || segments.length === 0);

  // 判断是否正在思考（没有最终回答时）
  const isThinking = isStreaming && !mergedFinalAnswer;

  // 构建 state
  const state: AiMessageState = {
    thoughts: mergedThoughtContent,
    thinks,
    isThinking,
    isStopped: isStopped || false,
    isEmpty,
    isStreaming,
    tools,
    finalAnswer: mergedFinalAnswer,
    workerActivities,
    monitors,
  };

  // 构建 actions
  const actions: AiMessageActions = {
    onWorkerClick,
  };

  // 构建 meta，当前不需要手动传递 token
  const meta: AiMessageMeta = {
    token: undefined,
    sessionId,
    onOpenWorkspaceArtifact,
  };

  // 按顺序渲染 segments
  // 流式过程中保持到达时序，只在历史恢复（非流式）时做防御性排序
  const renderSegments = () => {
    if (!segments || segments.length === 0) {
      return null;
    }

    // 防御性排序：仅在非流式（历史恢复）时按类型排序
    // 流式过程中 segments 已按到达时序排列
    // 每个类型必须有唯一 order，避免 sort 不稳定导致顺序随机
    const SEGMENT_ORDER: Record<string, number> = {
      turn: 0,
      think: 1,
      tool_call: 2,
      tool_output: 3,
      text: 4,
      monitor: 5,
    };
    let sortedSegments: ChatSegment[];
    if (isStreaming) {
      // 流式过程中保持到达时序
      sortedSegments = segments;
    } else {
      // 历史恢复时按类型排序
      sortedSegments = [...segments].sort((a, b) => {
        const orderA = SEGMENT_ORDER[a.type] ?? 99;
        const orderB = SEGMENT_ORDER[b.type] ?? 99;
        return orderA - orderB;
      });
    }

    // 合并连续的同类型 segments
    // 仅合并 text / think，tool_call / tool_output / monitor 保持独立
    const MERGEABLE_TYPES = new Set<string>(["text", "think"]);
    const mergedSegments: ChatSegment[] = [];
    for (const seg of sortedSegments) {
      const lastSeg = mergedSegments[mergedSegments.length - 1];
      if (
        lastSeg &&
        lastSeg.type === seg.type &&
        MERGEABLE_TYPES.has(seg.type)
      ) {
        lastSeg.content += seg.content;
      } else {
        mergedSegments.push({ ...seg });
      }
    }

    // 按顺序渲染合并后的 segments
    return mergedSegments.map((seg, idx) => {
      if (seg.type === "think") {
        return (
          <StreamingThoughtBlock
            key={`seg-think-${idx}`}
            initialContent={seg.content}
            isStreaming={isStreaming && !seg.isComplete}
            defaultOpen={isStreaming}
            onOpenInMainCanvas={onOpenWorkspaceArtifact}
          />
        );
      }

      if (seg.type === "text") {
        // 将 HTML <img> 标签转换为 Markdown 格式，以便统一处理
        const processedContent = seg.content
          .replace(
            /<img[^>]+src=["']([^"']+)["'][^>]*alt=["']([^"']*)["'][^>]*\/?>/gi,
            (_match, src, alt) => `![${alt}](${src})`,
          )
          .replace(
            /<img[^>]+alt=["']([^"']*)["'][^>]*src=["']([^"']+)["'][^>]*\/?>/gi,
            (_match, alt, src) => `![${alt}](${src})`,
          );
        return (
          <div
            key={`seg-text-${idx}`}
            className="prose prose-sm max-w-none min-w-0 break-all"
          >
            <ChartAwareMarkdown
              content={processedContent}
              token={undefined}
              sessionId={sessionId}
              onOpenInMainCanvas={onOpenWorkspaceArtifact}
            />
          </div>
        );
      }

      if (seg.type === "tool_call") {
        return (
          <button
            key={`seg-tool-${idx}`}
            onClick={(e) => {
              const rect = (
                e.currentTarget as HTMLButtonElement
              ).getBoundingClientRect();
              // 优先使用 toolCallId 作为唯一标识符
              onViewToolDetails?.(
                seg.toolCallId || seg.toolName || `tool-${idx}`,
                taskId,
                rect,
              );
            }}
            className="mb-2 group/tool flex items-center gap-3 px-3.5 py-2.5 rounded-lg border border-border bg-muted/50 hover:bg-accent/70 transition-all duration-200 hover:shadow-sm"
          >
            <div className="flex items-center justify-center w-6 h-6 rounded-md bg-primary/10 text-primary flex-shrink-0">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
              </svg>
            </div>
            <div className="flex flex-col items-start gap-0.5 min-w-0">
              <span className="text-xs font-semibold text-foreground truncate max-w-[200px]">
                {seg.toolName}
              </span>
              <span className="text-[10px] text-muted-foreground group-hover/tool:text-foreground/70 transition-colors">
                点击查看详情 →
              </span>
            </div>
          </button>
        );
      }

      if (seg.type === "tool_output") {
        if (!showToolOutputs) return null;
        const hasContent = seg.content && seg.content.trim().length > 0;
        return (
          <ToolBlock
            key={`seg-tool-output-${idx}`}
            title={`${seg.toolName || "工具"} ${seg.isError ? "错误" : "执行结果"}`}
            content={hasContent ? seg.content : "（无输出）"}
            defaultOpen={seg.isError || false}
          />
        );
      }

      if (seg.type === "monitor") {
        const isRunning = seg.monitorStatus === "running";
        const statusColor = seg.isError
          ? "border-red-200 bg-red-50"
          : seg.isComplete
            ? "border-green-200 bg-green-50"
            : "border-amber-200 bg-amber-50";
        const statusText = seg.isError
          ? "失败"
          : seg.isComplete
            ? "完成"
            : "运行中";
        return (
          <div
            key={`seg-monitor-${seg.monitorId || idx}`}
            className={`my-2 mx-3 rounded-lg border ${statusColor} overflow-hidden`}
          >
            <div className="flex items-center gap-2 px-3 py-2 border-b border-black/5">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={isRunning ? "animate-pulse text-amber-600" : seg.isError ? "text-red-600" : "text-green-600"}
              >
                <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
              <span className="text-[11px] font-medium text-foreground/80 truncate">
                Monitor {seg.monitorCommand}
              </span>
              <span className={`text-[10px] ml-auto px-1.5 py-0.5 rounded ${seg.isError ? "bg-red-100 text-red-700" : seg.isComplete ? "bg-green-100 text-green-700" : "bg-amber-100 text-amber-700"}`}>
                {statusText}{seg.monitorExitCode !== null && seg.monitorExitCode !== undefined ? ` (${seg.monitorExitCode})` : ""}
              </span>
            </div>
            {seg.content && (
              <pre className="px-3 py-2 text-[11px] font-mono text-muted-foreground max-h-48 overflow-auto whitespace-pre-wrap break-all">
                {seg.content}
              </pre>
            )}
            {isRunning && (
              <div className="px-3 py-1.5 border-t border-black/5">
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
                  <span className="text-[10px] text-muted-foreground">后台运行中...</span>
                </div>
              </div>
            )}
          </div>
        );
      }

      if (seg.type === "turn") {
        return (
          <div
            key={`seg-turn-${idx}`}
            className="flex w-full items-center gap-3 my-4"
          >
            <div className="h-px flex-1 bg-border/70" />
            <span className="rounded-full bg-muted px-2.5 py-0.5 text-[10px] font-medium text-muted-foreground whitespace-nowrap">
              Turn {seg.turnN ?? "?"}
            </span>
            <div className="h-px flex-1 bg-border/70" />
          </div>
        );
      }

      return null;
    });
  };

  return (
    <AiMessageProvider state={state} actions={actions} meta={meta}>
      <div className="min-w-0 px-0.5 py-2">
        {/* 加载中占位符 */}
        {isEmpty && isStreaming && !isStopped && <LoadingPlaceholder />}

        {/* 终止状态提示 */}
        {isStopped && <StoppedIndicator />}

        {/* 纯文本内容（没有 text segments 时渲染 content 作为后备） */}
        {content && texts.length === 0 && (
          <div className="prose prose-sm max-w-none min-w-0 break-all">
            <ChartAwareMarkdown
              content={content}
              token={undefined}
              sessionId={sessionId}
              onOpenInMainCanvas={onOpenWorkspaceArtifact}
            />
          </div>
        )}

        {/* 按顺序渲染的内容 */}
        {renderSegments()}

        {/* Worker 状态指示器 */}
        <WorkerIndicators />
      </div>
    </AiMessageProvider>
  );
});

export default AiMessageContent;
