/**
 * MessageLayout - 消息布局容器
 *
 * 处理消息的整体布局（头像位置、内容对齐等）
 */
import type { ReactNode } from "react";
import { useChatAreaContext } from "./context";

interface MessageLayoutProps {
  children: ReactNode;
}

export function MessageLayout({ children }: MessageLayoutProps) {
  const {
    meta: { layout = "default" },
  } = useChatAreaContext();
  const isCompactSurface = layout === "compact" || layout === "rail";

  return (
    <div
      className={`flex min-w-0 ${
        isCompactSurface ? "gap-2" : "gap-4"
      } flex-row`}
    >
      {children}
    </div>
  );
}
