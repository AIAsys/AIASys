import type { AskUserRequest } from "@/types/askUser";
import type { SessionExportScope } from "@/types/sessionExport";
import type {
  SessionConversationArchiveBatch,
  SessionExecutionMaintenanceMarker,
  SessionExecutionRecord,
  SessionHistoryMessage,
  SessionRecordsDialogTab,
  SessionStatusInfo,
} from "../types";

export interface UseSessionLifecycleManagerParams {
  apiBaseUrl: string;
  userId: string;
  sessionId?: string;
  statusQueryEnabled?: boolean;
  isRunning: boolean;
  refreshExecutionHistory: () => Promise<void>;
  clearCurrentConversationView: () => Promise<void>;
  refreshWorkspaceList?: () => Promise<unknown>;
  refreshSessionMcpServers?: () => Promise<void>;
  removeAskUserSession: (sessionId: string) => void;
  setAskUserActiveSessionId: (sessionId: string) => void;
  showAskUser: (request: AskUserRequest, sessionId: string) => void;
}

export type LifecycleToast = {
  id: string;
  message: string;
  type: "success" | "error";
};

export interface UseSessionLifecycleManagerReturn {
  toasts: LifecycleToast[];
  sessionStatus: SessionStatusInfo | null;
  effectiveSessionStatus: SessionStatusInfo | null;
  refreshSessionStatus: () => void;
  exportingSessionId: string | null;
  handleExportSession: (
    targetSessionId: string,
    scope: SessionExportScope,
  ) => Promise<void>;
  isCompactingConversation: boolean;
  handleCompactConversation: (instruction?: string) => Promise<void>;
  isExecutionRecordsDialogOpen: boolean;
  setIsExecutionRecordsDialogOpen: (open: boolean) => void;
  recordsDialogTab: SessionRecordsDialogTab;
  setRecordsDialogTab: (tab: SessionRecordsDialogTab) => void;
  highlightedExecutionSequence: number | null;
  isLoadingExecutionRecords: boolean;
  conversationHistoryMessages: SessionHistoryMessage[];
  conversationHistoryArchivedBatches: SessionConversationArchiveBatch[];
  executionRecords: SessionExecutionRecord[];
  executionMaintenanceMarkers: SessionExecutionMaintenanceMarker[];
  executionRecordsSummary: SessionStatusInfo | null;
  handleViewExecutionRecords: (options?: {
    highlightSequence?: number | null;
    initialTab?: SessionRecordsDialogTab;
  }) => Promise<void>;
}
