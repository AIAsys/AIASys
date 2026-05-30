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
}: UseCodeExecutorActiveSessionSyncProps) {
  const activeSessionIdRef = useRef<string>(sessionId || "");
  activeSessionIdRef.current = sessionId || "";

  useEffect(() => {
    const currentSessionId = sessionId || "";
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

  const updateChatItemsForSession = useCallback(
    (targetSessionId: string, updater: (prev: ChatItem[]) => ChatItem[]) => {
      if (targetSessionId === activeSessionIdRef.current) {
        setChatItems(updater);
        return;
      }
      updateSessionChatItems(targetSessionId, updater);
    },
    [setChatItems, updateSessionChatItems],
  );

  const addStreamEventsForSessionWrapped = useCallback(
    (
      targetSessionId: string,
      taskId: string,
      events: TaskEvent[],
      label?: string,
    ) => {
      if (targetSessionId === activeSessionIdRef.current) {
        addStreamEventsDirect(taskId, events, label);
        return;
      }
      addStreamEventsForSession(targetSessionId, taskId, events, label);
    },
    [addStreamEventsDirect, addStreamEventsForSession],
  );

  return {
    activeSessionIdRef,
    updateChatItemsForSession,
    addStreamEventsForSessionWrapped,
  };
}
