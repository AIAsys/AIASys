import { lazy, Suspense, useCallback, useEffect, useRef, useState } from "react";
import { updateTaskWorkspace, exportWorkspace, importWorkspace } from "@/lib/api/workspaces";
import { DesignSidebar } from "@/components/layout/DesignSidebar";
import { MainContent } from "./MainContent";
import { WorkspaceDeleteDialog } from "./components/WorkspaceDeleteDialog";
import { WorkspaceGlobalDialogs } from "./components/WorkspaceGlobalDialogs";
import { useWorkspaceRouteSync } from "./hooks/useWorkspaceRouteSync";
import { useSidebarTabRequest } from "./hooks/useSidebarTabRequest";
import { useWorkspaceLifecycleActions } from "./hooks/useWorkspaceLifecycleActions";
import type { WorkspaceLayoutProps } from "./types";

import { useAuthContext } from "@/contexts/AuthContext";

export type { WorkspaceLayoutProps } from "./types";

const LazyGlobalSettingsDialog = lazy(() =>
  import("@/components/settings/global-settings").then((module) => ({
    default: module.GlobalSettingsDialog,
  })),
);



export function WorkspaceLayout({
  apiBaseUrl,
  executor,
  workspaces,
  isLoadingWorkspaces,
  currentWorkspaceId,
  currentWorkspace,
  loadWorkspaces,
  runtimeControls,
  sessionLifecycle,
  userModels,
  selectedModelId,
  effectiveModelDisplayName,
  onSelectModel,
  thinkingEnabled,
  thinkingEffort,
  setThinkingEnabled,
  setThinkingEffort,
  selectedModelSupportsThinking,
  hasMessagesForMcp,
  hasMCPConfig,
  onDeleteSession,
  onOpenDatabaseConnectionsDialog,
  onCreateDatabaseConnectionDialog,
  onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog,
  onOpenLLMConfigDialog,
  onOpenToolConfig,
  onViewToolDetails,
}: WorkspaceLayoutProps) {
  const leaveProjectWorkspace = useCallback(() => {}, []);

  const { activeTabRequest, requestSidebarTab } = useSidebarTabRequest(currentWorkspaceId);

  const { navigateToWorkspaceConversation } = useWorkspaceRouteSync({
    currentWorkspace,
    currentWorkspaceId,
    sessionId: executor.sessionId,
    handleSelectSession: executor.handleSelectSession,
    isLoadingWorkspaces,
    leaveProjectWorkspace,
    workspaces,
  });

  const {
    deleteWorkspaceError,
    handleDeleteAllWorkspaces,
    handleDeleteConversation,
    handleDeleteSelectedWorkspaces,
    handleDeleteWorkspace,
    handleForkConversation,
    handleNewSession,
    handleNewTask,
    handleRenameConversation,
    handleSessionSelect,
    handleBulkDeleteDialogOpenChange,
    handleWorkspaceDeleteDialogOpenChange,
    handleWorkspaceSelect,
    bulkDeletePendingIds,
    isDeletingWorkspace,
    workspacePendingDeletion,
    confirmDeleteAllWorkspaces,
    confirmDeleteWorkspace,
  } = useWorkspaceLifecycleActions({
    apiBaseUrl,
    currentWorkspace,
    currentWorkspaceId,
    executor,
    leaveProjectWorkspace,
    loadWorkspaces,
    navigateToWorkspaceConversation,
    onDeleteSession,
    runtimeControls,
    workspaces,
  });

  const [isChannelOpen, setIsChannelOpen] = useState(false);
  const [isGlobalSettingsOpen, setIsGlobalSettingsOpen] = useState(false);
  const [globalSettingsSection, setGlobalSettingsSection] = useState<import("@/components/settings/global-settings").SettingsSection>("capabilities");

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === ",") {
        e.preventDefault();
        const last = localStorage.getItem("aiasys:last-settings-section") as import("@/components/settings/global-settings").SettingsSection | null;
        setGlobalSettingsSection(last ?? "capabilities");
        setIsGlobalSettingsOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  // 监听 Electron 托盘菜单动作
  useEffect(() => {
    const desktop = window.__AIASYS_DESKTOP__;
    if (!desktop?.onTrayAction) return;
    desktop.onTrayAction((action) => {
      if (action.type === "open-settings" && action.section) {
        setGlobalSettingsSection(action.section as import("@/components/settings/global-settings").SettingsSection);
        setIsGlobalSettingsOpen(true);
      }
    });
  }, []);

  // 监听来自其他组件（如 NewWorkspaceDialog PreflightCheck）的全局设置打开请求
  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent).detail as string | undefined;
      setGlobalSettingsSection((detail ?? "llm") as import("@/components/settings/global-settings").SettingsSection);
      setIsGlobalSettingsOpen(true);
    };
    window.addEventListener("aiasys:open-global-settings", handler);
    return () => window.removeEventListener("aiasys:open-global-settings", handler);
  }, []);


  const { user } = useAuthContext();

  const handleOpenChannelSettings = () => setIsChannelOpen(true);
  const handleOpenGlobalSettings = (section: import("@/components/settings/global-settings").SettingsSection) => {
    setGlobalSettingsSection(section);
    setIsGlobalSettingsOpen(true);
  };
  const handleOpenChannel = useCallback(() => {
    setIsChannelOpen(true);
  }, []);

  const handleUpdateWorkspace = useCallback(
    async (
      workspaceId: string,
      patch: { title?: string; description?: string | null },
    ) => {
      await updateTaskWorkspace(workspaceId, {
        ...patch,
        description: patch.description ?? undefined,
      });
      await loadWorkspaces();
    },
    [loadWorkspaces],
  );

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleExportWorkspace = useCallback(
    async (workspaceId: string) => {
      try {
        const blob = await exportWorkspace(workspaceId);
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `workspace_${workspaceId}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error("导出工作区失败:", error);
      }
    },
    [],
  );

  const handleImportWorkspaceClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  const handleImportFileChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      try {
        await importWorkspace(file);
        await loadWorkspaces();
      } catch (error) {
        console.error("导入工作区失败:", error);
      }
      e.target.value = "";
    },
    [loadWorkspaces],
  );



  const sessionTitle =
    sessionLifecycle.effectiveSessionStatus?.title ||
    executor.conversations?.find(
      (session) => session.session_id === executor.sessionId,
    )?.title ||
    null;
  const isDeletingCurrentWorkspace = Boolean(
    workspacePendingDeletion &&
    workspacePendingDeletion.workspaceId === currentWorkspaceId,
  );

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={handleImportFileChange}
      />
      <DesignSidebar
        collapsed={executor.sidebarMode === "collapsed"}
        workspaces={workspaces}
        currentWorkspaceId={currentWorkspaceId}
        isLoadingHistory={executor.isLoadingHistory || isLoadingWorkspaces}
        onWorkspaceSelect={handleWorkspaceSelect}
        onDeleteWorkspace={handleDeleteWorkspace}
        onDeleteAllWorkspaces={handleDeleteAllWorkspaces}
        onDeleteSelectedWorkspaces={handleDeleteSelectedWorkspaces}
        onNewTask={handleNewTask}
        onUpdateWorkspace={handleUpdateWorkspace}
        onExportWorkspace={handleExportWorkspace}
        onImportWorkspace={handleImportWorkspaceClick}
        onOpenGlobalSettings={handleOpenGlobalSettings}
        onOpenChannel={handleOpenChannel}
        onOpenChannelSettings={handleOpenChannelSettings}
        onClose={() => executor.setSidebarMode("collapsed")}
        onExpand={() => executor.setSidebarMode("expanded")}
      />

      <WorkspaceDeleteDialog
        open={Boolean(workspacePendingDeletion)}
        workspaceTitle={workspacePendingDeletion?.title ?? null}
        isCurrentWorkspace={isDeletingCurrentWorkspace}
        deleteWorkspaceError={deleteWorkspaceError}
        isDeletingWorkspace={isDeletingWorkspace}
        onOpenChange={handleWorkspaceDeleteDialogOpenChange}
        onConfirmDelete={confirmDeleteWorkspace}
      />

      <WorkspaceDeleteDialog
        open={Boolean(bulkDeletePendingIds)}
        isCurrentWorkspace={false}
        isBulkDelete
        workspaceCount={bulkDeletePendingIds?.length ?? 0}
        deleteWorkspaceError={deleteWorkspaceError}
        isDeletingWorkspace={isDeletingWorkspace}
        onOpenChange={handleBulkDeleteDialogOpenChange}
        onConfirmDelete={confirmDeleteAllWorkspaces}
      />

      <MainContent
        executor={executor}
        runtimeControls={runtimeControls}
        sessionLifecycle={sessionLifecycle}
        workspaces={workspaces}
        isLoadingWorkspaces={isLoadingWorkspaces}
        userModels={userModels}
        selectedModelId={selectedModelId}
        effectiveModelDisplayName={effectiveModelDisplayName}
        onSelectModel={onSelectModel}
        thinkingEnabled={thinkingEnabled}
        thinkingEffort={thinkingEffort}
        setThinkingEnabled={setThinkingEnabled}
        setThinkingEffort={setThinkingEffort}
        selectedModelSupportsThinking={selectedModelSupportsThinking}
        hasMessagesForMcp={hasMessagesForMcp}
        hasMCPConfig={hasMCPConfig}
        onOpenDatabaseConnectionsDialog={onOpenDatabaseConnectionsDialog}
        onCreateDatabaseConnectionDialog={onCreateDatabaseConnectionDialog}
        onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
        onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
        onOpenLLMConfigDialog={onOpenLLMConfigDialog}
        onOpenToolConfig={onOpenToolConfig}
        onViewToolDetails={onViewToolDetails}
        sessionTitle={sessionTitle}
        currentWorkspace={currentWorkspace}
        onSelectWorkspace={handleWorkspaceSelect}
        onSelectConversation={handleSessionSelect}
        onNewConversation={handleNewSession}
        onNewWorkspace={handleNewTask}
        onForkConversation={handleForkConversation}
        onRenameConversation={handleRenameConversation}
        onDeleteConversation={handleDeleteConversation}
        activeTabRequest={activeTabRequest}
        requestSidebarTab={requestSidebarTab}
      />

      <WorkspaceGlobalDialogs
        isChannelOpen={isChannelOpen}
        onChannelOpenChange={setIsChannelOpen}
        currentSessionId={executor.sessionId ?? null}
        workspaces={workspaces}
      />

      <Suspense fallback={null}>
        <LazyGlobalSettingsDialog
          open={isGlobalSettingsOpen}
          onOpenChange={setIsGlobalSettingsOpen}
          initialSection={globalSettingsSection}
          workspaceId={currentWorkspaceId ?? null}
          workspaceTitle={currentWorkspace?.title ?? null}
          userId={user?.id}
          workspaces={workspaces}
          availableModels={userModels}
        />
      </Suspense>

    </>
  );
}
