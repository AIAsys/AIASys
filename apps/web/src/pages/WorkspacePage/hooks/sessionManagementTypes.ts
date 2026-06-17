import type { ChatItem, Conversation } from "../types";

export interface UseSessionManagementProps {
  apiBaseUrl: string;
  initialSessionId?: string | null;
  onSessionSelect?: (sessionId: string, chatItems: ChatItem[]) => void;
}

export interface UseSessionManagementReturn {
  conversations: Conversation[];  // 替代 historySessions
  isLoadingHistory: boolean;
  isRestoringSession: boolean;
  historyLoadError: string | null;
  loadConversations: () => Promise<void>;  // 替代 loadHistorySessions
  handleSessionSelect: (sid: string) => Promise<ChatItem[]>;
  handleDeleteSession: (sid: string) => Promise<void>;
  addOptimisticSession: (sessionId: string, title?: string) => void;
  updateSessionTitle: (sessionId: string, title: string) => Promise<void>;
  loadMoreHistory: (sid: string) => Promise<ChatItem[] | null>;
  hasMoreHistory: (sid: string) => boolean;
}
