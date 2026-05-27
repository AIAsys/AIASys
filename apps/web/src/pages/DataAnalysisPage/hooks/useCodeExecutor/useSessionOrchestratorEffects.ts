import { useEffect, useRef, type RefObject } from "react";

interface UseSessionBootstrapEffectsProps {
  initialSessionId?: string | null;
  initialSessionIdRef: RefObject<string | null>;
  pendingRestoreSessionIdRef: RefObject<string | null>;
  hasLoadedHistoryRef: RefObject<boolean>;
  loadConversations: () => Promise<void>;
  selectSession: (sessionId: string) => Promise<unknown>;
}

interface UseSessionPrewarmEffectProps {
  sessionId: string;
  chatItemsLength: number;
  pendingRestoreSessionIdRef: RefObject<string | null>;
  setIsPrewarming: (value: boolean) => void;
}

export function useSessionBootstrapEffects({
  initialSessionId,
  initialSessionIdRef,
  pendingRestoreSessionIdRef,
  hasLoadedHistoryRef,
  loadConversations,
  selectSession,
}: UseSessionBootstrapEffectsProps) {
  const latestSelectSessionRef = useRef(selectSession);

  useEffect(() => {
    latestSelectSessionRef.current = selectSession;
  }, [selectSession]);

  useEffect(() => {
    if (!hasLoadedHistoryRef.current) {
      hasLoadedHistoryRef.current = true;
      void loadConversations();
    }
  }, [hasLoadedHistoryRef, loadConversations]);

  useEffect(() => {
    if (!initialSessionId || initialSessionId === initialSessionIdRef.current) {
      return;
    }

    initialSessionIdRef.current = initialSessionId;
    pendingRestoreSessionIdRef.current = initialSessionId;
    void latestSelectSessionRef.current(initialSessionId);
  }, [
    initialSessionId,
    initialSessionIdRef,
    pendingRestoreSessionIdRef,
  ]);
}

export function useSessionPrewarmEffect({
  sessionId,
  chatItemsLength,
  pendingRestoreSessionIdRef,
  setIsPrewarming,
}: UseSessionPrewarmEffectProps) {
  useEffect(() => {
    if (!sessionId) {
      return;
    }

    const isRestoringHistory = pendingRestoreSessionIdRef.current === sessionId;
    const hasConversation = chatItemsLength > 0;

    // 当前主线只支持本地执行，不再预热独立运行环境。
    // 这里仅负责确保 UI 不会停留在旧的预热态。
    if (!isRestoringHistory && !hasConversation) {
      setIsPrewarming(false);
      return;
    }

    setIsPrewarming(false);
  }, [
    chatItemsLength,
    pendingRestoreSessionIdRef,
    sessionId,
    setIsPrewarming,
  ]);
}
