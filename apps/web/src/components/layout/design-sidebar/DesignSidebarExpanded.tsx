import {
  PanelLeftClose,
  Plus,
  SatelliteDish,
  Upload,
  Settings,
} from "lucide-react";
import { BrandLockup } from "@/components/branding/BrandLogo";
import { DesignSidebarHistorySection } from "./DesignSidebarHistorySection";
import { DesignSidebarFooter } from "./DesignSidebarFooter";
import type { TaskWorkspaceSummary } from "@/pages/WorkspacePage/types";
import type { SettingsSection } from "@/components/settings/global-settings";

interface DesignSidebarExpandedProps {
  avatarChar: string;
  avatarColor: string;
  currentWorkspaceId?: string;
  displayName: string;
  filteredWorkspaces: TaskWorkspaceSummary[];
  isAuthenticated: boolean;
  isLoadingHistory: boolean;
  searchQuery: string;
  workspaces: TaskWorkspaceSummary[];
  onClose?: () => void;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onDeleteWorkspace?: (workspaceId: string) => void | Promise<void>;
  onDeleteAllWorkspaces?: () => void;
  onDeleteSelectedWorkspaces?: (ids: string[]) => void;
  onExportWorkspace?: (workspaceId: string) => void | Promise<void>;
  onImportWorkspace?: () => void | Promise<void>;
  onUpdateWorkspace?: (
    workspaceId: string,
    patch: { title?: string; description?: string | null },
  ) => Promise<void> | void;
  onEditProfile: () => void;
  onLogout: () => void;
  onNewTask?: () => void;
  onOpenGlobalSettings?: (section: SettingsSection) => void;
  onOpenChannel?: () => void;
  onOpenChannelSettings?: () => void;
  onSearchQueryChange: (value: string) => void;
  onClearSearch: () => void;
}

export function DesignSidebarExpanded({
  avatarChar,
  avatarColor,
  currentWorkspaceId,
  displayName,
  filteredWorkspaces,
  isAuthenticated,
  isLoadingHistory,
  searchQuery,
  workspaces,
  onClose,
  onWorkspaceSelect,
  onDeleteWorkspace,
  onDeleteAllWorkspaces,
  onDeleteSelectedWorkspaces,
  onExportWorkspace,
  onImportWorkspace,
  onUpdateWorkspace,
  onEditProfile,
  onLogout,
  onNewTask,
  onOpenGlobalSettings,
  onOpenChannel,
  onOpenChannelSettings,
  onSearchQueryChange,
  onClearSearch,
}: DesignSidebarExpandedProps) {
  return (
    <div className="flex flex-col h-full w-[220px] min-w-[220px] transition-opacity duration-200 delay-200 opacity-100">
      <div className="px-4 pt-6 pb-2">
        <div className="flex items-center justify-between mb-4">
          <div className="flex-shrink-0">
            <BrandLockup
              subtitle="任务工作区"
              className="gap-2"
              markClassName="h-8 w-8"
              titleClassName="text-[1rem]"
              href="/"
            />
          </div>
          <PanelLeftClose
            className="w-5 h-5 text-muted-foreground cursor-pointer hover:text-foreground flex-shrink-0"
            onClick={onClose}
          />
        </div>
      </div>

      <div className="px-3 mb-2">
        <button
          type="button"
          data-testid="sidebar-new-task-expanded"
          onClick={onNewTask}
          className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 font-medium text-sm transition-colors"
        >
          <Plus className="w-4 h-4" />
          新建工作区
        </button>
      </div>
      {onImportWorkspace ? (
        <div className="px-3 mb-2">
          <button
            type="button"
            data-testid="sidebar-import-workspace-expanded"
            onClick={onImportWorkspace}
            className="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background hover:bg-accent font-medium text-sm transition-colors text-foreground"
          >
            <Upload className="w-4 h-4 text-tertiary" />
            导入工作区
          </button>
        </div>
      ) : null}

      <div className="px-3 mb-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            data-testid="sidebar-open-claw-expanded"
            onClick={onOpenChannel}
            className="flex-1 flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-background hover:bg-accent font-medium text-sm transition-colors text-foreground"
          >
            <SatelliteDish className="w-4 h-4 text-tertiary" />
            频道
          </button>
          {onOpenChannelSettings ? (
            <button
              type="button"
              title="频道设置"
              onClick={onOpenChannelSettings}
              className="flex items-center justify-center w-9 h-9 rounded-lg border border-border bg-background hover:bg-accent text-muted-foreground hover:text-foreground transition-colors"
            >
              <Settings className="w-4 h-4 text-muted-foreground" />
            </button>
          ) : null}
        </div>
      </div>

      <DesignSidebarHistorySection
        workspaces={workspaces}
        filteredWorkspaces={filteredWorkspaces}
        currentWorkspaceId={currentWorkspaceId}
        isLoadingHistory={isLoadingHistory}
        searchQuery={searchQuery}
        onSearchQueryChange={onSearchQueryChange}
        onClearSearch={onClearSearch}
        onWorkspaceSelect={onWorkspaceSelect}
        onDeleteWorkspace={onDeleteWorkspace}
        onDeleteAllWorkspaces={onDeleteAllWorkspaces}
        onDeleteSelectedWorkspaces={onDeleteSelectedWorkspaces}
        onExportWorkspace={onExportWorkspace}
        onUpdateWorkspace={onUpdateWorkspace}
      />

      <DesignSidebarFooter
        avatarChar={avatarChar}
        avatarColor={avatarColor}
        displayName={displayName}
        isAuthenticated={isAuthenticated}
        onEditProfile={onEditProfile}
        onOpenGlobalSettings={onOpenGlobalSettings}
        onLogout={onLogout}
      />
    </div>
  );
}
