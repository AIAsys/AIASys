/**
 * MessageItem - 单条消息的完整渲染
 *
 * 使用 Compound Components 模式组合各个部分
 */
import * as React from "react";
import { ChevronDown, ChevronUp, FileText } from "lucide-react";
import type { ChatItem } from "@/pages/WorkspacePage/types";
import { ChatAreaProvider } from "./ChatAreaProvider";
import type { ChatAreaActions } from "./context";
import { MessageLayout } from "./MessageLayout";
import { MessageAvatar } from "./MessageAvatar";
import { MessageBody } from "./MessageBody";
import { MessageContent } from "./MessageContent";
import { UserMessageContent } from "./UserMessageContent";
import { AiMessageContent } from "./AiMessageContent";
import { MessageTimestamp } from "./MessageTimestamp";
import type { ChatAreaLayout } from "./context";

function CompactionSummaryContent({ content }: { content: string }) {
  const [isOpen, setIsOpen] = React.useState(false);
  return (
    <div className="w-full rounded-lg border border-dashed border-border bg-muted/30 px-3 py-2 text-sm text-muted-foreground">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between gap-2 hover:text-foreground"
      >
        <span className="flex items-center gap-2">
          <FileText className="h-4 w-4" />
          上下文已压缩为摘要
        </span>
        {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {isOpen && (
        <div className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap border-t border-border pt-2 text-xs">
          {content}
        </div>
      )}
    </div>
  );
}

interface MessageItemProps {
  item: ChatItem;
  actions: ChatAreaActions;
  sessionId?: string;
  layout?: ChatAreaLayout;
  isRunning?: boolean;
}

export const MessageItem = React.memo(function MessageItem({
  item,
  actions,
  sessionId,
  layout = "default",
  isRunning = false,
}: MessageItemProps) {
  // MessageItem 只在 ChatAreaList 中对 type="message" 的项调用
  const msgItem = item as import("@/pages/WorkspacePage/types").MessageChatItem;
  const isUser = msgItem.sender === "user" || msgItem.role === "user";
  const isCompactionSummary = msgItem.segments?.some(
    (seg) => seg.type === "compaction_summary",
  );

  return (
    <ChatAreaProvider
      item={msgItem}
      isUser={isUser}
      actions={actions}
      meta={{ attachments: msgItem.attachments, sessionId, layout, isRunning }}
    >
      <MessageLayout>
        <MessageAvatar />
        <MessageBody>
          <MessageContent>
            {isCompactionSummary ? (
              <CompactionSummaryContent content={msgItem.content || ""} />
            ) : isUser ? (
              <UserMessageContent />
            ) : (
              <AiMessageContent />
            )}
          </MessageContent>
          <MessageTimestamp />
        </MessageBody>
      </MessageLayout>
    </ChatAreaProvider>
  );
});
