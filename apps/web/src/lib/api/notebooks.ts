import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  ClearNotebookOutputsRequest,
  CreateNotebookRequest,
  DeleteNotebookCellRequest,
  InsertNotebookCellRequest,
  NotebookArtifactsResponse,
  MoveNotebookCellRequest,
  NotebookDocument,
  NotebookDiffResponse,
  NotebookExecutionRecordsResponse,
  NotebookKernelSummary,
  NotebookListResponse,
  NotebookOutlineResponse,
  NotebookPromoteRequest,
  NotebookPromoteResponse,
  NotebookRunResponse,
  NotebookRuntimeControlResponse,
  NotebookRuntimeStateResponse,
  NotebookSearchRequest,
  NotebookSearchResponse,
  NotebookState,
  NotebookVariablesResponse,
  NotebookWorkbenchSnapshot,
  RunNotebookRequest,
  SaveNotebookRequest,
  UpdateNotebookCellRequest,
} from "@/types/notebook";

function getUserId() {
  return getCurrentUserId();
}

export async function listNotebooks(
  sessionId: string,
  directory?: string,
): Promise<NotebookListResponse> {
  const userId = getUserId();
  const endpoint = directory
    ? `${API_ENDPOINTS.NOTEBOOKS_ROOT(userId, sessionId)}?directory=${encodeURIComponent(directory)}`
    : API_ENDPOINTS.NOTEBOOKS_ROOT(userId, sessionId);
  return apiRequest<NotebookListResponse>(endpoint);
}

export async function createNotebook(
  sessionId: string,
  request: CreateNotebookRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(API_ENDPOINTS.NOTEBOOKS_ROOT(userId, sessionId), {
    method: "POST",
    body: request,
  });
}

