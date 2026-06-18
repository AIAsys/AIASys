import { WorkspaceContextSurface } from "@/components/layout/WorkspaceSidebar";
import { ErrorBoundary } from "@/components/error/ErrorBoundary";
import { SectionErrorFallback } from "@/components/error/SectionErrorFallback";
import { useAuthContext } from "@/contexts/AuthContext";
import { TopBar } from "../TopBar";
import type { MainContentProps } from "./types";
import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { usePaneTree } from "./usePaneTree";
import { PaneRenderer } from "./PaneRenderer";
import { reorderTabs } from "./paneTree";
import {
  WorkspaceConfigDialog,
  type WorkspaceConfigSection,
} from "@/components/workspace/WorkspaceConfigDialog";

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
  activeTabRequest,
  requestSidebarTab,
}: MainContentProps) {
  const { session, user } = useAuthContext();
  const token = session?.token;
  const [sessionInputBridgeRequestKey, setSessionInputBridgeRequestKey] = useState(0);
  const [isWorkspaceConfigOpen, setIsWorkspaceConfigOpen] = useState(false);
  const [workspaceConfigInitialSection, setWorkspaceConfigInitialSection] =
    useState<WorkspaceConfigSection>("agent-config");

  const executorSessionId = executor.sessionId;

  const isConversationDockClosedByUser = executor.userClosedSidebar;
  const setConversationDockOpen = executor.setIsRightSidebarOpen;
  const setConversationDockClosedByUser = executor.setUserClosedSidebar;
  const currentWorkspaceId = currentWorkspace?.workspace_id;
  // 刷新信号只携带语义化触发器：会话切换、运行状态切换、token_usage 事件序号。
  // 不要塞入 chatItems.length / message_count 这类高频变化值，否则流式输出期间会
  // 触发大量冗余的 token 统计请求（见 useTokenUsageStats）。
  const tokenUsageRefreshSignal = [
    executorSessionId ?? "",
    executor.isRunning ? "running" : "idle",
    executor.tokenUsageRevision,
  ].join(":");

  const {
    paneTree,
    setPaneTree,
    dropZones,
    workspaceDefaultActiveTab,
    workspaceInitialArtifactFile,
    tabDirtyMap,
    setTabDirtyMap,
    closedTerminals,
    reopenTerminal,
    restoreTerminalTabs,
    resetPaneTree,
    openWorkspaceFileTarget,
    openSubagentDetailTab,
    openTerminalTab,
    openBrowserTab,
    openDatabaseQueryTab,
    openCapabilityDetailTab,
    openRuntimeTab,
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

  const handleOpenWorkspaceConfigSection = useCallback(
    (section: WorkspaceConfigSection) => {
      setWorkspaceConfigInitialSection(section);
      setIsWorkspaceConfigOpen(true);
    },
    [],
  );

  const handleOpenWorkspaceSettings = useCallback(() => {
    handleOpenWorkspaceConfigSection("agent-config");
  }, [handleOpenWorkspaceConfigSection]);

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
    // 页面刷新后从 sessionStorage 恢复终端 Tab
    restoreTerminalTabs();
  }, [executorSessionId, resetPaneTree, restoreTerminalTabs]);

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
      workspaceSummary={currentWorkspace}
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
      onOpenRuntimeTab={openRuntimeTab}
      onNewBrowserTab={(url) => openBrowserTab(url)}
      onOpenWorkspaceFileFromCanvas={openWorkspaceFileFromCanvas}
      onOpenInBrowserTab={(url) => openBrowserTab(url)}
      onOpenPreviewFileFromCanvas={openWorkspaceFileTarget}
      onEditFileInMainCanvas={handleEditFileInMainCanvas}
      onTabDirtyChange={(tabId, dirty) => {
        setTabDirtyMap((prev) => ({ ...prev, [tabId]: dirty }));
      }}
      refreshSessionStatus={sessionLifecycle.refreshSessionStatus}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
      onDragLeave={handleDragLeave}
      closedTerminals={closedTerminals}
      onReopenTerminal={reopenTerminal}
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
              <ErrorBoundary
                key={currentWorkspace.workspace_id}
                fallback={(error, reset) => (
                  <SectionErrorFallback error={error} reset={reset} />
                )}
              >
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
                onOpenInBrowserTab={(file) =>
                  openBrowserTab(file.name)
                }
                onOpenGlobalResourceInMainCanvas={handleOpenGlobalResource}
                onEditInMainCanvas={handleEditFileInMainCanvas}
                onOpenKnowledgeGraphCanvas={onOpenKnowledgeGraphDialog}
                onOpenWorkspaceSettings={handleOpenWorkspaceSettings}
                onNewConversation={onNewConversation}
                onSelectConversation={onSelectConversation}
                onForkConversation={onForkConversation}
                onRenameConversation={onRenameConversation}
                onDeleteConversation={onDeleteConversation}
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
              />
              </ErrorBoundary>
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
              onOpenInBrowserTab={(path) =>
                openBrowserTab(path)
              }
              onViewToolDetails={onViewToolDetails}
              onRewriteUserMessage={executor.rewriteUserMessage}
              onRetryLastSubmit={executor.handleRetryLastSubmit}
              onLoadMoreHistory={async () => {
                if (!executor.sessionId) return;
                const older = await executor.loadMoreHistory(executor.sessionId);
                if (older && older.length > 0) {
                  executor.updateChatItemsForSession(executor.sessionId, (prev) => [...older, ...prev]);
                }
              }}
              hasMoreHistory={executor.sessionId ? executor.hasMoreHistory(executor.sessionId) : false}
              inputValue={executor.inputValue}
              onInputChange={executor.setInputValue}
              onSubmit={() => void executor.handleSubmit()}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  !event.nativeEvent.isComposing
                ) {
                  event.preventDefault();
                  void executor.handleSubmit();
                }
              }}
              isRunning={executor.isRunning}
              isPrewarming={executor.isPrewarming}
              isUploading={executor.isUploading}
              uploadProgress={executor.uploadProgress}
              onStop={executor.handleStop}
              uploadedFiles={executor.uploadedFiles}
              failedUploads={executor.failedUploads}
              onRetryUpload={executor.retryUpload}
              onRemoveFailedUpload={executor.removeFailedUpload}
              onRemoveFile={async (idx) => {
                const fileToRemove = executor.uploadedFiles[idx];
                await executor.removeFile(
                  fileToRemove?.file_path,
                );
              }}
              onAddFileClick={executor.handleAddFileClick}
              fileInputRef={executor.fileInputRef}
              onFileChange={executor.handleFileChange}
              runtimeControls={runtimeControls}
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
              onOpenRuntimeTab={openRuntimeTab}
              isCompactingConversation={sessionLifecycle.isCompactingConversation}
              onCompactConversation={sessionLifecycle.handleCompactConversation}
              compactionState={executor.compactionState}
              sessionInputFocusSignal={sessionInputBridgeRequestKey}
              tokenUsageRefreshSignal={tokenUsageRefreshSignal}
            />
          </Suspense>
        ) : null}
      </div>

      {currentWorkspace ? (
        <WorkspaceConfigDialog
          open={isWorkspaceConfigOpen}
          onOpenChange={setIsWorkspaceConfigOpen}
          workspaceSummary={currentWorkspace}
          sessionId={executorSessionId}
          userId={user?.id}
          initialSection={workspaceConfigInitialSection}
          executionPolicy={currentWorkspace.execution_policy}
          availableModels={userModels}
          currentSessionId={executorSessionId}
          currentSessionTitle={sessionTitle}
          conversations={currentWorkspace.conversations ?? []}
          currentConversation={currentWorkspace.current_conversation ?? null}
        />
      ) : null}
    </>
  );
}


