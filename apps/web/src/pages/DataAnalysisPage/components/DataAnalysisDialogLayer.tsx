import { Suspense, lazy } from "react";

import { LLMConfigDialog } from "@/components/settings/LLMConfigDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { DataAnalysisAuxiliaryDialogs } from "./DataAnalysisAuxiliaryDialogs";
import { FileImportModal } from "./FileImportModal";
import { ToastContainer } from "./ToastContainer";
import { useDataAnalysisPageController } from "../hooks/useDataAnalysisPageController";

const LazyNewWorkspaceDialog = lazy(() =>
  import("@/components/NewWorkspaceDialog").then((module) => ({
    default: module.NewWorkspaceDialog,
  })),
);

const LazyToolPreviewPopover = lazy(() =>
  import("@/components/ToolPreviewPopover").then((module) => ({
    default: module.ToolPreviewPopover,
  })),
);

const LazyCheckpointReviewDialog = lazy(() =>
  import("@/components/CheckpointReviewDialog").then((module) => ({
    default: module.CheckpointReviewDialog,
  })),
);

const LazyAgentConfigPanel = lazy(() => import("@/components/agent-config/AgentConfigPanel"));

const LazySessionLifecycleDialogs = lazy(() =>
  import("./SessionLifecycleDialogs").then((module) => ({
    default: module.SessionLifecycleDialogs,
  })),
);

interface DataAnalysisDialogLayerProps {
  controller: ReturnType<typeof useDataAnalysisPageController>;
}

const LazyDatabaseResourceDialog = lazy(() =>
  import("./DatabaseResourceDialog").then((module) => ({
    default: module.DatabaseResourceDialog,
  })),
);

const LazyResourceManagementDialog = lazy(() =>
  import("./ResourceManagementDialog").then((module) => ({
    default: module.ResourceManagementDialog,
  })),
);

