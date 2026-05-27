import {
  PanelLeftClose,
  Plus,
  SatelliteDish,
  Settings,
} from "lucide-react";
import { BrandLockup } from "@/components/branding/BrandLogo";
import { DesignSidebarHistorySection } from "./DesignSidebarHistorySection";
import { DesignSidebarFooter } from "./DesignSidebarFooter";
import type {
  Conversation,
  TaskWorkspaceSummary,
} from "@/pages/DataAnalysisPage/types";
import type { SessionExportScope } from "@/types/sessionExport";
import type { SettingsSection } from "@/components/settings/global-settings";

interface DesignSidebarExpandedProps {
  avatarChar: string;
  avatarColor: string;
  currentSessionId?: string;
  currentWorkspaceId?: string;
  displayName: string;
  exportingSessionId?: string | null;
  filteredSessions: Conversation[];
  filteredWorkspaces: TaskWorkspaceSummary[];
  isAuthenticated: boolean;
  isLoadingHistory: boolean;
  searchQuery: string;
  sessions: Conversation[];
  workspaces: TaskWorkspaceSummary[];
  onClose?: () => void;
  onDeleteSession?: (sessionId: string) => void;
  onForkConversation?: (sessionId: string) => void | Promise<void>;
  onWorkspaceSelect?: (workspaceId: string) => void;
  onDeleteWorkspace?: (workspaceId: string) => void | Promise<void>;
  onDeleteAllWorkspaces?: () => void;
  onDeleteSelectedWorkspaces?: (ids: string[]) => void;
  onUpdateWorkspace?: (
    workspaceId: string,
    patch: { title?: string; description?: string | null },
  ) => Promise<void> | void;
  onExportSession?: (
    sessionId: string,
    scope: SessionExportScope,
  ) => Promise<void> | void;
  onEditProfile: () => void;
  onLogout: () => void;
  onNewTask?: () => void;
  onOpenGlobalSettings?: (section: SettingsSection) => void;
  onOpenChannel?: () => void;
  onOpenChannelSettings?: () => void;
  onSearchQueryChange: (value: string) => void;
  onSessionSelect?: (sessionId: string) => void;
  onClearSearch: () => void;
}

export function DesignSidebarExpanded({
  avatarChar,
  avatarColor,
  currentSessionId,
  currentWorkspaceId,
  displayName,
  exportingSessionId,
  filteredSessions,
  filteredWorkspaces,
  isAuthenticated,
  isLoadingHistory,
  searchQuery,
  sessions,
  workspaces,
  onClose,
  onDeleteSession,
  onForkConversation,
  onWorkspaceSelect,
  onDeleteWorkspace,
  onDeleteAllWorkspaces,
  onDeleteSelectedWorkspaces,
  onUpdateWorkspace,
  onExportSession,
  onEditProfile,
  onLogout,
  onNewTask,
  onOpenGlobalSettings,
  onOpenChannel,
  onOpenChannelSettings,
  onSearchQueryChange,
  onSessionSelect,
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
        sessions={sessions}
        workspaces={workspaces}
        filteredWorkspaces={filteredWorkspaces}
        currentWorkspaceId={currentWorkspaceId}
        filteredSessions={filteredSessions}
        currentSessionId={currentSessionId}
        isLoadingHistory={isLoadingHistory}
        searchQuery={searchQuery}
        onSearchQueryChange={onSearchQueryChange}
        onClearSearch={onClearSearch}
        onSessionSelect={onSessionSelect}
        onDeleteSession={onDeleteSession}
        onForkConversation={onForkConversation}
        onWorkspaceSelect={onWorkspaceSelect}
        onDeleteWorkspace={onDeleteWorkspace}
        onDeleteAllWorkspaces={onDeleteAllWorkspaces}
        onDeleteSelectedWorkspaces={onDeleteSelectedWorkspaces}
        onUpdateWorkspace={onUpdateWorkspace}
        onExportSession={onExportSession}
        exportingSessionId={exportingSessionId}
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
