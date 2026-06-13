/**
 * SubAgentDetailDrawer - Sub Agent 详情抽屉
 * 
 * 显示单个 Sub Agent 的完整执行时间线和输出文件
 * 单层视图：只有执行时间线，没有细分 Tab
 */

import { useState, useMemo } from "react";
import { 
  Play, 
  CheckCircle2, 
  XCircle, 
  Pause,
  Square,
  Clock,
  RefreshCw,
  Loader2,
  MessageSquare,
  Wrench,
  Zap,
  User,
  Bot,
  Settings2,
  Hammer,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { ChartAwareMarkdown } from "@/components/chat/ChartAwareMarkdown";
import { AiMessageContent } from "@/components/chat/AiMessageContent";
import { ToolPreviewPopover } from "@/components/ToolPreviewPopover";
import { resolveToolPreviewFromEvents } from "@/lib/toolPreview";
import type { ExecutionEvent, SubAgentDetail } from "@/hooks/useExecutionTree";
import type { ChatSegment } from "@/pages/WorkspacePage/types";

interface SubAgentDetailDrawerProps {
  subagent: SubAgentDetail | null;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  isLoading?: boolean;
  onStop?: () => Promise<void>;
  onRetry?: () => Promise<void>;
  userId?: string;
  sessionId?: string;
  allowStopActions?: boolean;
  allowRetryActions?: boolean;
  /** 内嵌模式：不渲染 Sheet 外壳，直接输出内容面板 */
  inline?: boolean;
  onOpenWorkspaceFile?: (file: { name: string }) => void;
  onOpenInBrowserTab?: (url: string) => void;
}

const statusConfigMap: Record<string, { label: string; icon: typeof Clock; color: string; animate?: boolean }> = {
  idle: { label: "空闲", icon: Clock, color: "text-muted-foreground" },
  running: { label: "运行中", icon: Play, color: "text-tertiary", animate: true },
  completed: { label: "已完成", icon: CheckCircle2, color: "text-success" },
  failed: { label: "失败", icon: XCircle, color: "text-error" },
  cancelled: { label: "已取消", icon: Pause, color: "text-warning" },
  closed: { label: "已关闭", icon: Square, color: "text-muted-foreground" },
  queued: { label: "排队中", icon: Clock, color: "text-warning" },
};

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${Math.floor(ms / 1000)}s`;
  if (ms < 3600000) return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  return `${Math.floor(ms / 3600000)}h ${Math.floor((ms % 3600000) / 60000)}m`;
}

function formatShortId(value?: string | null): string {
  if (!value) return "未记录";
  return value.length <= 16 ? value : `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function getNodeRoleLabel(subagent: SubAgentDetail | null): string {
  if (!subagent) return "协作节点";
  if (subagent.hosting_controller || subagent.node_role === "hosting_controller") {
    return "托管控制节点";
  }
  return "协作节点";
}

function getExpertRoleLabel(subagent: SubAgentDetail | null): string | null {
  return subagent?.role_summary?.display_name || subagent?.subagent_type || null;
}

function formatTimestamp(timestamp?: number): string {
  if (!timestamp) return "";
  const date = new Date(timestamp * 1000);
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatIsoTime(value?: string | null): string {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return date.toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function summarizeStepProgress(events: ExecutionEvent[]): { current: number; total: number } {
  let stepEvents = 0;
  let currentStep = 0;

  for (const event of events) {
    if (event.type !== "step_begin") continue;
    stepEvents += 1;
    const reportedStep = event.step_n;
    if (typeof reportedStep === "number") {
      currentStep = Math.max(currentStep, reportedStep, stepEvents);
    } else {
      currentStep = Math.max(currentStep, stepEvents);
    }
  }

  if (currentStep <= 0) {
    return { current: 0, total: 0 };
  }

  return { current: currentStep, total: currentStep };
}

function stringifyStructuredValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value == null) {
    return "";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function normalizeContextContent(content: unknown): string {
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") return part;
        if (!part || typeof part !== "object") return "";
        if ("text" in part && typeof part.text === "string") return part.text;
        if ("think" in part && typeof part.think === "string") return part.think;
        if ("type" in part && part.type === "image_url") return "[图片]";
        return stringifyStructuredValue(part);
      })
      .join("");
  }
  return stringifyStructuredValue(content);
}

interface DispatchMessage {
  id: string;
  content: string;
  timestamp?: string | null;
}

interface ContextFallbackMessage {
  id: string;
  role: "assistant" | "system" | "tool";
  content: string;
  timestamp?: string | null;
  toolCallId?: string | null;
}

