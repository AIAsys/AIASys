import {
  NEW_TASK_STAGE_LABELS,
  type NewTaskLifecycleState,
  type NewTaskStage,
} from "@/types/workspace";

const NEW_TASK_BUSY_STAGES = new Set<NewTaskStage>([
  "preparing_session",
  "scanning_folder",
  "copying_files",
  "import_creating_workspace",
  "creating_workspace",
  "binding_environment",
  "waiting_runtime",
  "activating_session",
]);

export function buildNewTaskLifecycleState(
  stage: NewTaskStage,
  errorMessage: string | null,
  progress?: number,
  message?: string,
): NewTaskLifecycleState {
  const isError = stage === "error" || Boolean(errorMessage);

  return {
    stage,
    stageLabel: NEW_TASK_STAGE_LABELS[stage],
    showProgress: stage !== "idle",
    isBusy: NEW_TASK_BUSY_STAGES.has(stage),
    isError,
    errorMessage,
    progress,
    message,
  };
}
