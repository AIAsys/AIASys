/**
 * MessageBody - 消息主体容器
 *
 * 处理消息内容的布局和对齐
 */
import type { ReactNode } from "react";
import { useChatAreaContext } from "./context";

interface MessageBodyProps {
  children: ReactNode;
}

export function MessageBody({ children }: MessageBodyProps) {
  const {
    meta: { layout = "default" },
  } = useChatAreaContext();
  const bodyClass =
    layout === "compact" || layout === "rail"
      ? "w-full items-start"
      : "w-full items-start";

  return (
    <div className={`flex min-w-0 flex-col ${bodyClass}`}>
      {children}
    </div>
  );
}