interface AssistantTimelineBlock {
  id: string;
  step: number | null;
  timestamp?: number;
  segments: ChatSegment[];
}

function buildDispatchMessages(subagent: SubAgentDetail | null): DispatchMessage[] {
  if (!subagent) return [];

  const contextMessages: DispatchMessage[] = [];
  (subagent.context ?? []).forEach((msg, idx) => {
    const m = msg as Record<string, unknown> | null | undefined;
    if (m?.role !== "user") return;
    const content = normalizeContextContent(m?.content as string).trim();
    if (!content) return;
    contextMessages.push({
      id: `dispatch-context-${idx}`,
      content,
      timestamp: typeof m?.timestamp === "string" ? (m.timestamp as string) : null,
    });
  });

  if (contextMessages.length > 0) {
    return contextMessages;
  }

  const roleLabel = subagent.role_summary?.display_name || subagent.subagent_type || "协作节点";
  const taskDescription = subagent.description?.trim();
  const metaRecord = subagent.meta as Record<string, unknown>;
  const launchSpec = metaRecord.launch_spec as Record<string, unknown> | undefined;
  const effectiveModel =
    typeof launchSpec?.effective_model === "string"
      ? launchSpec.effective_model as string
      : null;

  let content = `派发 ${roleLabel} 执行当前子任务。`;
  if (taskDescription) {
    content = `派发 ${roleLabel} 执行：${taskDescription}`;
  }
  if (effectiveModel) {
    content += `\n\n运行模型：${effectiveModel}`;
  }

  return [{
    id: "dispatch-synthetic",
    content,
    timestamp: subagent.created_at,
  }];
}

function buildFallbackContextMessages(context: unknown[]): ContextFallbackMessage[] {
  const messages: ContextFallbackMessage[] = [];
  context.forEach((msg, idx) => {
    if (!msg || typeof msg !== "object") return;
    const entry = msg as Record<string, unknown>;
    const role =
      entry.role === "assistant" || entry.role === "system" || entry.role === "tool"
        ? entry.role
        : null;
    if (!role) return;
    const content = normalizeContextContent(entry.content).trim();
    if (!content) return;
    messages.push({
      id: `context-${role}-${idx}`,
      role,
      content,
      timestamp: typeof entry.timestamp === "string" ? entry.timestamp : null,
      toolCallId: typeof entry.tool_call_id === "string" ? entry.tool_call_id : null,
    });
  });
  return messages;
}

function buildAssistantTimelineBlocks(events: ExecutionEvent[]): AssistantTimelineBlock[] {
  const blocks: AssistantTimelineBlock[] = [];
  let currentBlockIndex = -1;
  let pendingStep: number | null = null;

  const ensureBlock = (timestamp?: number) => {
    const existingBlock =
      currentBlockIndex >= 0 ? blocks[currentBlockIndex] : undefined;
    if (existingBlock) {
      if (!existingBlock.timestamp && timestamp) {
        existingBlock.timestamp = timestamp;
      }
      if (existingBlock.step == null && pendingStep != null) {
        existingBlock.step = pendingStep;
      }
      return existingBlock;
    }

    const block: AssistantTimelineBlock = {
        id: `assistant-block-${blocks.length + 1}`,
        step: pendingStep,
        timestamp,
        segments: [],
      };
    blocks.push(block);
    currentBlockIndex = blocks.length - 1;
    return block;
  };

  for (const event of events) {
    switch (event.type) {
      case "turn_begin":
      case "turn_end":
      case "status":
        continue;
      case "step_begin": {
        pendingStep = typeof event.step_n === "number" ? event.step_n : pendingStep;
        const activeBlock =
          currentBlockIndex >= 0 ? blocks[currentBlockIndex] : undefined;
        if (activeBlock && activeBlock.segments.length > 0) {
          currentBlockIndex = -1;
        } else if (activeBlock) {
          activeBlock.step = pendingStep;
          if (!activeBlock.timestamp && event.timestamp) {
            activeBlock.timestamp = event.timestamp;
          }
        }
        continue;
      }
      case "think": {
        const block = ensureBlock(event.timestamp);
        block.segments.push({
          type: "think",
          content: typeof event.think === "string" ? event.think : stringifyStructuredValue(event.think),
        });
        continue;
      }
      case "text": {
        const block = ensureBlock(event.timestamp);
        block.segments.push({
          type: "text",
          content: typeof event.text === "string" ? event.text : stringifyStructuredValue(event.text),
        });
        continue;
      }
      case "tool_call": {
        const block = ensureBlock(event.timestamp);
        block.segments.push({
          type: "tool_call",
          content: "",
          toolName: typeof event.tool_name === "string" ? event.tool_name : "unknown",
          toolCallId: typeof event.tool_call_id === "string" ? event.tool_call_id : undefined,
          toolParams: stringifyStructuredValue(event.arguments),
        });
        continue;
      }
      case "tool_result": {
        const block = ensureBlock(event.timestamp);
        block.segments.push({
          type: "tool_output",
          content: stringifyStructuredValue(event.content),
          toolCallId: typeof event.tool_call_id === "string" ? event.tool_call_id : undefined,
          toolName: typeof event.tool_name === "string" ? event.tool_name : undefined,
          isError: Boolean(event.is_error),
        });
        continue;
      }
      default: {
        const fallbackText =
          typeof event.message === "string"
            ? event.message
            : typeof event.error === "string"
              ? event.error
              : "";
        if (!fallbackText.trim()) {
          continue;
        }
        const block = ensureBlock(event.timestamp);
        block.segments.push({
          type: "text",
          content: fallbackText,
        });
      }
    }
  }

  return blocks.filter((block) => block.segments.length > 0);
}

