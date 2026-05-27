import type { Dispatch, SetStateAction } from "react";

import type { PreviewFile } from "@/components/layout/WorkspaceSidebar/preview";
import type {
  NotebookArtifactSummary,
  NotebookCell,
  NotebookCellType,
  NotebookDiffCellChange,
  NotebookDocument,
  NotebookExecutionRecord,
  NotebookOutlineItem,
  NotebookRuntimeStateResponse,
  NotebookSearchMatch,
  NotebookVariableSummary,
  NotebookWorkbenchSnapshot,
} from "@/types/notebook";
import type { WorkspaceFile } from "@/types/task";

export interface NotebookWorkbenchCanvasProps {
  file: PreviewFile;
  sessionId?: string;
  workspaceFiles: WorkspaceFile[];
  onClose: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
  onRefreshWorkspace?: (sessionId: string) => Promise<void>;
  onRefreshSessionStatus?: () => void;
}

export type NotebookInspectorTab =
  | "search"
  | "outline"
  | "variables"
  | "artifacts"
  | "runs"
  | "diff";

export type NotebookRuntimeAction = "interrupt" | "restart" | "stop";
export type NotebookCellMoveDirection = "up" | "down";
export type NotebookLocalInsertPosition = "before" | "after";

export interface UseNotebookDocumentOptions {
  file: PreviewFile;
  sessionId?: string;
  workspaceFiles: WorkspaceFile[];
  onRefreshWorkspace?: (sessionId: string) => Promise<void>;
  onRefreshSessionStatus?: () => void;
}

export interface UseNotebookDocumentResult {
  draftDocument: NotebookDocument | null;
  workbenchSnapshot: NotebookWorkbenchSnapshot | null;
  isLoading: boolean;
  isSaving: boolean;
  isRunning: boolean;
  runningCellId: string | null;
  error: string | null;
  externalUpdateDetected: boolean;
  isDirty: boolean;
  runtimeState: NotebookRuntimeStateResponse | null;
  runtimeAction: NotebookRuntimeAction | null;
  inspectorRefreshVersion: number;
  loadDocument: (silent?: boolean) => Promise<void>;
  refreshRuntimeState: () => Promise<NotebookRuntimeStateResponse | null>;
  saveDocument: () => Promise<boolean>;
  runNotebook: (scope: "all" | "cell", cellId?: string) => Promise<void>;
  restartAndRunAll: () => Promise<void>;
  clearOutputs: (cellId?: string) => Promise<void>;
  forkToSession: () => Promise<void>;
  promoteToWorkspace: () => Promise<void>;
  controlRuntime: (action: NotebookRuntimeAction) => Promise<void>;
  updateCell: (cellId: string, patch: Partial<NotebookCell>) => void;
  insertCell: (
    referenceIndex: number,
    position: NotebookLocalInsertPosition,
    type: NotebookCellType,
  ) => void;
  moveCell: (index: number, direction: NotebookCellMoveDirection) => void;
  deleteCell: (cellId: string) => void;
}

export interface UseNotebookInspectorOptions {
  sessionId?: string;
  notebookPath?: string | null;
  lastExecutionRecordId?: string | null;
  refreshVersion: number;
}

export interface UseNotebookInspectorResult {
  inspectorTab: NotebookInspectorTab | null;
  inspectorLoading: boolean;
  inspectorError: string | null;
  searchQuery: string;
  setSearchQuery: Dispatch<SetStateAction<string>>;
  searchResults: NotebookSearchMatch[];
  outlineItems: NotebookOutlineItem[];
  variables: NotebookVariableSummary[];
  artifacts: NotebookArtifactSummary[];
  executionRecords: NotebookExecutionRecord[];
  diffChanges: NotebookDiffCellChange[];
  diffMetadataChanged: boolean;
  toggleInspectorTab: (tab: NotebookInspectorTab) => void;
  closeInspector: () => void;
  handleSearch: () => Promise<void>;
  refreshInspectorData: () => Promise<void>;
}
