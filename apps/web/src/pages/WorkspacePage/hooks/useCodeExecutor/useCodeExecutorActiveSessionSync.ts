import { useCallback, useEffect, useRef } from "react";
import type { TaskEvent } from "@/types/task";
import type { ChatItem } from "../../types";

interface UseCodeExecutorActiveSessionSyncProps {
  sessionId: string;
  setActiveStreamSession: (sessionId: string) => void;
  setChatActiveSessionId: (sessionId: string) => void;
  setMultiTaskActiveSessionId: (sessionId: string) => void;
  setUploadActiveSessionId: (sessionId: string) => void;
  setChatItems: (
    items: ChatItem[] | ((prev: ChatItem[]) => ChatItem[]),
  ) => void;
  updateSessionChatItems: (
    sessionId: string,
    updater: (prev: ChatItem[]) => ChatItem[],
  ) => void;
  addStreamEventsDirect: (
    taskId: string,
    events: TaskEvent[],
    label?: string,
  ) => void;
  addStreamEventsForSession: (
    sessionId: string,
    taskId: string,
    events: TaskEvent[],
    label?: string,
  ) => void;
  /** chatState 的 activeSessionIdRef，用于避免 session 切换时的竞态 */
  chatActiveSessionIdRef: React.RefObject<string>;
}

export function useCodeExecutorActiveSessionSync({
  sessionId,
  setActiveStreamSession,
  setChatActiveSessionId,
  setMultiTaskActiveSessionId,
  setUploadActiveSessionId,
  setChatItems,
  updateSessionChatItems,
  addStreamEventsDirect,
  addStreamEventsForSession,
  chatActiveSessionIdRef,
}: UseCodeExecutorActiveSessionSyncProps) {
  const activeSessionIdRef = useRef<string>(sessionId || "");

  useEffect(() => {
    const currentSessionId = sessionId || "";
    activeSessionIdRef.current = currentSessionId;
    setChatActiveSessionId(currentSessionId);
    setMultiTaskActiveSessionId(currentSessionId);
    setUploadActiveSessionId(currentSessionId);

    if (currentSessionId) {
      setActiveStreamSession(currentSessionId);
    }
  }, [
    sessionId,
    setActiveStreamSession,
    setChatActiveSessionId,
    setMultiTaskActiveSessionId,
    setUploadActiveSessionId,
  ]);

  /**
   * 使用 chatState 的 activeSessionIdRef 判断活跃 session，
   * 避免与 useCodeExecutorActiveSessionSync 自己的 ref 不同步导致的竞态。
   * chatState 的 ref 在 switchChatSession 中同步更新，没有渲染延迟。
   */
  const updateChatItemsForSession = useCallback(
    (targetSessionId: string, updater: (prev: ChatItem[]) => ChatItem[]) => {
      if (targetSessionId === chatActiveSessionIdRef.current) {
        setChatItems(updater);
        return;
      }
      updateSessionChatItems(targetSessionId, updater);
    },
    [setChatItems, updateSessionChatItems, chatActiveSessionIdRef],
  );

  const addStreamEventsForSessionWrapped = useCallback(
    (
      targetSessionId: string,
      taskId: string,
      events: TaskEvent[],
      label?: string,
    ) => {
      if (targetSessionId === chatActiveSessionIdRef.current) {
        addStreamEventsDirect(taskId, events, label);
        return;
      }
      addStreamEventsForSession(targetSessionId, taskId, events, label);
    },
    [addStreamEventsDirect, addStreamEventsForSession, chatActiveSessionIdRef],
  );

  return {
    activeSessionIdRef,
    updateChatItemsForSession,
    addStreamEventsForSessionWrapped,
  };
}
