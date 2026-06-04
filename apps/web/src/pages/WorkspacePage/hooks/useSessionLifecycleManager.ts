import { useCallback, useRef, useState } from "react";
import { useFileUploadToast } from "@/components/file/FileUploadToast";
import type {
  SessionConversationArchiveBatch,
  SessionExecutionMaintenanceMarker,
  SessionExecutionRecord,
  SessionHistoryMessage,
  SessionRecordsDialogTab,
  SessionStatusInfo,
} from "../types";
import type {
  UseSessionLifecycleManagerParams,
  UseSessionLifecycleManagerReturn,
} from "./sessionLifecycleManagerTypes";
import { mergeEffectiveSessionStatus } from "./sessionLifecycleManagerUtils";
import {
  useAskUserSessionSync,
  usePendingAskUserRestore,
  useSessionStatusLoader,
  useSessionStatusRefreshOnRunComplete,
} from "./useSessionLifecycleManagerEffects";
import { useSessionLifecycleManagerActions } from "./useSessionLifecycleManagerActions";

export type { UseSessionLifecycleManagerReturn } from "./sessionLifecycleManagerTypes";

export function useSessionLifecycleManager({
  apiBaseUrl,
  userId,
  sessionId,
  statusQueryEnabled = true,
  isRunning,
  refreshExecutionHistory,
  clearCurrentConversationView,
  refreshWorkspaceList,
  refreshSessionMcpServers,
  removeAskUserSession,
  setAskUserActiveSessionId,
  showAskUser,
}: UseSessionLifecycleManagerParams): UseSessionLifecycleManagerReturn {
  const {
    toasts,
    showSuccess: showSessionExportSuccess,
    showError: showSessionExportError,
  } = useFileUploadToast();
  const [exportingSessionId, setExportingSessionId] = useState<string | null>(
    null,
  );
  const [sessionStatus, setSessionStatus] = useState<SessionStatusInfo | null>(
    null,
  );
  const [sessionStatusRefreshKey, setSessionStatusRefreshKey] = useState(0);
  const sessionStatusRequestIdRef = useRef(0);
  const [isCompactingConversation, setIsCompactingConversation] = useState(false);
  const [isExecutionRecordsDialogOpen, setIsExecutionRecordsDialogOpen] =
    useState(false);
  const [recordsDialogTab, setRecordsDialogTab] =
    useState<SessionRecordsDialogTab>("conversation");
  const [highlightedExecutionSequence, setHighlightedExecutionSequence] =
    useState<number | null>(null);
  const [isLoadingExecutionRecords, setIsLoadingExecutionRecords] =
    useState(false);
  const [conversationHistoryMessages, setConversationHistoryMessages] =
    useState<SessionHistoryMessage[]>([]);
  const [
    conversationHistoryArchivedBatches,
    setConversationHistoryArchivedBatches,
  ] = useState<SessionConversationArchiveBatch[]>([]);
  const [executionRecords, setExecutionRecords] = useState<
    SessionExecutionRecord[]
  >([]);
  const [executionMaintenanceMarkers, setExecutionMaintenanceMarkers] =
    useState<SessionExecutionMaintenanceMarker[]>([]);
  const [executionRecordsSummary, setExecutionRecordsSummary] =
    useState<SessionStatusInfo | null>(null);
  const previousActiveSessionRunningRef = useRef(false);

  const handleExecutionRecordsDialogOpenChange = useCallback((open: boolean) => {
    setIsExecutionRecordsDialogOpen(open);
    if (!open) {
      setHighlightedExecutionSequence(null);
      setRecordsDialogTab("conversation");
    }
  }, []);

  const refreshSessionStatus = useCallback(() => {
    setSessionStatusRefreshKey((prev) => prev + 1);
  }, []);

  useSessionStatusLoader({
    apiBaseUrl,
    sessionId,
    enabled: statusQueryEnabled,
    refreshKey: sessionStatusRefreshKey,
    sessionStatusRequestIdRef,
    setSessionStatus,
  });

  useAskUserSessionSync({
    sessionId,
    setAskUserActiveSessionId,
  });

  useSessionStatusRefreshOnRunComplete({
    isRunning,
    sessionId,
    previousActiveSessionRunningRef,
    refreshSessionStatus,
  });

  usePendingAskUserRestore({
    apiBaseUrl,
    sessionId,
    enabled: statusQueryEnabled,
    showAskUser,
  });

  const effectiveSessionStatus: SessionStatusInfo | null = mergeEffectiveSessionStatus(
    sessionId,
    sessionStatus,
    executionRecordsSummary,
  );

  const {
    handleExportSession,
    handleCompactConversation,
    handleViewExecutionRecords,
  } = useSessionLifecycleManagerActions({
    apiBaseUrl,
    userId,
    sessionId,
    exportingSessionId,
    isCompactingConversation,
    isRunning,
    refreshExecutionHistory,
    refreshSessionStatus,
    clearCurrentConversationView,
    refreshWorkspaceList,
    refreshSessionMcpServers,
    removeAskUserSession,
    showSuccess: showSessionExportSuccess,
    showError: showSessionExportError,
    setExportingSessionId,
    setSessionStatus,
    setExecutionRecordsSummary,
    setExecutionRecords,
    setExecutionMaintenanceMarkers,
    setConversationHistoryMessages,
    setConversationHistoryArchivedBatches,
    setIsCompactingConversation,
    setIsExecutionRecordsDialogOpen,
    setRecordsDialogTab,
    setHighlightedExecutionSequence,
    setIsLoadingExecutionRecords,
  });

  return {
    toasts,
    sessionStatus,
    effectiveSessionStatus,
    refreshSessionStatus,
    exportingSessionId,
    handleExportSession,
    isCompactingConversation,
    handleCompactConversation,
    isExecutionRecordsDialogOpen,
    setIsExecutionRecordsDialogOpen: handleExecutionRecordsDialogOpenChange,
    recordsDialogTab,
    setRecordsDialogTab,
    highlightedExecutionSequence,
    isLoadingExecutionRecords,
    conversationHistoryMessages,
    conversationHistoryArchivedBatches,
    executionRecords,
    executionMaintenanceMarkers,
    executionRecordsSummary,
    handleViewExecutionRecords,
  };
}