export function DataAnalysisDialogLayer({
  controller,
}: DataAnalysisDialogLayerProps) {
  const {
    apiBaseUrl,
    executor,
    sessionLifecycle,
    runtimeControls,
    overlayState,
    reloadModels,
    askUser,
    toolPreview,
    combinedToasts,
  } = controller;

  const sessionId = executor.sessionId;
  const workspaceId = controller.currentWorkspaceId;
  return (
    <>
      <FileImportModal
        isOpen={executor.showImportModal}
        onClose={() => executor.setShowImportModal(false)}
        targetSessionId={sessionId}
        targetWorkspaceId={workspaceId}
        onImportSuccess={executor.handleImportSuccess}
        apiBaseUrl={apiBaseUrl}
      />

      <ToastContainer toasts={combinedToasts} />

      <Suspense fallback={null}>
        <LazySessionLifecycleDialogs
          isExecutionRecordsDialogOpen={
            sessionLifecycle.isExecutionRecordsDialogOpen
          }
          onExecutionRecordsDialogOpenChange={
            sessionLifecycle.setIsExecutionRecordsDialogOpen
          }
          recordsDialogTab={sessionLifecycle.recordsDialogTab}
          onRecordsDialogTabChange={sessionLifecycle.setRecordsDialogTab}
          highlightedExecutionSequence={
            sessionLifecycle.highlightedExecutionSequence
          }
          isLoadingExecutionRecords={sessionLifecycle.isLoadingExecutionRecords}
          conversationHistoryMessages={
            sessionLifecycle.conversationHistoryMessages
          }
          conversationHistoryArchivedBatches={
            sessionLifecycle.conversationHistoryArchivedBatches
          }
          executionRecords={sessionLifecycle.executionRecords}
          executionMaintenanceMarkers={
            sessionLifecycle.executionMaintenanceMarkers
          }
          executionRecordsSummary={sessionLifecycle.executionRecordsSummary}
          effectiveSessionStatus={sessionLifecycle.effectiveSessionStatus}
        />
      </Suspense>

      <Suspense fallback={null}>
        <LazyNewWorkspaceDialog
          isOpen={runtimeControls.showNewWorkspaceDialog}
          onClose={runtimeControls.closeNewWorkspaceDialog}
          onConfirm={runtimeControls.handleConfirmNewWorkspace}
          lifecycleState={runtimeControls.newWorkspaceLifecycleState}
          registeredPythonEnvs={runtimeControls.registeredPythonEnvs}
          isLoadingRegisteredPythonEnvs={runtimeControls.isLoadingRegisteredPythonEnvs}
          stage={runtimeControls.newWorkspaceStage}
          errorMessage={runtimeControls.newWorkspaceError}
          isSubmitting={
            runtimeControls.isCreatingWorkspace ||
            runtimeControls.isInitializingEnvironment
          }
        />
      </Suspense>

      {overlayState.showDatabaseConnectionsDialog ? (
        <Suspense fallback={null}>
          <LazyDatabaseResourceDialog
            open={overlayState.showDatabaseConnectionsDialog}
            onOpenChange={overlayState.setShowDatabaseConnectionsDialog}
            defaultTab={overlayState.defaultDatabaseResourceDialogTab}
            defaultAction={overlayState.defaultDatabaseResourceDialogAction}
            sessionId={sessionId}
          />
        </Suspense>
      ) : null}

      {overlayState.showResourceManagementDialog ? (
        <Suspense fallback={null}>
          <LazyResourceManagementDialog
            open={overlayState.showResourceManagementDialog}
            onOpenChange={overlayState.setShowResourceManagementDialog}
            defaultSection={overlayState.defaultResourceManagementSection}
            defaultKnowledgeBaseTab={overlayState.defaultKnowledgeBaseDialogTab}
            defaultKnowledgeGraphTab={overlayState.defaultKnowledgeGraphDialogTab}
          />
        </Suspense>
      ) : null}

      <LLMConfigDialog
        open={overlayState.showLLMConfigDialog}
        onOpenChange={overlayState.setShowLLMConfigDialog}
        onModelsChange={reloadModels}
      />

      <Dialog
        open={overlayState.showAgentConfigDialog}
        onOpenChange={overlayState.setShowAgentConfigDialog}
      >
        <DialogContent className="flex h-[88vh] max-w-[min(1280px,94vw)] flex-col gap-0 overflow-hidden p-0 bg-background">
          <DialogTitle className="sr-only">当前会话配置</DialogTitle>
          <DialogDescription className="sr-only">
            配置当前会话的工作说明、工具策略和运行时策略。
          </DialogDescription>
          <Suspense fallback={null}>
            <LazyAgentConfigPanel
              hideHeader
              visibleSections={["tools", "runtime", "preview"]}
              sessionId={sessionId}
              workspaceId={workspaceId}
              sessionTitle={sessionLifecycle.effectiveSessionStatus?.title ?? null}
              sessionStatus={sessionLifecycle.effectiveSessionStatus}
              isSessionRunning={executor.isRunning}
            />
          </Suspense>
        </DialogContent>
      </Dialog>

      <DataAnalysisAuxiliaryDialogs
        runtimeControls={runtimeControls}
      />

      <Suspense fallback={null}>
        <LazyToolPreviewPopover
          isOpen={toolPreview.isOpen}
          onClose={toolPreview.close}
          toolName={toolPreview.data?.toolName || ""}
          toolParams={toolPreview.data?.toolParams}
          toolOutput={toolPreview.data?.toolOutput}
          taskId={toolPreview.data?.taskId}
          triggerRect={toolPreview.data?.triggerRect}
        />
      </Suspense>

      {/* AskUser 弹窗 - 仅检查点评审类型保留弹窗，其他类型已改为聊天流内联卡片 */}
      {askUser.request?.type === 'checkpoint_review' && askUser.request.checkpoint_data ? (
        <Suspense fallback={null}>
          <LazyCheckpointReviewDialog
            checkpointData={askUser.request.checkpoint_data}
            isOpen={Boolean(askUser.request)}
            isLoading={askUser.isLoading}
            errorMessage={askUser.error?.message || null}
            onResponse={askUser.handleResolve}
            onClose={askUser.dismiss}
          />
        </Suspense>
      ) : null}
    </>
  );
}
