/**
 * MessageAvatar - 消息头像组件
 *
 * 独立的子组件，通过 Context 获取状态
 */
import { Bot, User } from "lucide-react";
import { useChatAreaContext } from "./context";

export function MessageAvatar() {
  const {
    state: { isUser },
    meta: { layout = "default" },
  } = useChatAreaContext();

  if (layout === "compact") {
    return null;
  }
  const isRail = layout === "rail";
  const iconSize = isRail ? 15 : 18;

  return (
    <div
      className={`flex items-center justify-center rounded-full shadow-sm ${
        isRail ? "h-7 w-7" : "h-8 w-8"
      } flex-shrink-0 ${
        isUser
          ? isRail
            ? "border border-tertiary/20 bg-tertiary text-tertiary-foreground"
            : "bg-secondary border border-border"
          : "bg-muted border border-border"
      }`}
    >
      {isUser ? (
        <User
          size={iconSize}
          className={isRail ? "text-tertiary-foreground" : "text-foreground"}
        />
      ) : (
        <Bot size={iconSize} className="text-foreground" />
      )}
    </div>
  );
}
