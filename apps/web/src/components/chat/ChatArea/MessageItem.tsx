/**
 * MessageItem - 单条消息的完整渲染
 *
 * 使用 Compound Components 模式组合各个部分
 */
import * as React from "react";
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
            {isUser ? <UserMessageContent /> : <AiMessageContent />}
          </MessageContent>
          <MessageTimestamp />
        </MessageBody>
      </MessageLayout>
    </ChatAreaProvider>
  );
});
