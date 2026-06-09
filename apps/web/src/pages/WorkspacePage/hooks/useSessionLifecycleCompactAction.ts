import { useCallback } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { SessionStatusInfo } from "../types";
import type { SessionLifecycleActionContext } from "./sessionLifecycleManagerActionTypes";

interface CompactionEvent {
  tier_used: "tool_clear" | "llm_summary" | "none";
  compacted_count: number;
  preserved_count: number;
  tokens_before: number;
  tokens_after: number;
  saved_tokens: number;
  saved_chars?: number;
  summary_tokens?: number;
  elapsed_ms: number;
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function buildCompactionToast(compaction: CompactionEvent): string {
  if (compaction.tier_used === "tool_clear") {
    return `已清理 ${compaction.compacted_count} 条旧 tool 结果，节省约 ${formatTokens(compaction.saved_tokens)} tokens`;
  }
  if (compaction.tier_used === "llm_summary") {
    return `已压缩 ${compaction.compacted_count} 条消息，上下文从 ${formatTokens(compaction.tokens_before)} 降至 ${formatTokens(compaction.tokens_after)} tokens`;
  }
  return "对话上下文已压缩";
}

export function useSessionLifecycleCompactAction({
  apiBaseUrl,
  userId,
  sessionId,
  isCompactingConversation,
  isRunning,
  refreshSessionStatus,
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
        const data = await apiRequest<{
          session?: SessionStatusInfo;
          compaction?: CompactionEvent;
        }>(
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
        // 不再清空视图——后端已自动插入压缩提示系统消息
        refreshSessionStatus();
        showSuccess(
          data.compaction
            ? buildCompactionToast(data.compaction)
            : "对话上下文已压缩",
        );
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
