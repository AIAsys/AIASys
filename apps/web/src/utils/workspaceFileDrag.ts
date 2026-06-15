export const WORKSPACE_FILE_DRAG_MIME = "application/x-aiasys-workspace-file";

export interface WorkspaceFileReferenceDragPayload {
  scope: "current" | "global";
  paths: string[];
}
