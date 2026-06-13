import { Suspense, lazy } from "react";

import { LLMConfigDialog } from "@/components/settings/LLMConfigDialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { WorkspaceAuxiliaryDialogs } from "./WorkspaceAuxiliaryDialogs";
import { ToastContainer } from "./ToastContainer";
import { useWorkspacePageController } from "../hooks/useWorkspacePageController";

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

const LazyAgentConfigPanel = lazy(() => import("@/components/agent-config/AgentConfigPanel"));

const LazySessionLifecycleDialogs = lazy(() =>
  import("./SessionLifecycleDialogs").then((module) => ({
    default: module.SessionLifecycleDialogs,
  })),
);

interface WorkspaceDialogLayerProps {
  controller: ReturnType<typeof useWorkspacePageController>;
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

export function WorkspaceDialogLayer({
  controller,
}: WorkspaceDialogLayerProps) {
  const {
    executor,
    sessionLifecycle,
    runtimeControls,
    overlayState,
    reloadModels,
    toolPreview,
    combinedToasts,
  } = controller;

  const sessionId = executor.sessionId;
  const workspaceId = controller.currentWorkspaceId;
  return (
    <>
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

      <WorkspaceAuxiliaryDialogs
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
    </>
  );
}
