/**
 * ChatArea Provider - 状态管理解耦
 *
 * 将状态提升到 Provider，使子组件可以通过 Context 访问
 */
import type { ReactNode } from "react";
import {
  ChatAreaContext,
  type ChatAreaActions,
  type ChatAreaMeta,
} from "./context";
import type { ChatItem } from "@/pages/DataAnalysisPage/types";

interface ChatAreaProviderProps {
  children: ReactNode;
  item: ChatItem;
  isUser: boolean;
  actions: ChatAreaActions;
  meta?: ChatAreaMeta;
}

export function ChatAreaProvider({
  children,
  item,
  isUser,
  actions,
  meta = {},
}: ChatAreaProviderProps) {
  const value = {
    state: { item, isUser },
    actions,
    meta,
  };

  return <ChatAreaContext value={value}>{children}</ChatAreaContext>;
}
