import { useCallback } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  SessionConversationArchiveBatch,
  SessionExecutionMaintenanceMarker,
  SessionExecutionRecord,
  SessionHistoryMessage,
  SessionRecordsDialogTab,
  SessionStatusInfo,
} from "../types";
import type {
  SessionLifecycleActionContext,
} from "./sessionLifecycleManagerActionTypes";

export function useSessionLifecycleExecutionActions({
  apiBaseUrl,
  userId,
  sessionId,
  showError,
  setExecutionRecordsSummary,
  setExecutionRecords,
  setExecutionMaintenanceMarkers,
  setConversationHistoryMessages,
  setConversationHistoryArchivedBatches,
  setIsExecutionRecordsDialogOpen,
  setRecordsDialogTab,
  setHighlightedExecutionSequence,
  setIsLoadingExecutionRecords,
}: Pick<
  SessionLifecycleActionContext,
  | "apiBaseUrl"
  | "userId"
  | "sessionId"
  | "showError"
  | "setExecutionRecordsSummary"
  | "setExecutionRecords"
  | "setExecutionMaintenanceMarkers"
  | "setConversationHistoryMessages"
  | "setConversationHistoryArchivedBatches"
  | "setIsExecutionRecordsDialogOpen"
  | "setRecordsDialogTab"
  | "setHighlightedExecutionSequence"
  | "setIsLoadingExecutionRecords"
>) {
  const loadExecutionRecords = useCallback(async (options?: {
    manageLoading?: boolean;
  }) => {
    if (!sessionId) {
      return null;
    }

    if (options?.manageLoading ?? true) {
      setIsLoadingExecutionRecords(true);
    }
    try {
      const data = await apiRequest<{
        records?: SessionExecutionRecord[];
        summary?: SessionStatusInfo;
        maintenance_markers?: SessionExecutionMaintenanceMarker[];
      }>(
        `${apiBaseUrl}${API_ENDPOINTS.SESSION_EXECUTION_RECORDS(
          userId,
          sessionId,
        )}?limit=50`,
      );

      const nextRecords = data.records || [];
      const nextMarkers = data.maintenance_markers || [];
      setExecutionRecords(nextRecords);
      setExecutionMaintenanceMarkers(nextMarkers);
      const nextSummary = {
        session_id: sessionId,
        execution_record_count: data.summary?.execution_record_count,
        recovery_policy: data.summary?.recovery_policy,
        last_execution_status: data.summary?.last_execution_status,
        last_runtime_state: data.summary?.last_runtime_state,
        rebuild_status: data.summary?.rebuild_status,
        last_replay_run_id: data.summary?.last_replay_run_id,
        last_replayed_sequences: data.summary?.last_replayed_sequences,
        last_remaining_sequences: data.summary?.last_remaining_sequences,
        last_failed_sequence: data.summary?.last_failed_sequence,
      } as SessionStatusInfo;
      setExecutionRecordsSummary((prev) => ({
        ...(prev || {}),
        ...nextSummary,
      }));
      return {
        records: nextRecords,
        summary: nextSummary,
      };
    } catch (error) {
      console.error("Failed to load execution records:", error);
      setExecutionRecords([]);
      setExecutionMaintenanceMarkers([]);
      return null;
    } finally {
      if (options?.manageLoading ?? true) {
        setIsLoadingExecutionRecords(false);
      }
    }
  }, [
    apiBaseUrl,
    sessionId,
    setExecutionRecords,
    setExecutionMaintenanceMarkers,
    setExecutionRecordsSummary,
    setIsLoadingExecutionRecords,
    userId,
  ]);

  const loadConversationHistory = useCallback(async () => {
    if (!sessionId) {
      return null;
    }

    try {
      const data = await apiRequest<{
        current_messages?: SessionHistoryMessage[];
        archived_batches?: SessionConversationArchiveBatch[];
      }>(
        `${apiBaseUrl}${API_ENDPOINTS.SESSION_HISTORY(userId, sessionId)}`,
      );

      const nextCurrentMessages = data.current_messages || [];
      const nextArchivedBatches = data.archived_batches || [];
      setConversationHistoryMessages(nextCurrentMessages);
      setConversationHistoryArchivedBatches(nextArchivedBatches);

      return {
        currentMessages: nextCurrentMessages,
        archivedBatches: nextArchivedBatches,
      };
    } catch (error) {
      console.error("Failed to load conversation history:", error);
      setConversationHistoryMessages([]);
      setConversationHistoryArchivedBatches([]);
      return null;
    }
  }, [
    apiBaseUrl,
    sessionId,
    setConversationHistoryArchivedBatches,
    setConversationHistoryMessages,
    userId,
  ]);

  const handleViewExecutionRecords = useCallback(
    async (options?: {
      highlightSequence?: number | null;
      initialTab?: SessionRecordsDialogTab;
    }) => {
      setIsLoadingExecutionRecords(true);
      const [executionLoaded, conversationLoaded] = await Promise.all([
        loadExecutionRecords({ manageLoading: false }),
        loadConversationHistory(),
      ]);
      setIsLoadingExecutionRecords(false);

      if (!executionLoaded || !conversationLoaded) {
        showError("记录加载失败");
        return;
      }

      setRecordsDialogTab(
        options?.initialTab ||
          (options?.highlightSequence != null ? "execution" : "conversation"),
      );
      setHighlightedExecutionSequence(options?.highlightSequence ?? null);
      setIsExecutionRecordsDialogOpen(true);
    },
    [
      loadConversationHistory,
      loadExecutionRecords,
      setIsLoadingExecutionRecords,
      setRecordsDialogTab,
      setHighlightedExecutionSequence,
      setIsExecutionRecordsDialogOpen,
      showError,
    ],
  );

  return {
    handleViewExecutionRecords,
  };
}
