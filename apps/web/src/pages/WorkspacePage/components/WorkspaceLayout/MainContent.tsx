import { WorkspaceContextSurface } from "@/components/layout/WorkspaceSidebar";
import { WorkspaceAutoTaskPanel } from "@/components/layout/WorkspaceSidebar/WorkspaceAutoTaskPanel";
import { useAuthContext } from "@/contexts/AuthContext";
import { TopBar } from "../TopBar";
import type { MainContentProps } from "./types";
import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { usePaneTree } from "./usePaneTree";
import { PaneRenderer } from "./PaneRenderer";
import { reorderTabs } from "./paneTree";

const LazyWorkspaceHomeScreen = lazy(() =>
  import("./WorkspaceHomeScreen").then((module) => ({
    default: module.WorkspaceHomeScreen,
  })),
);

const LazyConversationDock = lazy(() =>
  import("./ConversationDock").then((module) => ({
    default: module.ConversationDock,
  })),
);

export function MainContent({
  executor,
  runtimeControls,
  sessionLifecycle,
  workspaces,
  isLoadingWorkspaces,
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
  onOpenDatabaseConnectionsDialog,
  onCreateDatabaseConnectionDialog,
  onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog,
  onOpenLLMConfigDialog,
  onOpenToolConfig,
  onViewToolDetails,
  sessionTitle,
  currentWorkspace,
  onSelectWorkspace,
  onSelectConversation,
  onNewConversation,
  onNewWorkspace,
  onForkConversation,
  onRenameConversation,
  onDeleteConversation,
  onOpenGlobalAutoTask,
  onOpenWorkspaceSettings,
  activeTabRequest,
  requestSidebarTab,
}: MainContentProps) {
  const { session, user } = useAuthContext();
  const token = session?.token;
  const [sessionInputBridgeRequestKey, setSessionInputBridgeRequestKey] = useState(0);

  const executorSessionId = executor.sessionId;

  const isConversationDockClosedByUser = executor.userClosedSidebar;
  const setConversationDockOpen = executor.setIsRightSidebarOpen;
  const setConversationDockClosedByUser = executor.setUserClosedSidebar;
  const currentWorkspaceId = currentWorkspace?.workspace_id;
  const tokenUsageRefreshSignal = [
    executorSessionId ?? "",
    executor.chatItems.length,
    executor.isRunning ? "running" : "idle",
    executor.tokenUsageRevision,
    sessionLifecycle.sessionStatus?.message_count ?? 0,
  ].join(":");

  const {
    paneTree,
    setPaneTree,
    dropZones,
    workspaceDefaultActiveTab,
    workspaceInitialArtifactFile,
    tabDirtyMap,
    setTabDirtyMap,
    resetPaneTree,
    openWorkspaceFileTarget,
    openSubagentDetailTab,
    openTerminalTab,
    openDatabaseQueryTab,
    openCapabilityDetailTab,
    handleOpenGlobalResource,
    activateWorkspaceTab,
    closeWorkspaceTab,
    closeOtherTabs,
    closeRightTabs,
    closeAllTabs,
    splitPane,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    openWorkspaceFileFromCanvas,
    handleEditFileInMainCanvas,
  } = usePaneTree(executorSessionId, token, currentWorkspaceId);

  const openSubagentDock = useCallback(() => {
    setConversationDockOpen(true);
    setConversationDockClosedByUser(false);
  }, [setConversationDockOpen, setConversationDockClosedByUser]);

  const focusCurrentSessionInput = async (options?: {
    targetSessionId?: string | null;
    draft?: string;
  }) => {
    setConversationDockOpen(true);
    setConversationDockClosedByUser(false);
    if (
      options?.targetSessionId &&
      options.targetSessionId !== executorSessionId
    ) {
      await executor.handleSelectSession(options.targetSessionId);
    }
    if (options?.draft !== undefined) {
      executor.setInputValue(options.draft);
    }
    setSessionInputBridgeRequestKey((value) => value + 1);
  };

  useEffect(() => {
    resetPaneTree();
  }, [executorSessionId, resetPaneTree]);

  // Ctrl+` 切换到侧边栏终端 Tab
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === "`") {
        e.preventDefault();
        requestSidebarTab?.("terminal");
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [requestSidebarTab]);

  useEffect(() => {
    if (!activeTabRequest || !currentWorkspaceId) {
      return;
    }
    if (
      activeTabRequest.targetWorkspaceId &&
      activeTabRequest.targetWorkspaceId !== currentWorkspaceId
    ) {
      return;
    }

    if (activeTabRequest.tab === "subagents") {
      openSubagentDock();
      return;
    }

  }, [activeTabRequest, currentWorkspaceId, openSubagentDock]);

  useEffect(() => {
    if (!currentWorkspaceId || isConversationDockClosedByUser) {
      return;
    }

    setConversationDockOpen(true);
  }, [
    currentWorkspaceId,
    executorSessionId,
    isConversationDockClosedByUser,
    setConversationDockOpen,
  ]);

  const showWorkspaceHome =
    !currentWorkspace && !isLoadingWorkspaces && !executor.isRestoringSession;

  const workspaceEditorContent = (
    <PaneRenderer
      paneTree={paneTree}
      dropZones={dropZones}
      executor={executor}
      currentWorkspaceId={currentWorkspaceId}
      userId={user?.id}
      tabDirtyMap={tabDirtyMap}
      onActivateTab={activateWorkspaceTab}
      onCloseTab={closeWorkspaceTab}
      onCloseOtherTabs={closeOtherTabs}
      onCloseRightTabs={closeRightTabs}
      onCloseAllTabs={closeAllTabs}
      onSplitPane={splitPane}
      onTabReorder={(leafId, fromIndex, toIndex) => {
        setPaneTree((current) => reorderTabs(current, leafId, fromIndex, toIndex));
      }}
      onNewTerminalTab={() => openTerminalTab({ forceNew: true })}
      onOpenWorkspaceFileFromCanvas={openWorkspaceFileFromCanvas}
      onOpenPreviewFileFromCanvas={openWorkspaceFileTarget}
      onEditFileInMainCanvas={handleEditFileInMainCanvas}
      onTabDirtyChange={(tabId, dirty) => {
        setTabDirtyMap((prev) => ({ ...prev, [tabId]: dirty }));
      }}
      refreshSessionStatus={sessionLifecycle.refreshSessionStatus}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onDragLeave={handleDragLeave}
    />
  );

  return (
    <>
      <div className="relative flex h-full min-h-0 min-w-0 flex-1 overflow-hidden bg-background">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          <TopBar
            sessionId={showWorkspaceHome ? null : executorSessionId}
            workspaceTitle={currentWorkspace?.title ?? null}
            sessionTitle={showWorkspaceHome ? "工作区首页" : sessionTitle}
            locked={false}
          />

          <div className="relative flex min-h-0 flex-1 overflow-hidden">
            {showWorkspaceHome ? (
              <Suspense fallback={
                <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
                  正在加载工作区首页...
                </div>
              }>
                <LazyWorkspaceHomeScreen
                  workspaces={workspaces}
                  isLoading={isLoadingWorkspaces}
                  onOpenWorkspace={onSelectWorkspace}
                  onCreateWorkspace={onNewWorkspace}
                />
              </Suspense>
            ) : currentWorkspace ? (
              <WorkspaceContextSurface
                key={currentWorkspace.workspace_id}
                defaultActiveTab={workspaceDefaultActiveTab}
                taskList={executor.currentTaskList}
                selectedTask={executor.selectedTask}
                selectedTaskId={executor.selectedTaskId}
                onSelectTask={executor.selectTask}
                sessionId={executor.sessionId}
                sessionTitle={sessionTitle}
                messageCount={sessionLifecycle.effectiveSessionStatus?.message_count}
                executionRecordCount={
                  sessionLifecycle.effectiveSessionStatus?.execution_record_count
                }
                lastRuntimeState={
                  sessionLifecycle.effectiveSessionStatus?.last_runtime_state
                }
                isSessionRunning={executor.isRunning}
                isCompactingConversation={sessionLifecycle.isCompactingConversation}
                isRestartingRuntime={runtimeControls.isRestartingRuntime}
                onCompactConversation={sessionLifecycle.handleCompactConversation}
                onRestartRuntime={runtimeControls.handleRestartRuntime}
                onViewExecutionRecords={sessionLifecycle.handleViewExecutionRecords}
                isLoadingHistory={executor.isLoadingHistory}
                userModels={userModels}
                workspaceSummary={currentWorkspace}
                sessionStatus={sessionLifecycle.sessionStatus}
                workspaceFiles={executor.workspaceFiles}
                pendingUploadedFiles={executor.uploadedFiles}
                onDeleteFile={executor.deleteWorkspaceFile}
                onDeleteFolder={executor.deleteWorkspaceFolder}
                onReadFileContent={executor.readWorkspaceFileContent}
                onRefreshWorkspaceFiles={
                  executor.sessionId
                    ? () =>
                        executor.refreshWorkspaceForSession(executor.sessionId, {
                          force: true,
                        })
                    : undefined
                }
                onMoveFile={executor.moveFile}
                onUploadFiles={executor.handleUploadFiles}
                activeTabRequest={activeTabRequest}
                initialArtifactFile={workspaceInitialArtifactFile}
                onManageDatabaseConnections={onOpenDatabaseConnectionsDialog}
                onCreateDatabaseConnection={onCreateDatabaseConnectionDialog}
                onOpenKnowledgeBaseDialog={onOpenKnowledgeBaseDialog}
                onOpenKnowledgeGraphDialog={onOpenKnowledgeGraphDialog}
                onOpenCanvasPreview={(file) =>
                  openWorkspaceFileTarget(file)
                }
                onOpenGlobalResourceInMainCanvas={handleOpenGlobalResource}
                onEditInMainCanvas={handleEditFileInMainCanvas}
                onOpenKnowledgeGraphCanvas={onOpenKnowledgeGraphDialog}
                onOpenGlobalAutoTask={onOpenGlobalAutoTask}
                onOpenWorkspaceSettings={onOpenWorkspaceSettings}
                onNewConversation={onNewConversation}
                onRequestHostClarification={(request) => {
                  void focusCurrentSessionInput(request);
                }}
                onRequestSubagentDock={openSubagentDock}
                onOpenSubagentInMainCanvas={openSubagentDetailTab}
                onOpenDatabaseQueryTab={openDatabaseQueryTab}
                onOpenTerminalTab={openTerminalTab}
                onOpenCapabilityDetailTab={(capId, displayName) => {
                  if (currentWorkspace?.workspace_id) {
                    openCapabilityDetailTab(capId, currentWorkspace.workspace_id, displayName);
                  }
                }}
                editorContent={workspaceEditorContent}
                autoTaskContent={
                <WorkspaceAutoTaskPanel
                  workspaceId={currentWorkspace?.workspace_id}
                  executionPolicy={currentWorkspace?.execution_policy}
                  availableModels={userModels}
                  currentSessionId={executorSessionId}
                  currentSessionTitle={sessionTitle}
                  conversations={currentWorkspace?.conversations ?? []}
                  currentConversation={
                    currentWorkspace?.current_conversation ?? null
                  }
                />
                }
              />
            ) : (
              <div className="flex flex-1 items-center justify-center px-6 text-sm text-muted-foreground">
                正在同步当前工作区与会话上下文...
              </div>
            )}
          </div>
        </div>

        {currentWorkspace ? (
          <Suspense fallback={
              <div
                className="relative shrink-0 border-l border-border bg-background"
                style={{ width: `${executor.sidebarWidth}px` }}
              />
            }>
            <LazyConversationDock
              isOpen={executor.isRightSidebarOpen}
              width={executor.sidebarWidth}
              onWidthChange={executor.setSidebarWidth}
              onOpen={() => {
                setConversationDockOpen(true);
                setConversationDockClosedByUser(false);
              }}
              onClose={() => {
                setConversationDockOpen(false);
                setConversationDockClosedByUser(true);
              }}
              workspace={currentWorkspace}
              sessionStatus={sessionLifecycle.sessionStatus}
              currentSessionId={executorSessionId}
              sessionTitle={sessionTitle}
              chatItems={executor.chatItems}
              messagesEndRef={executor.messagesEndRef}
              onSelectConversation={onSelectConversation}
              onNewConversation={onNewConversation}
              onForkConversation={onForkConversation}
              onRenameConversation={onRenameConversation}
              onDeleteConversation={onDeleteConversation}
              onWorkerClick={(workerName) => {
                executor.handleWorkerClick(workerName);
              }}
              onOpenWorkspaceArtifact={(file) =>
                openWorkspaceFileTarget(file)
              }
              onViewToolDetails={onViewToolDetails}
              onRewriteUserMessage={executor.rewriteUserMessage}
              inputValue={executor.inputValue}
              onInputChange={executor.setInputValue}
              onSubmit={() => void executor.handleSubmit()}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  void executor.handleSubmit();
                }
              }}
              isRunning={executor.isRunning}
              isPrewarming={executor.isPrewarming}
              isUploading={executor.isUploading}
              onStop={executor.handleStop}
              uploadedFiles={executor.uploadedFiles}
              onRemoveFile={async (idx) => {
                const fileToRemove = executor.uploadedFiles[idx];
                await executor.removeFile(
                  fileToRemove?.file_path,
                );
              }}
              onAddFileClick={executor.handleAddFileClick}
              onImportFromSession={() => executor.setShowImportModal(true)}
              fileInputRef={executor.fileInputRef}
              onFileChange={executor.handleFileChange}
              runtimeControls={runtimeControls}
              hasMessagesForMcp={hasMessagesForMcp}
              hasMCPConfig={hasMCPConfig}
              userModels={userModels}
              selectedModelId={selectedModelId}
              effectiveModelDisplayName={effectiveModelDisplayName}
              onSelectModel={onSelectModel}
              thinkingEnabled={thinkingEnabled}
              thinkingEffort={thinkingEffort}
              setThinkingEnabled={setThinkingEnabled}
              setThinkingEffort={setThinkingEffort}
              selectedModelSupportsThinking={selectedModelSupportsThinking}
              onOpenLLMConfigDialog={onOpenLLMConfigDialog}
              onOpenToolConfig={onOpenToolConfig}
              onOpenWorkspaceSettings={onOpenWorkspaceSettings}
              isCompactingConversation={sessionLifecycle.isCompactingConversation}
              onCompactConversation={sessionLifecycle.handleCompactConversation}
              sessionInputFocusSignal={sessionInputBridgeRequestKey}
              tokenUsageRefreshSignal={tokenUsageRefreshSignal}
              onUploadToWorkspace={executor.handleUploadFiles}
            />
          </Suspense>
        ) : null}
      </div>
    </>
  );
}


