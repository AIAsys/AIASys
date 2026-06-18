/**
 * ChatArea - 聊天消息显示区域
 *
 * 重构为 Compound Components 模式：
 * - 避免 boolean prop 泛滥
 * - 每个子组件职责单一
 * - 通过 Context 共享状态
 *
 * @example
 * ```tsx
 * <ChatArea items={items} actions={actions}>
 *   <ChatArea.List />
 * </ChatArea>
 * ```
 */
import {
  type RefObject,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ArrowDown, Loader2 } from "lucide-react";
import { useVirtualizer } from "@tanstack/react-virtual";
import type { ChatItem } from "@/pages/WorkspacePage/types";
import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MessageItem } from "./MessageItem";
import { AskUserInlineCard } from "@/components/AskUserInlineCard";
import { CapabilityConfirmationCard } from "@/components/CapabilityConfirmationCard";
import { askUserBridge } from "@/lib/askUserBridge";
import type { ChatAreaActions, ChatAreaLayout } from "./context";

// Context 和 Provider 导出
export { ChatAreaContext, useChatAreaContext } from "./context";
export { ChatAreaProvider } from "./ChatAreaProvider";

// 子组件导出
export { MessageAvatar } from "./MessageAvatar";
export { MessageBody } from "./MessageBody";
export { MessageContent } from "./MessageContent";
export { MessageLayout } from "./MessageLayout";
export { MessageTimestamp } from "./MessageTimestamp";
export { UserMessageContent } from "./UserMessageContent";
export { AiMessageContent } from "./AiMessageContent";
export { MessageItem } from "./MessageItem";

interface ChatAreaProps {
  /** 聊天消息列表 */
  items: ChatItem[];
  /** 消息列表滚动引用 */
  messagesEndRef?: RefObject<HTMLDivElement | null>;
  /** 查看执行空间回调 */
  onViewExecutionSpace?: (taskId: string) => void;
  /** Worker 点击回调 */
  onWorkerClick?: (workerName: string) => void;
  /** 在主画布打开工作区产物 */
  onOpenWorkspaceArtifact?: (file: PreviewFile) => void;
  /** 在浏览器标签页打开工作区文件 */
  onOpenInBrowserTab?: (path: string) => void;
  /** 打开执行资源面板 */
  onOpenRuntimeTab?: () => void;
  /** 查看工具调用详情 - 包含触发元素位置用于悬浮窗定位 */
  onViewToolDetails?: (
    toolCallId: string,
    taskId: string | undefined,
    triggerRect: DOMRect,
  ) => void;
  /** 编辑用户消息并从该消息处重新发送 */
  onRewriteUserMessage?: (
    messageId: string,
    content: string,
    originalContent?: string,
  ) => Promise<void> | void;
  /** 重试上一次失败的提交 */
  onRetryLastSubmit?: () => Promise<void> | void;
  /** 加载更多历史消息 */
  onLoadMoreHistory?: () => Promise<void>;
  /** 是否还有更多历史消息 */
  hasMoreHistory?: boolean;
  /** 当前会话是否正在运行 */
  isRunning?: boolean;
  /** 当前会话 ID */
  sessionId?: string;
  /** 布局模式 */
  layout?: ChatAreaLayout;
  /** 子元素 */
  children?: React.ReactNode;
}

/**
 * ChatArea Root 组件
 */
