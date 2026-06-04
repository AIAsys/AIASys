import type {
  SessionConversationArchiveBatch,
  SessionExecutionMaintenanceMarker,
  SessionExecutionRecord,
  SessionHistoryMessage,
  SessionRecordsDialogTab,
  SessionStatusInfo,
} from "../../types";

export type ExecutionRecordSegment = {
  id: string;
  isCurrent: boolean;
  marker?: SessionExecutionMaintenanceMarker;
  records: SessionExecutionRecord[];
};

export type ConversationHistoryBatch = {
  id: string;
  isCurrent: boolean;
  occurredAt?: string | null;
  label: string;
  description: string;
  messages: SessionHistoryMessage[];
};

export interface SessionLifecycleDialogsProps {
  isExecutionRecordsDialogOpen: boolean;
  onExecutionRecordsDialogOpenChange: (open: boolean) => void;
  recordsDialogTab: SessionRecordsDialogTab;
  onRecordsDialogTabChange: (tab: SessionRecordsDialogTab) => void;
  highlightedExecutionSequence: number | null;
  isLoadingExecutionRecords: boolean;
  conversationHistoryMessages: SessionHistoryMessage[];
  conversationHistoryArchivedBatches: SessionConversationArchiveBatch[];
  executionRecords: SessionExecutionRecord[];
  executionMaintenanceMarkers: SessionExecutionMaintenanceMarker[];
  executionRecordsSummary: SessionStatusInfo | null;
  effectiveSessionStatus: SessionStatusInfo | null;
}