// Worker 工作区文件浏览器组件
export function SubAgentDetailDrawer({
  subagent,
  open,
  onOpenChange,
  isLoading,
  onStop,
  onRetry,
  userId,
  sessionId,
  allowStopActions = false,
  allowRetryActions = false,
  inline = false,
  onOpenWorkspaceFile,
  onOpenInBrowserTab,
}: SubAgentDetailDrawerProps) {
  void userId;
  const [isStopping, setIsStopping] = useState(false);
  const [isRetrying, setIsRetrying] = useState(false);

  // 工具详情弹窗状态 - 使用与 Host Agent 统一的 ToolPreviewPopover
  const [toolPreviewOpen, setToolPreviewOpen] = useState(false);
  const [toolPreviewData, setToolPreviewData] = useState<{
    toolName: string;
    toolParams?: Record<string, unknown>;
    toolOutput?: string;
    taskId?: string;
    triggerRect?: DOMRect;
  } | null>(null);
  
  // 处理工具详情查看
  const handleViewToolDetails = (toolCallId: string, taskId: string | undefined, triggerRect: DOMRect) => {
    if (!subagent) return;
    const { toolName, toolParams, toolOutput } = resolveToolPreviewFromEvents(
      subagent?.events ?? [],
      toolCallId,
    );

    setToolPreviewData({
      toolName,
      toolParams,
      toolOutput,
      taskId,
      triggerRect,
    });
    setToolPreviewOpen(true);
  };
  
  const status = subagent?.status || "idle";
  const statusConfigItem = statusConfigMap[status] || statusConfigMap.idle;
  const StatusIcon = statusConfigItem.icon;
  const nodeRoleLabel = getNodeRoleLabel(subagent);
  const expertRoleLabel = getExpertRoleLabel(subagent);
  const parentToolCallId = subagent?.parent_tool_call_id || subagent?.ownership?.parent_tool_call_id;
  const createdAtLabel = subagent?.created_at
    || ((subagent?.meta as Record<string, unknown>)?.created_at ? new Date(((subagent?.meta as Record<string, unknown>).created_at as number) * 1000).toISOString() : null);
  
  const handleStop = async () => {
    if (!onStop) return;
    setIsStopping(true);
    try {
      await onStop();
    } catch (err) {
      const message = err instanceof Error ? err.message : "停止失败";
      console.error("停止协作节点失败:", err);
      alert(`停止失败: ${message}`);
    } finally {
      setIsStopping(false);
    }
  };

  const handleRetry = async () => {
    if (!onRetry) return;
    setIsRetrying(true);
    try {
      await onRetry();
    } catch (err) {
      const message = err instanceof Error ? err.message : "重试失败";
      console.error("重试协作节点失败:", err);
      alert(`重试失败: ${message}`);
    } finally {
      setIsRetrying(false);
    }
  };
  
  // 计算进度
  const events = useMemo(() => subagent?.events ?? [], [subagent?.events]);
  const progress = useMemo(() => summarizeStepProgress(events), [events]);
  const dispatchMessages = useMemo(() => buildDispatchMessages(subagent), [subagent]);
  const assistantBlocks = useMemo(() => buildAssistantTimelineBlocks(events), [events]);
  const fallbackContextMessages = useMemo(
    () => (assistantBlocks.length > 0 ? [] : buildFallbackContextMessages(subagent?.context ?? [])),
    [assistantBlocks.length, subagent?.context],
  );
  const timelineItemCount =
    dispatchMessages.length + assistantBlocks.length + fallbackContextMessages.length;

  if (!subagent && !isLoading) {
    return null;
  }

  if (inline) {
    return (
      <div className="flex flex-col h-full bg-background">

        {!inline && (
          <SheetHeader className="sr-only">
            <SheetTitle>
              {subagent?.description || subagent?.name || "协作节点详情"}
            </SheetTitle>
            <SheetDescription>
              查看单个协作节点的派发信息、事件流、工具调用与产出文件。
            </SheetDescription>
          </SheetHeader>
        )}
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : subagent ? (
          <>
            {/* 头部 */}
            <div className="px-4 py-3 border-b space-y-3">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center",
                    "bg-primary/10"
                  )}>
                    <StatusIcon className={cn(
                      "w-5 h-5", 
                      statusConfigItem.color,
                      statusConfigItem.animate && "animate-pulse"
                    )} />
                  </div>
                  <div>
                    <div className="text-base font-semibold text-foreground">
                      {subagent.name || subagent.description}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                      <code className="bg-muted px-1 rounded">{subagent.id.slice(0, 8)}...</code>
                      <span>·</span>
                      <span>
                        {createdAtLabel
                          ? new Date(createdAtLabel).toLocaleString()
                          : "创建时间未记录"}
                      </span>
                    </div>
                  </div>
                </div>
                
                {/* 操作按钮 */}
                {allowStopActions || allowRetryActions ? (
                  <div className="flex items-center gap-1">
                    {allowStopActions && status === "running" ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={handleStop}
                        disabled={isStopping}
                      >
                        {isStopping ? (
                          <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <Pause className="w-3.5 h-3.5 mr-1" />
                        )}
                        停止
                      </Button>
                    ) : null}
                    {allowRetryActions && (status === "failed" || status === "cancelled") ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={handleRetry}
                        disabled={isRetrying}
                      >
                        {isRetrying ? (
                          <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <RefreshCw className="w-3.5 h-3.5 mr-1" />
                        )}
                        重试
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              
              {/* 状态栏 */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
                <Badge
                  variant={status === "running" ? "default" : "outline"}
                  className="text-[10px] shrink-0"
                >
                  {statusConfigItem.label}
                </Badge>
                <Badge variant="outline" className="text-[10px] shrink-0">
                  {nodeRoleLabel}
                </Badge>
                {expertRoleLabel ? (
                  <Badge variant="secondary" className="text-[10px] shrink-0">
                    {expertRoleLabel}
                  </Badge>
                ) : null}

                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
                  <span className="flex items-center gap-1 shrink-0">
                    <Zap className="w-3 h-3 shrink-0" />
                    {progress.total > 0 ? `Step ${progress.current} / ${progress.total}` : "未记录步骤"}
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <Clock className="w-3 h-3 shrink-0" />
                    {formatDuration(subagent.duration_ms || 0)}
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <Wrench className="w-3 h-3 shrink-0" />
                    {events.filter(e => e.type === "tool_call").length} 节点内工具
                  </span>
                </div>
              </div>
              
              {/* 描述 */}
              {subagent.description && (
                <p className="text-xs text-muted-foreground">
                  {subagent.description}
                </p>
              )}

              <div className="rounded-lg border border-border bg-muted/10 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                任务进度和节点配置请到工作区"专家协作节点"视图查看。
              </div>
            </div>

            <div className="border-b border-border bg-muted/10 px-4 py-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-medium text-foreground">
                  <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                  协作节点会话流
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                  <span>{timelineItemCount} 段</span>
                  <span>·</span>
                  <span>{events.length} 事件</span>
                  <span>·</span>
                  <span>{subagent.output_files.length} 文件</span>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-hidden">
              <ScrollArea className={inline ? "h-full" : "h-[calc(100vh-280px)]"}>
                <div className="min-w-0 p-4">
                  {timelineItemCount === 0 ? (
                    <div className="text-center py-10 text-muted-foreground">
                      <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <p className="text-xs">暂无协作节点会话记录</p>
                    </div>
                  ) : (
                    <div className="space-y-5">
                      {dispatchMessages.map((message) => (
                        <div key={message.id} className="flex gap-3">
                          <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                            <User className="h-3.5 w-3.5" />
                          </div>
                          <div className="flex min-w-0 flex-1 flex-col items-start gap-1.5">
                            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                              <span className="font-medium text-foreground/80">主控调用 Task 派发</span>
                              {parentToolCallId ? (
                                <code className="rounded bg-muted px-1 py-0.5 text-[10px]">
                                  {formatShortId(parentToolCallId)}
                                </code>
                              ) : null}
                              {formatIsoTime(message.timestamp) ? (
                                <span>{formatIsoTime(message.timestamp)}</span>
                              ) : null}
                            </div>
                            <div className="min-w-0 max-w-full overflow-hidden rounded-2xl bg-primary/10 px-3 py-2 text-sm text-foreground ring-1 ring-primary/10 shadow-sm">
                              <div className="prose prose-sm max-w-none min-w-0 break-all">
                                <ChartAwareMarkdown
                                  content={message.content}
                                  paragraphClassName="my-0"
                                  onOpenInMainCanvas={onOpenWorkspaceFile ? (file) => onOpenWorkspaceFile({ name: file.name }) : undefined}
                                  onOpenInBrowserTab={onOpenInBrowserTab}
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}

                      {assistantBlocks.map((block) => {
                        const toolCount = block.segments.filter(
                          (segment) => segment.type === "tool_call",
                        ).length;
                        return (
                          <div key={block.id} className="flex gap-3">
                            <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-muted text-muted-foreground">
                              <Bot className="h-3.5 w-3.5" />
                            </div>
                            <div className="min-w-0 flex-1 space-y-1.5">
                              <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                <span className="font-medium text-foreground/80">协作节点</span>
                                {block.step != null ? (
                                  <Badge variant="outline" className="h-5 text-[10px]">
                                    Step {block.step}
                                  </Badge>
                                ) : null}
                                {toolCount > 0 ? (
                                  <Badge variant="outline" className="h-5 text-[10px]">
                                    {toolCount} 个节点内工具
                                  </Badge>
                                ) : null}
                                {formatTimestamp(block.timestamp) ? (
                                  <span>{formatTimestamp(block.timestamp)}</span>
                                ) : null}
                              </div>
                              <AiMessageContent
                                segments={block.segments}
                                isStreaming={subagent.status === "running" && block === assistantBlocks[assistantBlocks.length - 1]}
                                sessionId={sessionId}
                                onViewToolDetails={handleViewToolDetails}
                                showToolOutputs={true}
                              />
                            </div>
                          </div>
                        );
                      })}

                      {fallbackContextMessages.map((message) => {
                        if (message.role === "assistant") {
                          return (
                            <div key={message.id} className="flex gap-3">
                              <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-muted text-muted-foreground">
                                <Bot className="h-3.5 w-3.5" />
                              </div>
                              <div className="min-w-0 flex-1 space-y-1.5">
                                <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                  <span className="font-medium text-foreground/80">协作节点</span>
                                  {formatIsoTime(message.timestamp) ? (
                                    <span>{formatIsoTime(message.timestamp)}</span>
                                  ) : null}
                                </div>
                                <AiMessageContent
                                  segments={[{ type: "text", content: message.content }]}
                                  isStreaming={subagent.status === "running"}
                                  sessionId={sessionId}
                                  onViewToolDetails={handleViewToolDetails}
                                />
                              </div>
                            </div>
                          );
                        }

                        if (message.role === "tool") {
                          return (
                            <div
                              key={message.id}
                              className="ml-10 rounded-lg border border-border/60 bg-muted/20 px-3 py-2"
                            >
                              <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
                                <Hammer className="h-3 w-3" />
                                <span>工具结果</span>
                                {message.toolCallId ? (
                                  <code className="rounded bg-muted px-1 py-0.5 text-[10px]">
                                    {formatShortId(message.toolCallId)}
                                  </code>
                                ) : null}
                              </div>
                              <div className="mt-1 text-xs text-foreground/80">
                                <ChartAwareMarkdown
                                  content={message.content}
                                  paragraphClassName="my-0"
                                  onOpenInMainCanvas={onOpenWorkspaceFile ? (file) => onOpenWorkspaceFile({ name: file.name }) : undefined}
                                  onOpenInBrowserTab={onOpenInBrowserTab}
                                />
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div
                            key={message.id}
                            className="ml-10 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2"
                          >
                            <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
                              <Settings2 className="h-3 w-3" />
                              <span>系统提示</span>
                              {formatIsoTime(message.timestamp) ? (
                                <span>{formatIsoTime(message.timestamp)}</span>
                              ) : null}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              <ChartAwareMarkdown
                                content={message.content}
                                paragraphClassName="my-0"
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
            
            {/* 工具详情悬浮窗 - 复用 Host Agent 的 ToolPreviewPopover */}
            <ToolPreviewPopover
              isOpen={toolPreviewOpen}
              onClose={() => setToolPreviewOpen(false)}
              toolName={toolPreviewData?.toolName || ""}
              toolParams={toolPreviewData?.toolParams}
              toolOutput={toolPreviewData?.toolOutput}
              taskId={toolPreviewData?.taskId}
              triggerRect={toolPreviewData?.triggerRect}
            />
          </>
        ) : null}
      </div>
    );
  }

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="w-[500px] sm:max-w-[500px] p-0 flex flex-col">

        {!inline && (
          <SheetHeader className="sr-only">
            <SheetTitle>
              {subagent?.description || subagent?.name || "协作节点详情"}
            </SheetTitle>
            <SheetDescription>
              查看单个协作节点的派发信息、事件流、工具调用与产出文件。
            </SheetDescription>
          </SheetHeader>
        )}
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
          </div>
        ) : subagent ? (
          <>
            {/* 头部 */}
            <div className="px-4 py-3 border-b space-y-3">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className={cn(
                    "w-10 h-10 rounded-lg flex items-center justify-center",
                    "bg-primary/10"
                  )}>
                    <StatusIcon className={cn(
                      "w-5 h-5", 
                      statusConfigItem.color,
                      statusConfigItem.animate && "animate-pulse"
                    )} />
                  </div>
                  <div>
                    <div className="text-base font-semibold text-foreground">
                      {subagent.name || subagent.description}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mt-0.5">
                      <code className="bg-muted px-1 rounded">{subagent.id.slice(0, 8)}...</code>
                      <span>·</span>
                      <span>
                        {createdAtLabel
                          ? new Date(createdAtLabel).toLocaleString()
                          : "创建时间未记录"}
                      </span>
                    </div>
                  </div>
                </div>
                
                {/* 操作按钮 */}
                {allowStopActions || allowRetryActions ? (
                  <div className="flex items-center gap-1">
                    {allowStopActions && status === "running" ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={handleStop}
                        disabled={isStopping}
                      >
                        {isStopping ? (
                          <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <Pause className="w-3.5 h-3.5 mr-1" />
                        )}
                        停止
                      </Button>
                    ) : null}
                    {allowRetryActions && (status === "failed" || status === "cancelled") ? (
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs"
                        onClick={handleRetry}
                        disabled={isRetrying}
                      >
                        {isRetrying ? (
                          <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <RefreshCw className="w-3.5 h-3.5 mr-1" />
                        )}
                        重试
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
              
              {/* 状态栏 */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs">
                <Badge
                  variant={status === "running" ? "default" : "outline"}
                  className="text-[10px] shrink-0"
                >
                  {statusConfigItem.label}
                </Badge>
                <Badge variant="outline" className="text-[10px] shrink-0">
                  {nodeRoleLabel}
                </Badge>
                {expertRoleLabel ? (
                  <Badge variant="secondary" className="text-[10px] shrink-0">
                    {expertRoleLabel}
                  </Badge>
                ) : null}

                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-muted-foreground">
                  <span className="flex items-center gap-1 shrink-0">
                    <Zap className="w-3 h-3 shrink-0" />
                    {progress.total > 0 ? `Step ${progress.current} / ${progress.total}` : "未记录步骤"}
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <Clock className="w-3 h-3 shrink-0" />
                    {formatDuration(subagent.duration_ms || 0)}
                  </span>
                  <span className="flex items-center gap-1 shrink-0">
                    <Wrench className="w-3 h-3 shrink-0" />
                    {events.filter(e => e.type === "tool_call").length} 节点内工具
                  </span>
                </div>
              </div>
              
              {/* 描述 */}
              {subagent.description && (
                <p className="text-xs text-muted-foreground">
                  {subagent.description}
                </p>
              )}

              <div className="rounded-lg border border-border bg-muted/10 px-3 py-2 text-[11px] leading-5 text-muted-foreground">
                这是一次主控派发出来的协作实例，只展示本次执行记录。任务进度和会话关系请到工作区视图查看。
              </div>

              {subagent.role_summary ? (
                <div className="rounded-lg border border-border bg-muted/10 px-3 py-2 text-[11px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="font-medium text-foreground">
                      {subagent.role_summary.display_name}
                    </div>
                    <Badge variant="outline" className="text-[10px]">
                      {subagent.role_summary.role_id}
                    </Badge>
                    {subagent.role_summary.tool_policy ? (
                      <Badge
                        variant={
                          subagent.role_summary.tool_policy === "inherit"
                            ? "outline"
                            : "secondary"
                        }
                        className="text-[10px]"
                      >
                        {subagent.role_summary.tool_policy === "inherit"
                          ? "继承模式"
                          : "白名单模式"}
                      </Badge>
                    ) : null}
                    {subagent.role_summary.supports_background ? (
                      <Badge variant="outline" className="text-[10px]">
                        可后台
                      </Badge>
                    ) : null}
                  </div>
                  <div className="mt-1 text-muted-foreground">
                    {subagent.role_summary.description}
                  </div>
                  {subagent.role_summary.when_to_use ? (
                    <div className="mt-2 text-muted-foreground">
                      主控选择建议：{subagent.role_summary.when_to_use}
                    </div>
                  ) : null}
                  <div className="mt-2 flex flex-wrap gap-2">
                    {subagent.role_summary.capabilities.map((capability) => (
                      <Badge key={capability} variant="outline" className="text-[10px]">
                        {capability}
                      </Badge>
                    ))}
                    {subagent.role_summary.permissions.map((permission) => (
                      <Badge
                        key={permission}
                        variant="secondary"
                        className="text-[10px]"
                      >
                        {permission}
                      </Badge>
                    ))}
                  </div>
                </div>
              ) : null}

              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                  <div className="text-[10px] text-muted-foreground">主控会话</div>
                  <div className="mt-1 font-medium text-foreground">
                    {formatShortId(subagent.host_session_id || subagent.ownership?.host_session_id)}
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                  <div className="text-[10px] text-muted-foreground">实例 ID</div>
                  <div className="mt-1 font-medium text-foreground">
                    {formatShortId(subagent.agent_id || subagent.id)}
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                  <div className="text-[10px] text-muted-foreground">父派发调用</div>
                  <div className="mt-1 font-medium text-foreground">
                    {formatShortId(parentToolCallId)}
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                  <div className="text-[10px] text-muted-foreground">节点角色</div>
                  <div className="mt-1 font-medium text-foreground">
                    {nodeRoleLabel}
                  </div>
                </div>
                <div className="rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                  <div className="text-[10px] text-muted-foreground">协作专家</div>
                  <div className="mt-1 font-medium text-foreground">
                    {expertRoleLabel || "内联创建（无模板）"}
                  </div>
                  {subagent.role_summary?.role_id ? (
                    <div className="mt-1 text-[10px] text-muted-foreground">
                      {subagent.role_summary.role_id}
                    </div>
                  ) : null}
                </div>
                {subagent.bound_host_session_id ? (
                  <div className="col-span-2 rounded-lg border border-border bg-muted/20 px-2.5 py-2">
                    <div className="text-[10px] text-muted-foreground">绑定主控</div>
                    <div className="mt-1 font-medium text-foreground">
                      {formatShortId(subagent.bound_host_session_id)}
                    </div>
                  </div>
                ) : null}
              </div>
            </div>

            <div className="border-b border-border bg-muted/10 px-4 py-2.5">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2 text-xs font-medium text-foreground">
                  <MessageSquare className="h-3.5 w-3.5 text-muted-foreground" />
                  协作节点会话流
                </div>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                  <span>{timelineItemCount} 段</span>
                  <span>·</span>
                  <span>{events.length} 事件</span>
                  <span>·</span>
                  <span>{subagent.output_files.length} 文件</span>
                </div>
              </div>
            </div>

            <div className="flex-1 overflow-hidden">
              <ScrollArea className={inline ? "h-full" : "h-[calc(100vh-280px)]"}>
                <div className="min-w-0 p-4">
                  {timelineItemCount === 0 ? (
                    <div className="text-center py-10 text-muted-foreground">
                      <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-30" />
                      <p className="text-xs">暂无协作节点会话记录</p>
                    </div>
                  ) : (
                    <div className="space-y-5">
                      {dispatchMessages.map((message) => (
                        <div key={message.id} className="flex gap-3">
                          <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary">
                            <User className="h-3.5 w-3.5" />
                          </div>
                          <div className="flex min-w-0 flex-1 flex-col items-start gap-1.5">
                            <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                              <span className="font-medium text-foreground/80">主控调用 Task 派发</span>
                              {parentToolCallId ? (
                                <code className="rounded bg-muted px-1 py-0.5 text-[10px]">
                                  {formatShortId(parentToolCallId)}
                                </code>
                              ) : null}
                              {formatIsoTime(message.timestamp) ? (
                                <span>{formatIsoTime(message.timestamp)}</span>
                              ) : null}
                            </div>
                            <div className="min-w-0 max-w-full overflow-hidden rounded-2xl bg-primary/10 px-3 py-2 text-sm text-foreground ring-1 ring-primary/10 shadow-sm">
                              <div className="prose prose-sm max-w-none min-w-0 break-all">
                                <ChartAwareMarkdown
                                  content={message.content}
                                  paragraphClassName="my-0"
                                  onOpenInMainCanvas={onOpenWorkspaceFile ? (file) => onOpenWorkspaceFile({ name: file.name }) : undefined}
                                  onOpenInBrowserTab={onOpenInBrowserTab}
                                />
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}

                      {assistantBlocks.map((block) => {
                        const toolCount = block.segments.filter(
                          (segment) => segment.type === "tool_call",
                        ).length;
                        return (
                          <div key={block.id} className="flex gap-3">
                            <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-muted text-muted-foreground">
                              <Bot className="h-3.5 w-3.5" />
                            </div>
                            <div className="min-w-0 flex-1 space-y-1.5">
                              <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                <span className="font-medium text-foreground/80">协作节点</span>
                                {block.step != null ? (
                                  <Badge variant="outline" className="h-5 text-[10px]">
                                    Step {block.step}
                                  </Badge>
                                ) : null}
                                {toolCount > 0 ? (
                                  <Badge variant="outline" className="h-5 text-[10px]">
                                    {toolCount} 个节点内工具
                                  </Badge>
                                ) : null}
                                {formatTimestamp(block.timestamp) ? (
                                  <span>{formatTimestamp(block.timestamp)}</span>
                                ) : null}
                              </div>
                              <AiMessageContent
                                segments={block.segments}
                                isStreaming={subagent.status === "running" && block === assistantBlocks[assistantBlocks.length - 1]}
                                sessionId={sessionId}
                                onViewToolDetails={handleViewToolDetails}
                                showToolOutputs={true}
                              />
                            </div>
                          </div>
                        );
                      })}

                      {fallbackContextMessages.map((message) => {
                        if (message.role === "assistant") {
                          return (
                            <div key={message.id} className="flex gap-3">
                              <div className="mt-0.5 flex h-7 w-7 items-center justify-center rounded-full bg-muted text-muted-foreground">
                                <Bot className="h-3.5 w-3.5" />
                              </div>
                              <div className="min-w-0 flex-1 space-y-1.5">
                                <div className="flex flex-wrap items-center gap-2 text-[10px] text-muted-foreground">
                                  <span className="font-medium text-foreground/80">协作节点</span>
                                  {formatIsoTime(message.timestamp) ? (
                                    <span>{formatIsoTime(message.timestamp)}</span>
                                  ) : null}
                                </div>
                                <AiMessageContent
                                  segments={[{ type: "text", content: message.content }]}
                                  isStreaming={subagent.status === "running"}
                                  sessionId={sessionId}
                                  onViewToolDetails={handleViewToolDetails}
                                />
                              </div>
                            </div>
                          );
                        }

                        if (message.role === "tool") {
                          return (
                            <div
                              key={message.id}
                              className="ml-10 rounded-lg border border-border/60 bg-muted/20 px-3 py-2"
                            >
                              <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
                                <Hammer className="h-3 w-3" />
                                <span>工具结果</span>
                                {message.toolCallId ? (
                                  <code className="rounded bg-muted px-1 py-0.5 text-[10px]">
                                    {formatShortId(message.toolCallId)}
                                  </code>
                                ) : null}
                              </div>
                              <div className="mt-1 text-xs text-foreground/80">
                                <ChartAwareMarkdown
                                  content={message.content}
                                  paragraphClassName="my-0"
                                  onOpenInMainCanvas={onOpenWorkspaceFile ? (file) => onOpenWorkspaceFile({ name: file.name }) : undefined}
                                  onOpenInBrowserTab={onOpenInBrowserTab}
                                />
                              </div>
                            </div>
                          );
                        }

                        return (
                          <div
                            key={message.id}
                            className="ml-10 rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2"
                          >
                            <div className="flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
                              <Settings2 className="h-3 w-3" />
                              <span>系统提示</span>
                              {formatIsoTime(message.timestamp) ? (
                                <span>{formatIsoTime(message.timestamp)}</span>
                              ) : null}
                            </div>
                            <div className="mt-1 text-xs text-muted-foreground">
                              <ChartAwareMarkdown
                                content={message.content}
                                paragraphClassName="my-0"
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </ScrollArea>
            </div>
            
            {/* 工具详情悬浮窗 - 复用 Host Agent 的 ToolPreviewPopover */}
            <ToolPreviewPopover
              isOpen={toolPreviewOpen}
              onClose={() => setToolPreviewOpen(false)}
              toolName={toolPreviewData?.toolName || ""}
              toolParams={toolPreviewData?.toolParams}
              toolOutput={toolPreviewData?.toolOutput}
              taskId={toolPreviewData?.taskId}
              triggerRect={toolPreviewData?.triggerRect}
            />
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