function ChatAreaRoot({
  items,
  messagesEndRef,
  onViewExecutionSpace,
  onWorkerClick,
  onOpenWorkspaceArtifact,
  onOpenInBrowserTab,
  onOpenRuntimeTab,
  onViewToolDetails,
  onRewriteUserMessage,
  onRetryLastSubmit,
  onLoadMoreHistory,
  hasMoreHistory,
  isRunning = false,
  sessionId,
  layout = "default",
  children,
}: ChatAreaProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const contentWrapperRef = useRef<HTMLDivElement | null>(null);
  const [containerWidth, setContainerWidth] = useState<number | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [hasNewContent, setHasNewContent] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const isFollowingBottomRef = useRef(true);
  const isProgrammaticScrollRef = useRef(false);
  const programmaticScrollTimerRef = useRef<number | null>(null);
  const isLoadingMoreRef = useRef(false);
  const previousScrollHeightRef = useRef(0);
  const previousItemsRef = useRef<{
    length: number;
    lastId?: string;
    sessionId?: string;
  }>({
    length: 0,
    lastId: undefined,
    sessionId: undefined,
  });
  const actions: ChatAreaActions = useMemo(
    () => ({
      onViewExecutionSpace,
      onWorkerClick,
      onOpenWorkspaceArtifact,
      onOpenInBrowserTab,
      onOpenRuntimeTab,
      onViewToolDetails,
      onRewriteUserMessage,
      onRetryLastSubmit,
    }),
    [
      onViewExecutionSpace,
      onWorkerClick,
      onOpenWorkspaceArtifact,
      onOpenInBrowserTab,
      onOpenRuntimeTab,
      onViewToolDetails,
      onRewriteUserMessage,
      onRetryLastSubmit,
    ],
  );
  useEffect(() => {
    if (layout === "compact" || layout === "rail" || !containerRef.current) {
      return;
    }

    const element = containerRef.current;
    const updateWidth = () => {
      setContainerWidth(element.clientWidth);
    };

    updateWidth();

    const observer = new ResizeObserver(() => {
      updateWidth();
    });
    observer.observe(element);

    return () => {
      observer.disconnect();
    };
  }, [layout]);

  const isNearBottom = useCallback((element: HTMLDivElement) => {
    return element.scrollHeight - element.scrollTop - element.clientHeight <= 96;
  }, []);

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = "auto") => {
      const container = containerRef.current;
      if (!container) {
        messagesEndRef?.current?.scrollIntoView({ behavior, block: "end" });
        return;
      }

      if (programmaticScrollTimerRef.current) {
        window.clearTimeout(programmaticScrollTimerRef.current);
      }
      isProgrammaticScrollRef.current = true;
      programmaticScrollTimerRef.current = window.setTimeout(() => {
        isProgrammaticScrollRef.current = false;
        programmaticScrollTimerRef.current = null;
      }, behavior === "smooth" ? 450 : 50);

      if (behavior === "smooth") {
        messagesEndRef?.current?.scrollIntoView({
          behavior: "smooth",
          block: "end",
        });
      } else {
        container.scrollTop = container.scrollHeight;
      }

      isFollowingBottomRef.current = true;
      setShowScrollToBottom(false);
      setHasNewContent(false);
    },
    [messagesEndRef],
  );

  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    // 顶部检测：加载更多历史
    if (
      container.scrollTop < 60 &&
      hasMoreHistory &&
      onLoadMoreHistory &&
      !isLoadingMoreRef.current
    ) {
      isLoadingMoreRef.current = true;
      setIsLoadingMore(true);
      previousScrollHeightRef.current = container.scrollHeight;
      onLoadMoreHistory().finally(() => {
        isLoadingMoreRef.current = false;
        setIsLoadingMore(false);
      });
    }

    const atBottom = isNearBottom(container);
    if (isProgrammaticScrollRef.current) {
      if (atBottom) {
        setShowScrollToBottom(false);
        setHasNewContent(false);
      }
      return;
    }

    isFollowingBottomRef.current = atBottom;
    setShowScrollToBottom(!atBottom);
    if (atBottom) {
      setHasNewContent(false);
    }
  }, [hasMoreHistory, isNearBottom, onLoadMoreHistory]);

  useEffect(() => {
    isFollowingBottomRef.current = true;
    setShowScrollToBottom(false);
    setHasNewContent(false);
    requestAnimationFrame(() => scrollToBottom("auto"));
  }, [scrollToBottom, sessionId]);

  // 加载更多后保持滚动位置（补偿新增高度）
  useEffect(() => {
    if (!isLoadingMore && previousScrollHeightRef.current > 0 && containerRef.current) {
      const container = containerRef.current;
      const newScrollHeight = container.scrollHeight;
      const diff = newScrollHeight - previousScrollHeightRef.current;
      if (diff > 0) {
        container.scrollTop += diff;
      }
      previousScrollHeightRef.current = 0;
    }
  }, [isLoadingMore, items.length]);

  useEffect(() => {
    const previous = previousItemsRef.current;
    const lastItem = items[items.length - 1];
    const lastId = lastItem?.id;
    const sessionChanged = previous.sessionId !== sessionId;
    const itemCountChanged = previous.length !== items.length;
    const lastItemChanged = previous.lastId !== lastId;
    const userSubmitted =
      lastItem?.type === "message" && lastItem.sender === "user";

    previousItemsRef.current = {
      length: items.length,
      lastId,
      sessionId,
    };

    if (sessionChanged || userSubmitted) {
      isFollowingBottomRef.current = true;
    }

    if (isFollowingBottomRef.current) {
      requestAnimationFrame(() => scrollToBottom("auto"));
      return;
    }

    if (itemCountChanged || lastItemChanged || items.length > 0) {
      setHasNewContent(true);
      setShowScrollToBottom(true);
    }
  }, [items, scrollToBottom, sessionId]);

  // 监听内容高度变化（如思考过程展开/折叠），若当前在跟随底部则保持滚动到底。
  // 使用 ResizeObserver 观察内容容器自身尺寸变化，比 MutationObserver(subtree)
  // 精准得多：流式 token 插入、虚拟列表挂载等 DOM 变更不会触发回调，只有实际
  // 高度变化时才回调。
  useEffect(() => {
    const wrapper = contentWrapperRef.current;
    if (!wrapper) return;

    let rafId: number | null = null;
    let debounceTimer: number | null = null;
    const observer = new ResizeObserver(() => {
      if (!isFollowingBottomRef.current) return;
      if (debounceTimer) {
        window.clearTimeout(debounceTimer);
      }
      debounceTimer = window.setTimeout(() => {
        if (!isFollowingBottomRef.current) return;
        if (rafId) return;
        rafId = requestAnimationFrame(() => {
          rafId = null;
          scrollToBottom("auto");
        });
      }, 100);
    });

    observer.observe(wrapper);

    return () => {
      observer.disconnect();
      if (rafId) cancelAnimationFrame(rafId);
      if (debounceTimer) window.clearTimeout(debounceTimer);
    };
  }, [scrollToBottom]);

  useEffect(() => {
    return () => {
      if (programmaticScrollTimerRef.current) {
        window.clearTimeout(programmaticScrollTimerRef.current);
      }
    };
  }, []);

  const effectiveLayout =
    layout === "compact" ||
    layout === "rail" ||
    (containerWidth !== null && containerWidth <= 560)
      ? layout === "rail"
        ? "rail"
        : "compact"
      : "default";
  const isCompactSurface =
    effectiveLayout === "compact" || effectiveLayout === "rail";

  return (
    <div className="relative min-h-0 flex-1">
      <div
        ref={containerRef}
        data-testid="chat-scroll-container"
        onScroll={handleScroll}
        className={cn(
          "h-full overflow-y-auto scrollbar-thin scrollbar-thumb-gray-200",
          isCompactSurface ? "px-2 py-4" : "px-4 py-8 lg:px-8 xl:px-12",
        )}
      >
        <div
          ref={contentWrapperRef}
          aria-live="polite"
          aria-relevant="additions"
          className={cn(
            "mx-auto min-w-0",
            isCompactSurface
              ? "max-w-none pb-24"
              : "max-w-4xl pb-32",
          )}
        >
          {isLoadingMore ? (
            <div
              role="status"
              className="flex items-center justify-center py-3"
            >
              <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              <span className="ml-2 text-xs text-muted-foreground">加载更多消息...</span>
            </div>
          ) : null}
          {children || (
            <ChatAreaList
              items={items}
              actions={actions}
              sessionId={sessionId}
              layout={effectiveLayout}
              isRunning={isRunning}
            />
          )}
          {messagesEndRef && <div ref={messagesEndRef} />}
        </div>
      </div>
      {showScrollToBottom && (
        <div className="pointer-events-none absolute bottom-6 left-0 right-0 z-50 flex justify-center px-4">
          <Button
            type="button"
            data-testid="chat-scroll-to-bottom"
            size="sm"
            variant="secondary"
            className="pointer-events-auto h-8 rounded-full border border-border/80 bg-background px-3 text-xs shadow-[0_4px_20px_rgba(0,0,0,0.12)] backdrop-blur-sm hover:bg-muted"
            onClick={() => scrollToBottom("smooth")}
            title="回到底部"
          >
            <ArrowDown className="h-3.5 w-3.5" />
            <span>{hasNewContent ? "新内容" : "回到底部"}</span>
          </Button>
        </div>
      )}
    </div>
  );
}

