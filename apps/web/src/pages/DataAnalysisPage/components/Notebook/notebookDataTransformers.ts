import type {
  NotebookCell,
  NotebookCellInput,
  NotebookCellType,
  NotebookDocument,
  NotebookRuntimeControlResponse,
  NotebookRuntimeStateResponse,
} from "@/types/notebook";

import type {
  NotebookCellMoveDirection,
  NotebookLocalInsertPosition,
} from "./types";

export function cloneNotebookDocument(document: NotebookDocument): NotebookDocument {
  return {
    ...document,
    metadata: { ...document.metadata },
    state: { ...document.state, runtime_summary: { ...document.state.runtime_summary } },
    cells: document.cells.map((cell) => ({
      ...cell,
      metadata: { ...cell.metadata },
      outputs: cell.outputs.map((output) => ({ ...output })),
      output_summaries: cell.output_summaries.map((summary) => ({
        ...summary,
        mime_types: [...summary.mime_types],
      })),
    })),
  };
}

export function toNotebookCellInput(cell: NotebookCell): NotebookCellInput {
  return {
    cell_id: cell.cell_id,
    cell_type: cell.cell_type,
    source: cell.source,
    metadata: { ...cell.metadata },
    outputs: cell.outputs.map((output) => ({ ...output })),
    execution_count: cell.execution_count ?? null,
  };
}

export function createNotebookCell(cellType: NotebookCellType): NotebookCell {
  const cellId =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `cell-${Math.random().toString(16).slice(2, 10)}`;
  return {
    cell_id: cellId,
    cell_type: cellType,
    source: "",
    metadata: {},
    outputs: [],
    output_summaries: [],
    execution_count: null,
  };
}

export function isNotebookDocumentDirty(
  savedDocument: NotebookDocument | null,
  draftDocument: NotebookDocument | null,
): boolean {
  if (!savedDocument || !draftDocument) {
    return false;
  }
  return (
    JSON.stringify({
      metadata: savedDocument.metadata,
      cells: savedDocument.cells,
    }) !==
    JSON.stringify({
      metadata: draftDocument.metadata,
      cells: draftDocument.cells,
    })
  );
}

export function updateNotebookCellInDocument(
  document: NotebookDocument,
  cellId: string,
  patch: Partial<NotebookCell>,
): NotebookDocument {
  return {
    ...document,
    cells: document.cells.map((cell) =>
      cell.cell_id === cellId
        ? {
            ...cell,
            ...patch,
            metadata: patch.metadata ?? cell.metadata,
            outputs: patch.outputs ?? cell.outputs,
            output_summaries: patch.output_summaries ?? cell.output_summaries,
          }
        : cell,
    ),
  };
}

export function insertNotebookCellInDocument(
  document: NotebookDocument,
  referenceIndex: number,
  position: NotebookLocalInsertPosition,
  cellType: NotebookCellType,
): NotebookDocument {
  const nextCells = [...document.cells];
  const newCell = createNotebookCell(cellType);
  const insertIndex = position === "before" ? referenceIndex : referenceIndex + 1;
  nextCells.splice(insertIndex, 0, newCell);
  return {
    ...document,
    cells: nextCells,
  };
}

export function moveNotebookCellInDocument(
  document: NotebookDocument,
  index: number,
  direction: NotebookCellMoveDirection,
): NotebookDocument {
  const nextCells = [...document.cells];
  const targetIndex =
    direction === "up"
      ? Math.max(index - 1, 0)
      : Math.min(index + 1, nextCells.length - 1);
  if (targetIndex === index) {
    return document;
  }
  const [cell] = nextCells.splice(index, 1);
  nextCells.splice(targetIndex, 0, cell);
  return {
    ...document,
    cells: nextCells,
  };
}

export function deleteNotebookCellInDocument(
  document: NotebookDocument,
  cellId: string,
): NotebookDocument {
  return {
    ...document,
    cells: document.cells.filter((cell) => cell.cell_id !== cellId),
  };
}

export function buildNotebookRuntimeState(
  response: NotebookRuntimeControlResponse,
): NotebookRuntimeStateResponse {
  return {
    notebook_path: response.notebook_path,
    runtime_summary: response.runtime_summary,
    runtime_busy: response.runtime_summary.runtime_busy ?? false,
    kernel_active: response.runtime_summary.kernel_active ?? false,
    can_interrupt: response.runtime_summary.kernel_active ?? false,
    can_restart: true,
    can_stop: response.runtime_summary.kernel_active ?? false,
    edit_lock_reason: response.state.edit_lock_reason ?? null,
  };
}
