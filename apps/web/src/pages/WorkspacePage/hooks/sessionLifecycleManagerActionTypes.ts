import type { Dispatch, SetStateAction } from "react";
import type {
  SessionConversationArchiveBatch,
  SessionExecutionMaintenanceMarker,
  SessionExecutionRecord,
  SessionHistoryMessage,
  SessionRecordsDialogTab,
  SessionStatusInfo,
} from "../types";

export interface SessionConversationMutationResponse {
  session?: SessionStatusInfo;
}

export interface SessionLifecycleActionStateSetters {
  setExportingSessionId: Dispatch<SetStateAction<string | null>>;
  setSessionStatus: Dispatch<SetStateAction<SessionStatusInfo | null>>;
  setExecutionRecordsSummary: Dispatch<
    SetStateAction<SessionStatusInfo | null>
  >;
  setExecutionRecords: Dispatch<SetStateAction<SessionExecutionRecord[]>>;
  setExecutionMaintenanceMarkers: Dispatch<
    SetStateAction<SessionExecutionMaintenanceMarker[]>
  >;
  setConversationHistoryMessages: Dispatch<
    SetStateAction<SessionHistoryMessage[]>
  >;
  setConversationHistoryArchivedBatches: Dispatch<
    SetStateAction<SessionConversationArchiveBatch[]>
  >;
  setIsCompactingConversation: Dispatch<SetStateAction<boolean>>;
  setIsExecutionRecordsDialogOpen: Dispatch<SetStateAction<boolean>>;
  setRecordsDialogTab: Dispatch<SetStateAction<SessionRecordsDialogTab>>;
  setHighlightedExecutionSequence: Dispatch<SetStateAction<number | null>>;
  setIsLoadingExecutionRecords: Dispatch<SetStateAction<boolean>>;
}

export interface SessionLifecycleActionContext
  extends SessionLifecycleActionStateSetters {
  apiBaseUrl: string;
  userId: string;
  sessionId?: string;
  exportingSessionId: string | null;
  isCompactingConversation: boolean;
  isRunning: boolean;
  refreshExecutionHistory: () => Promise<void>;
  refreshSessionStatus: () => void;
  /** 后端 clear/compact 成功后，清空当前会话的前台对话视图。 */
  clearCurrentConversationView: () => Promise<void>;
  refreshWorkspaceList?: () => Promise<unknown>;
  refreshSessionMcpServers?: () => Promise<void>;
  removeAskUserSession: (sessionId: string) => void;
  showSuccess: (message: string) => void;
  showError: (message: string) => void;
}
