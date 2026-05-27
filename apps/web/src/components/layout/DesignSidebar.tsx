import { useAuthContext } from "@/contexts/AuthContext";
import { isSingleUserAuthMode } from "@/config/auth";
import { DesignSidebarCollapsed } from "./design-sidebar/DesignSidebarCollapsed";
import { DesignSidebarExpanded } from "./design-sidebar/DesignSidebarExpanded";
import { ProfileEditDialog } from "./design-sidebar/ProfileEditDialog";
import type { SidebarProps } from "./design-sidebar/types";
import { useMemo, useState } from "react";

// 默认头像颜色
const DEFAULT_AVATAR_COLOR = "bg-primary";

export function DesignSidebar({
  className = "",
  collapsed = false,
  onClose,
  onExpand,
  onNewTask,
  onUpdateWorkspace,
  onOpenGlobalSettings,
  onOpenChannel,
  onOpenChannelSettings,
  sessions = [],
  workspaces = [],
  currentWorkspaceId,
  currentSessionId,
  isLoadingHistory = false,
  onSessionSelect,
  onDeleteSession,
  onForkConversation,
  onWorkspaceSelect,
  onDeleteWorkspace,
  onDeleteAllWorkspaces,
  onDeleteSelectedWorkspaces,
  onExportSession,
  exportingSessionId,
}: SidebarProps) {
  const { user, isAuthenticated, isLoading, handleLogout, updateProfile } = useAuthContext();

  const [searchQuery, setSearchQuery] = useState("");
  const [profileDialogOpen, setProfileDialogOpen] = useState(false);

  const displayName = useMemo(() => {
    if (isLoading) return "加载中...";
    if (!isAuthenticated) {
      return isSingleUserAuthMode() ? "本地工作区" : "未登录";
    }
    return user?.nickname || user?.username || user?.email || "用户";
  }, [isLoading, isAuthenticated, user]);

  const avatarChar = useMemo(() => {
    if (!user) return "?";
    const name = user.nickname || user.username;
    return (user.avatarChar || name?.charAt(0) || "?").toUpperCase();
  }, [user]);

  const avatarColor = useMemo(() => {
    return user?.avatarColor || DEFAULT_AVATAR_COLOR;
  }, [user]);

  const handleEditProfile = () => {
    setProfileDialogOpen(true);
  };

  const handleSaveProfile = async (data: { name: string; avatarColor: string; avatarChar: string }) => {
    return updateProfile(data);
  };

  const filteredSessions = useMemo(() => {
    if (!searchQuery.trim()) return sessions;
    const query = searchQuery.toLowerCase();
    return sessions.filter((session) =>
      (session.title || "未命名对话").toLowerCase().includes(query),
    );
  }, [sessions, searchQuery]);

  const displayWorkspaces = useMemo(
    () => workspaces.filter((w) => w.workspace_kind !== "claw" && w.title !== "Claw 远程会话"),
    [workspaces],
  );

  const filteredWorkspaces = useMemo(() => {
    if (!searchQuery.trim()) {
      return displayWorkspaces;
    }
    const query = searchQuery.toLowerCase();
    return displayWorkspaces.filter((workspace) =>
      (workspace.title || "未命名工作区").toLowerCase().includes(query),
    );
  }, [searchQuery, displayWorkspaces]);

  return (
    <div
      className={`relative flex h-full bg-sidebar border-r border-sidebar-border text-sm overflow-hidden transition-all duration-300 ease-in-out ${collapsed ? "w-[56px]" : "w-[220px]"} ${className}`}
    >
      {collapsed ? (
        <DesignSidebarCollapsed
          avatarChar={avatarChar}
          avatarColor={avatarColor}
          displayName={displayName}
          onExpand={onExpand}
          onNewTask={onNewTask}
          onOpenGlobalSettings={onOpenGlobalSettings}
          onEditProfile={handleEditProfile}
        />
      ) : (
        <DesignSidebarExpanded
          avatarChar={avatarChar}
          avatarColor={avatarColor}
          currentSessionId={currentSessionId}
          currentWorkspaceId={currentWorkspaceId}
          displayName={displayName}
          exportingSessionId={exportingSessionId}
          filteredSessions={filteredSessions}
          filteredWorkspaces={filteredWorkspaces}
          isAuthenticated={isAuthenticated}
          isLoadingHistory={isLoadingHistory}
          searchQuery={searchQuery}
          sessions={sessions}
          workspaces={displayWorkspaces}
          onClose={onClose}
          onDeleteSession={onDeleteSession}
          onForkConversation={onForkConversation}
          onWorkspaceSelect={onWorkspaceSelect}
          onDeleteWorkspace={onDeleteWorkspace}
          onDeleteAllWorkspaces={onDeleteAllWorkspaces}
          onDeleteSelectedWorkspaces={onDeleteSelectedWorkspaces}
          onExportSession={onExportSession}
          onUpdateWorkspace={onUpdateWorkspace}
          onOpenGlobalSettings={onOpenGlobalSettings}
          onOpenChannel={onOpenChannel}
          onOpenChannelSettings={onOpenChannelSettings}
          onLogout={handleLogout}
          onNewTask={onNewTask}
          onSearchQueryChange={setSearchQuery}
          onSessionSelect={onSessionSelect}
          onClearSearch={() => setSearchQuery("")}
          onEditProfile={handleEditProfile}
        />
      )}
      <ProfileEditDialog
        open={profileDialogOpen}
        avatarColor={avatarColor}
        displayName={displayName}
        onClose={() => setProfileDialogOpen(false)}
        onSave={handleSaveProfile}
      />
    </div>
  );
}
