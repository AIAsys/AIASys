/**
 * AiMessageContent - AI 消息内容
 *
 * 专门处理 AI 消息的渲染，包括 AiMessageContent 组件和执行空间按钮
 */
import { Suspense, lazy } from "react";
import { useChatAreaContext } from "./context";
import { TerminalIcon } from "./chatAreaIcons";

const LazyAiMessageContentComponent = lazy(() =>
  import("../AiMessageContent/index").then((module) => ({
    default: module.AiMessageContent,
  })),
);

export function AiMessageContent() {
  const {
    state: { item },
    actions,
    meta,
  } = useChatAreaContext();
  // AiMessageContent 只在 MessageItem 内部使用，item 一定是 MessageChatItem
  const msgItem = item as import("@/pages/WorkspacePage/types").MessageChatItem;

  // 确保 content 是字符串
  const contentStr =
    typeof msgItem.content === "string"
      ? msgItem.content
      : String(msgItem.content ?? "");

  return (
    <div className="w-full min-w-0 overflow-hidden rounded-xl border border-border bg-background p-2 shadow-sm">
      <Suspense
        fallback={
          <div className="space-y-2 rounded-lg bg-muted/20 px-3 py-3">
            <div className="h-4 w-40 animate-pulse rounded bg-muted" />
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
            <div className="h-4 w-3/4 animate-pulse rounded bg-muted" />
          </div>
        }
      >
        <LazyAiMessageContentComponent
          content={contentStr}
          segments={msgItem.segments}
          isStreaming={msgItem.isStreaming || false}
          isStopped={msgItem.isStopped || false}
          workerRecords={msgItem.workerRecords}
          onWorkerClick={actions.onWorkerClick}
          onOpenWorkspaceArtifact={actions.onOpenWorkspaceArtifact}
          onViewToolDetails={actions.onViewToolDetails}
          sessionId={meta.sessionId}
          taskId={msgItem.taskId}
          showToolOutputs={true}
        />
      </Suspense>
      {msgItem.taskId && (
        <div className="mt-2 pt-2 border-t border-border flex justify-end">
          <button
            onClick={() => actions.onViewExecutionSpace?.(msgItem.taskId!)}
            className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground hover:text-foreground/80 bg-muted px-2 py-1 rounded transition-colors"
          >
            <TerminalIcon className="h-3 w-3" />
            查看执行记录
          </button>
        </div>
      )}
    </div>
  );
}
