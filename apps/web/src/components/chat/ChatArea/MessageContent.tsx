/**
 * MessageContent - 消息内容包装组件
 *
 * 提供基础的内容容器样式
 */
import type { ReactNode } from "react";
import { useChatAreaContext } from "./context";

interface MessageContentProps {
  children: ReactNode;
}

export function MessageContent({ children }: MessageContentProps) {
  const {
    state: { isUser },
    meta: { layout = "default" },
  } = useChatAreaContext();
  const userContentClass =
    layout === "rail"
      ? "inline-block max-w-full whitespace-pre-wrap break-words rounded-2xl bg-muted px-3 py-2.5 text-sm text-foreground [overflow-wrap:anywhere]"
      : layout === "compact"
        ? "min-w-0 whitespace-pre-wrap break-words rounded-2xl bg-muted px-3 py-2.5 text-[15px] text-foreground [overflow-wrap:anywhere]"
        : "min-w-0 whitespace-pre-wrap break-words rounded-2xl bg-muted p-4 text-base text-foreground [overflow-wrap:anywhere]";

  return (
    <div className={isUser ? userContentClass : "w-full min-w-0"}>
      {children}
    </div>
  );
}
