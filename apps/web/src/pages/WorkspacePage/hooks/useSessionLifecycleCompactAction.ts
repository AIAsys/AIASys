import { useCallback } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { SessionStatusInfo } from "../types";
import type { SessionLifecycleActionContext } from "./sessionLifecycleManagerActionTypes";

export function useSessionLifecycleCompactAction({
  apiBaseUrl,
  userId,
  sessionId,
  isCompactingConversation,
  isRunning,
  refreshSessionStatus,
  clearCurrentConversationView,
  removeAskUserSession,
  showSuccess,
  showError,
  setSessionStatus,
  setExecutionRecordsSummary,
  setIsCompactingConversation,
}: Pick<
  SessionLifecycleActionContext,
  | "apiBaseUrl"
  | "userId"
  | "sessionId"
  | "isCompactingConversation"
  | "isRunning"
  | "refreshSessionStatus"
  | "clearCurrentConversationView"
  | "removeAskUserSession"
  | "showSuccess"
  | "showError"
  | "setSessionStatus"
  | "setExecutionRecordsSummary"
  | "setIsCompactingConversation"
>) {
  const handleCompactConversation = useCallback(
    async (instruction?: string) => {
      if (!sessionId || isCompactingConversation || isRunning) {
        return;
      }

      setIsCompactingConversation(true);
      try {
        const data = await apiRequest<{ session?: SessionStatusInfo }>(
          `${apiBaseUrl}${API_ENDPOINTS.SESSION_COMPACT(userId, sessionId)}`,
          {
            method: "POST",
            body: JSON.stringify({ instruction: instruction || "" }),
          },
        );
        if (data.session) {
          setSessionStatus(data.session);
          setExecutionRecordsSummary(data.session);
        }

        removeAskUserSession(sessionId);
        await clearCurrentConversationView();
        refreshSessionStatus();
        showSuccess("对话上下文已压缩");
      } catch (error) {
        console.error("Failed to compact conversation:", error);
        showError(
          error instanceof Error ? error.message : "压缩对话上下文失败",
        );
      } finally {
        setIsCompactingConversation(false);
      }
    },
    [
      apiBaseUrl,
      clearCurrentConversationView,
      isCompactingConversation,
      isRunning,
      refreshSessionStatus,
      removeAskUserSession,
      sessionId,
      setExecutionRecordsSummary,
      setIsCompactingConversation,
      setSessionStatus,
      showError,
      showSuccess,
      userId,
    ],
  );

  return { handleCompactConversation };
}