interface ChatAreaListProps {
  items: ChatItem[];
  actions: ChatAreaActions;
  sessionId?: string;
  layout?: ChatAreaLayout;
  isRunning?: boolean;
}

/**
 * ChatArea.List - 消息列表组件（虚拟滚动）
 */
function ChatAreaList({
  items,
  actions,
  sessionId,
  layout = "default",
  isRunning = false,
}: ChatAreaListProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: items.length,
    getScrollElement: () =>
      wrapperRef.current?.closest('[data-testid="chat-scroll-container"]') ??
      null,
    estimateSize: () => 160,
    measureElement:
      typeof window !== "undefined" && "ResizeObserver" in window
        ? (element) => element.getBoundingClientRect().height
        : undefined,
    overscan: 4,
  });

  return (
    <div
      ref={wrapperRef}
      style={{
        height: `${rowVirtualizer.getTotalSize()}px`,
        width: "100%",
        position: "relative",
      }}
    >
      {rowVirtualizer.getVirtualItems().map((virtualItem) => {
        const item = items[virtualItem.index];
        return (
          <div
            key={item.id}
            data-index={virtualItem.index}
            ref={rowVirtualizer.measureElement}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              width: "100%",
              transform: `translateY(${virtualItem.start}px)`,
              paddingBottom: layout === "default" ? "32px" : "20px",
            }}
          >
            {item.type === "message" ? (
              <MessageItem
                item={item}
                actions={actions}
                sessionId={sessionId}
                layout={layout}
                isRunning={isRunning}
              />
            ) : item.type === "ask_user" ? (
              <AskUserInlineCard
                request={item.request}
                status={item.status}
                onResponse={async (approved, value) => {
                  if (askUserBridge.resolve) {
                    return await askUserBridge.resolve(
                      item.id,
                      approved,
                      value,
                    );
                  }
                  return false;
                }}
              />
            ) : item.type === "capability_confirmation" ? (
              <CapabilityConfirmationCard
                tool_name={item.tool_name}
                arguments={item.arguments}
                prompt={item.prompt}
                subagent_name={item.subagent_name}
                status={item.status}
                onApprove={async (scope) => {
                  const { eventBus } = await import("@/lib/eventBus");
                  eventBus.emit("capability:approve", {
                    sessionId: item.session_id,
                    toolCallId: item.id,
                    scope,
                    patternKey: item.pattern_key,
                  });
                  return true;
                }}
                onReject={async (feedback) => {
                  const { eventBus } = await import("@/lib/eventBus");
                  eventBus.emit("capability:reject", {
                    sessionId: item.session_id,
                    toolCallId: item.id,
                    feedback,
                  });
                  return true;
                }}
              />
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

// 将子组件附加到根组件
export const ChatArea = Object.assign(ChatAreaRoot, {
  List: ChatAreaList,
});

export default ChatArea;
