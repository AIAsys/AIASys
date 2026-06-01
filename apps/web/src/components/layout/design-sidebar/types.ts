import type { TaskWorkspaceSummary } from "@/pages/DataAnalysisPage/types";
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
  workspaces?: TaskWorkspaceSummary[];
  currentWorkspaceId?: string;
  isLoadingHistory?: boolean;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onDeleteWorkspace?: (workspaceId: string) => void | Promise<void>;
  onDeleteAllWorkspaces?: () => void;
  onDeleteSelectedWorkspaces?: (ids: string[]) => void;
  onExportWorkspace?: (workspaceId: string) => void | Promise<void>;
  onImportWorkspace?: () => void | Promise<void>;
}
