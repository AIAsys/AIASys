/**
 * MessageTimestamp - 消息时间戳组件
 */
import { useChatAreaContext } from "./context";

export function MessageTimestamp() {
  const {
    state: { item, isUser },
    meta: { layout = "default" },
  } = useChatAreaContext();

  return (
    <span
      className={`mt-1 text-muted-foreground ${
        layout === "compact" ? "px-0.5 text-[9px]" : "px-1 text-[10px]"
      } ${isUser ? "self-end" : "self-start"}`}
    >
      {new Date(item.timestamp).toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}
    </span>
  );
}