export async function getNotebookState(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookState> {
  const userId = getUserId();
  return apiRequest<NotebookState>(
    `${API_ENDPOINTS.NOTEBOOKS_STATE(userId, sessionId)}?notebook_path=${encodeURIComponent(notebookPath)}`,
  );
}

export async function getNotebookWorkbench(
  sessionId: string,
  notebookPath: string,
  options: { includeVariables?: boolean; recordsLimit?: number } = {},
): Promise<NotebookWorkbenchSnapshot> {
  const userId = getUserId();
  const params = new URLSearchParams({
    notebook_path: notebookPath,
    include_variables: String(options.includeVariables ?? true),
    records_limit: String(options.recordsLimit ?? 30),
  });
  return apiRequest<NotebookWorkbenchSnapshot>(
    `${API_ENDPOINTS.NOTEBOOKS_WORKBENCH(userId, sessionId)}?${params.toString()}`,
  );
}

export async function searchNotebookCells(
  sessionId: string,
  request: NotebookSearchRequest,
): Promise<NotebookSearchResponse> {
  const userId = getUserId();
  return apiRequest<NotebookSearchResponse>(
    API_ENDPOINTS.NOTEBOOKS_SEARCH_CELLS(userId, sessionId),
    {
      method: "POST",
      body: request,
    },
  );
}

export async function getNotebookOutline(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookOutlineResponse> {
  const userId = getUserId();
  return apiRequest<NotebookOutlineResponse>(
    `${API_ENDPOINTS.NOTEBOOKS_OUTLINE(userId, sessionId)}?notebook_path=${encodeURIComponent(notebookPath)}`,
  );
}

export async function getNotebookRuntimeState(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookRuntimeStateResponse> {
  const userId = getUserId();
  return apiRequest<NotebookRuntimeStateResponse>(
    `${API_ENDPOINTS.NOTEBOOKS_RUNTIME_STATE(userId, sessionId)}?notebook_path=${encodeURIComponent(notebookPath)}`,
  );
}

export async function getNotebookVariables(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookVariablesResponse> {
  const userId = getUserId();
  return apiRequest<NotebookVariablesResponse>(
    `${API_ENDPOINTS.NOTEBOOKS_VARIABLES(userId, sessionId)}?notebook_path=${encodeURIComponent(notebookPath)}`,
  );
}

export async function getNotebookArtifacts(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookArtifactsResponse> {
  const userId = getUserId();
  return apiRequest<NotebookArtifactsResponse>(
    `${API_ENDPOINTS.NOTEBOOKS_ARTIFACTS(userId, sessionId)}?notebook_path=${encodeURIComponent(notebookPath)}`,
  );
}

export async function getNotebookExecutionRecords(
  sessionId: string,
  notebookPath: string,
  limit = 20,
): Promise<NotebookExecutionRecordsResponse> {
  const userId = getUserId();
  const params = new URLSearchParams({
    notebook_path: notebookPath,
    limit: String(limit),
  });
  return apiRequest<NotebookExecutionRecordsResponse>(
    `${API_ENDPOINTS.NOTEBOOKS_EXECUTION_RECORDS(userId, sessionId)}?${params.toString()}`,
  );
}

export async function getNotebookDocument(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(
    API_ENDPOINTS.NOTEBOOKS_DOCUMENT(userId, sessionId, notebookPath),
  );
}

export async function saveNotebookDocument(
  sessionId: string,
  request: SaveNotebookRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(
    API_ENDPOINTS.NOTEBOOKS_DOCUMENT_SAVE(userId, sessionId),
    {
      method: "PUT",
      body: request,
    },
  );
}

export async function forkNotebookToSession(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookDocument> {
  const userId = getUserId();
  const response = await apiRequest<{ document: NotebookDocument }>(
    API_ENDPOINTS.NOTEBOOKS_FORK(userId, sessionId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
  return response.document;
}

export async function promoteNotebookToWorkspace(
  sessionId: string,
  request: NotebookPromoteRequest,
): Promise<NotebookPromoteResponse> {
  const userId = getUserId();
  return apiRequest<NotebookPromoteResponse>(
    API_ENDPOINTS.NOTEBOOKS_PROMOTE(userId, sessionId),
    {
      method: "POST",
      body: request,
    },
  );
}

export async function diffNotebookVersions(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookDiffResponse> {
  const userId = getUserId();
  return apiRequest<NotebookDiffResponse>(
    API_ENDPOINTS.NOTEBOOKS_DIFF(userId, sessionId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}

export async function insertNotebookCell(
  sessionId: string,
  request: InsertNotebookCellRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(API_ENDPOINTS.NOTEBOOKS_INSERT_CELL(userId, sessionId), {
    method: "POST",
    body: request,
  });
}

export async function updateNotebookCell(
  sessionId: string,
  request: UpdateNotebookCellRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(API_ENDPOINTS.NOTEBOOKS_UPDATE_CELL(userId, sessionId), {
    method: "POST",
    body: request,
  });
}

export async function moveNotebookCell(
  sessionId: string,
  request: MoveNotebookCellRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(API_ENDPOINTS.NOTEBOOKS_MOVE_CELL(userId, sessionId), {
    method: "POST",
    body: request,
  });
}

export async function deleteNotebookCell(
  sessionId: string,
  request: DeleteNotebookCellRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(API_ENDPOINTS.NOTEBOOKS_DELETE_CELL(userId, sessionId), {
    method: "POST",
    body: request,
  });
}

export async function clearNotebookOutputs(
  sessionId: string,
  request: ClearNotebookOutputsRequest,
): Promise<NotebookDocument> {
  const userId = getUserId();
  return apiRequest<NotebookDocument>(
    API_ENDPOINTS.NOTEBOOKS_CLEAR_OUTPUTS(userId, sessionId),
    {
      method: "POST",
      body: request,
    },
  );
}

export async function runNotebook(
  sessionId: string,
  request: RunNotebookRequest,
): Promise<NotebookRunResponse> {
  const userId = getUserId();
  return apiRequest<NotebookRunResponse>(API_ENDPOINTS.NOTEBOOKS_RUN(userId, sessionId), {
    method: "POST",
    body: request,
  });
}

export async function interruptNotebookRuntime(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookRuntimeControlResponse> {
  const userId = getUserId();
  return apiRequest<NotebookRuntimeControlResponse>(
    API_ENDPOINTS.NOTEBOOKS_RUNTIME_INTERRUPT(userId, sessionId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}

export async function restartNotebookRuntime(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookRuntimeControlResponse> {
  const userId = getUserId();
  return apiRequest<NotebookRuntimeControlResponse>(
    API_ENDPOINTS.NOTEBOOKS_RUNTIME_RESTART(userId, sessionId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}

export async function stopNotebookRuntime(
  sessionId: string,
  notebookPath: string,
): Promise<NotebookRuntimeControlResponse> {
  const userId = getUserId();
  return apiRequest<NotebookRuntimeControlResponse>(
    API_ENDPOINTS.NOTEBOOKS_RUNTIME_STOP(userId, sessionId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}

export async function listNotebookKernels(
  userId: string,
): Promise<NotebookKernelSummary[]> {
  return apiRequest<NotebookKernelSummary[]>(
    API_ENDPOINTS.NOTEBOOKS_KERNELS(userId),
  );
}

export async function interruptNotebookKernel(
  userId: string,
  notebookPath: string,
): Promise<NotebookRuntimeControlResponse> {
  return apiRequest<NotebookRuntimeControlResponse>(
    API_ENDPOINTS.NOTEBOOKS_KERNEL_INTERRUPT(userId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}

export async function restartNotebookKernel(
  userId: string,
  notebookPath: string,
): Promise<NotebookRuntimeControlResponse> {
  return apiRequest<NotebookRuntimeControlResponse>(
    API_ENDPOINTS.NOTEBOOKS_KERNEL_RESTART(userId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}

export async function stopNotebookKernel(
  userId: string,
  notebookPath: string,
): Promise<NotebookRuntimeControlResponse> {
  return apiRequest<NotebookRuntimeControlResponse>(
    API_ENDPOINTS.NOTEBOOKS_KERNEL_STOP(userId),
    {
      method: "POST",
      body: { notebook_path: notebookPath },
    },
  );
}
