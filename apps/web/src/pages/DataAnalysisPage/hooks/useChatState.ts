import { useCallback, useRef, useState } from "react";
import type { ChatItem } from "../types";

interface UseChatStateReturn {
  chatItems: ChatItem[];
  setChatItems: React.Dispatch<React.SetStateAction<ChatItem[]>>;
  inputValue: string;
  setInputValue: React.Dispatch<React.SetStateAction<string>>;
  addUserMessage: (content: string, attachments?: string[]) => string;
  addAiMessage: (id: string, taskId?: string) => void;
  updateAiMessage: (id: string, content: string, isStreaming?: boolean) => void;
  clearChat: () => void;
  /** 切换 session：保存当前 session 到 Map，加载目标 session */
  switchSession: (fromId: string, toId: string) => void;
  /** 更新指定 session 的 chatItems（活跃 session 走 useState，后台 session 只更新 Map） */
  updateSessionChatItems: (
    sessionId: string,
    updater: (prev: ChatItem[]) => ChatItem[],
  ) => void;
  /** 初始化 session（在 Map 中分配空间） */
  initSession: (id: string) => void;
  /** 移除 session */
  removeSession: (id: string) => void;
  /** 设置活跃 session ID */
  setActiveSessionId: (id: string) => void;
  /** 读取指定 session 的已缓存聊天内容 */
  getSessionChatItems: (sessionId: string) => ChatItem[];
}

export function useChatState(): UseChatStateReturn {
  const [chatItemsState, setChatItemsState] = useState<ChatItem[]>([]);
  const [inputValue, setInputValue] = useState("");
  const pendingAiMsgRef = useRef<{ id: string; taskId?: string } | null>(null);

  // Per-session chat storage
  const chatMapRef = useRef<Map<string, ChatItem[]>>(new Map());
  const activeSessionIdRef = useRef<string>("");
  const chatItemsRef = useRef<ChatItem[]>([]);

  const setChatItems: React.Dispatch<React.SetStateAction<ChatItem[]>> =
    useCallback((value) => {
      const next =
        typeof value === "function"
          ? (value as (prev: ChatItem[]) => ChatItem[])(chatItemsRef.current)
          : value;
      chatItemsRef.current = next;
      setChatItemsState(next);
    }, []);

  const setActiveSessionId = useCallback((id: string) => {
    activeSessionIdRef.current = id;
  }, []);

  const initSession = useCallback((id: string) => {
    if (!chatMapRef.current.has(id)) {
      chatMapRef.current.set(id, []);
    }
  }, []);

  const removeSession = useCallback((id: string) => {
    chatMapRef.current.delete(id);
  }, []);

  const getSessionChatItems = useCallback((sessionId: string): ChatItem[] => {
    if (sessionId === activeSessionIdRef.current) {
      return chatItemsRef.current;
    }
    return chatMapRef.current.get(sessionId) || [];
  }, []);

  const switchSession = useCallback(
    (fromId: string, toId: string) => {
      if (fromId === toId) return;

      // 保存当前 session 的 chatItems 到 Map
      if (fromId) {
        chatMapRef.current.set(fromId, chatItemsRef.current);
      }

      // 从 Map 加载目标 session 的 chatItems
      const targetItems = chatMapRef.current.get(toId) || [];
      setChatItems(targetItems);
      activeSessionIdRef.current = toId;
    },
    [setChatItems],
  );

  const updateSessionChatItems = useCallback(
    (
      sessionId: string,
      updater: (prev: ChatItem[]) => ChatItem[],
    ) => {
      if (sessionId === activeSessionIdRef.current) {
        // 活跃 session：通过 React setState 驱动渲染
        setChatItems(updater);
      } else {
        // 后台 session：只更新 Map，不触发重渲染
        const current = chatMapRef.current.get(sessionId) || [];
        chatMapRef.current.set(sessionId, updater(current));
      }
    },
    [],
  );

  const addUserMessage = useCallback(
    (content: string, attachments?: string[]): string => {
      const id = `user-${Date.now()}`;
      setChatItems((prev) => [
        ...prev,
        {
          type: "message",
          id,
          sender: "user",
          content,
          timestamp: new Date(),
          isStreaming: false,
          attachments:
            attachments && attachments.length > 0 ? attachments : undefined,
        },
      ]);
      return id;
    },
    [],
  );

  const addAiMessage = useCallback(
    (id: string, taskId?: string): void => {
      pendingAiMsgRef.current = { id, taskId };
      setChatItems((prev) => {
        if (prev.some((item) => item.id === id)) {
          return prev;
        }
        return [
          ...prev,
          {
            type: "message" as const,
            id,
            sender: "ai" as const,
            content: "",
            segments: [],
            timestamp: new Date(),
            isStreaming: true,
            taskId,
          },
        ];
      });
    },
    [],
  );

  const updateAiMessage = useCallback(
    (id: string, content: string, isStreaming = true) => {
      setChatItems((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, content, isStreaming } : item,
        ),
      );
    },
    [],
  );

  const clearChat = useCallback(() => {
    setChatItems([]);
    setInputValue("");
    pendingAiMsgRef.current = null;
  }, []);

  return {
    chatItems: chatItemsState,
    setChatItems,
    inputValue,
    setInputValue,
    addUserMessage,
    addAiMessage,
    updateAiMessage,
    clearChat,
    switchSession,
    updateSessionChatItems,
    initSession,
    removeSession,
    setActiveSessionId,
    getSessionChatItems,
  };
}
