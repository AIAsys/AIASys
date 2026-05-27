import type { SessionExportScope } from "@/types/sessionExport";
import type { Conversation, TaskWorkspaceSummary } from "@/pages/DataAnalysisPage/types";
import type { SettingsSection } from "@/components/settings/global-settings";

export interface SidebarProps {
  className?: string;
  collapsed?: boolean;
  onClose?: () => void;
  onExpand?: () => void;
  onNewTask?: () => void;
  onUpdateWorkspace?: (
    workspaceId: string,
    patch: { title?: string; description?: string | null },
  ) => Promise<void> | void;
  onOpenGlobalSettings?: (section: SettingsSection) => void;
  onOpenChannel?: () => void;
  onOpenChannelSettings?: () => void;
  sessions?: Conversation[];
  workspaces?: TaskWorkspaceSummary[];
  currentWorkspaceId?: string;
  currentSessionId?: string;
  isLoadingHistory?: boolean;
  onSessionSelect?: (sessionId: string) => void;
  onDeleteSession?: (sessionId: string) => void;
  onForkConversation?: (sessionId: string) => void | Promise<void>;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onDeleteWorkspace?: (workspaceId: string) => void | Promise<void>;
  onDeleteAllWorkspaces?: () => void;
  onDeleteSelectedWorkspaces?: (ids: string[]) => void;
  onExportSession?: (
    sessionId: string,
    scope: SessionExportScope,
  ) => Promise<void> | void;
  exportingSessionId?: string | null;
}
