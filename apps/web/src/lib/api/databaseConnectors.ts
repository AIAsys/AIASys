import { API_BASE_URL } from "@/config/api";
import { apiFetch } from "@/lib/api/httpClient";
import type {
  BuiltinSessionDatabaseSchema,
  DatabaseApiErrorCategory,
  DatabaseApiErrorDetail,
  DatabaseConnector,
  DatabaseConnectorCapability,
  DatabaseConnectorDraftPayload,
  DatabaseConnectorTestResult,
  RuntimeDatabaseExecutePayload,
  RuntimeDatabaseExecuteResponse,
  RuntimeDatabaseHandlesResponse,
  RuntimeDatabaseListTablesResponse,
  RuntimeDatabaseDescribeTableResponse,
  RuntimeDatabaseQueryPayload,
  RuntimeDatabaseQueryResponse,
  SessionDatabaseAttachment,
  UpdateDatabaseConnectorPayload,
} from "@/types/databaseConnectors";

function buildApiUrl(
  path: string,
  query?: Record<string, string | undefined | null>,
): string {
  const searchParams = new URLSearchParams();

  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value) {
      searchParams.set(key, value);
    }
  });

  const queryString = searchParams.toString();
  return `${API_BASE_URL}${path}${queryString ? `?${queryString}` : ""}`;
}

interface RequestErrorPayload {
  detail?: unknown;
  message?: unknown;
}

function normalizeErrorDetail(
  payload: RequestErrorPayload,
  responseStatus: number,
): DatabaseApiErrorDetail {
  const detail = payload.detail;
  if (typeof detail === "string" && detail.trim()) {
    return { message: detail.trim() };
  }

  if (detail && typeof detail === "object") {
    const detailRecord = detail as {
      code?: unknown;
      category?: unknown;
      message?: unknown;
      detail?: unknown;
      retryable?: unknown;
    };
    const message =
      (typeof detailRecord.message === "string" && detailRecord.message.trim()) ||
      (typeof detailRecord.detail === "string" && detailRecord.detail.trim()) ||
      (typeof payload.message === "string" && payload.message.trim()) ||
      `请求失败 (${responseStatus})`;

    return {
      code:
        typeof detailRecord.code === "string" && detailRecord.code.trim()
          ? detailRecord.code.trim()
          : null,
      category:
        typeof detailRecord.category === "string" && detailRecord.category.trim()
          ? (detailRecord.category.trim() as DatabaseApiErrorCategory)
          : null,
      message,
      retryable:
        typeof detailRecord.retryable === "boolean" ? detailRecord.retryable : null,
    };
  }

  if (typeof payload.message === "string" && payload.message.trim()) {
    return { message: payload.message.trim() };
  }

  return { message: `请求失败 (${responseStatus})` };
}

export class DatabaseConnectorApiError extends Error {
  status: number;
  code: string | null;
  category: DatabaseApiErrorCategory | null;
  retryable: boolean | null;

  constructor(
    status: number,
    detail: DatabaseApiErrorDetail,
  ) {
    super(detail.message);
    this.name = "DatabaseConnectorApiError";
    this.status = status;
    this.code = detail.code ?? null;
    this.category = detail.category ?? null;
    this.retryable = detail.retryable ?? null;
  }
}

function toReadableErrorMessage(error: DatabaseConnectorApiError): string {
  switch (error.code) {
    case "session_connector_not_attached":
    case "connector_not_attached":
      return "当前任务还没有挂载这个数据库连接。先挂载后再重试。";
    case "connector_not_found":
      return "数据库连接不存在，可能已经被删除。请刷新列表。";
    case "session_not_found":
      return "当前任务上下文不存在或已失效，请刷新页面后重试。";
    case "platform_grant_denied":
    case "grant_denied":
      return "当前任务授权不包含这项数据库操作，请检查挂载策略。";
    case "platform_capability_denied":
    case "capability_denied":
      return "当前连接器能力上限不支持这项数据库操作。";
    case "approval_rejected":
      return "数据库写入审批未通过，本次操作已取消。";
    case "approval_timeout":
      return "数据库写入审批等待超时，请重新发起。";
    case "approval_required":
      return "这次数据库写入需要人工审批，请先处理弹出的确认请求。";
    case "remote_permission_denied":
      return "目标数据库账号权限不足，远端数据库拒绝了这次操作。";
    case "missing_runtime_database_token":
    case "invalid_runtime_database_token":
    case "runtime_token_missing":
    case "runtime_token_invalid":
      return "当前任务的数据库运行时凭证已失效，请刷新页面或重新进入任务。";
    case "unsupported_handle":
    case "invalid_handle":
    case "invalid_connector_handle":
      return "数据库句柄无效，请刷新页面后重试。";
    default:
      break;
  }

  switch (error.category) {
    case "attachment":
      return error.message || "当前任务还没有挂载这个数据库连接。";
    case "approval":
      return error.message || "数据库审批未通过。";
    case "remote":
    case "remote_permission":
    case "remote_execution":
      return error.message || "目标数据库执行失败，请检查 SQL 和目标库权限。";
    case "platform":
      return error.message || "当前平台授权不允许执行该数据库操作。";
    case "session":
      return error.message || "当前任务的数据库状态已失效，请刷新页面。";
    case "auth":
      return error.message || "当前登录或运行时凭证已失效，请刷新页面。";
    default:
      return error.message;
  }
}

export function getDatabaseConnectorErrorMessage(
  error: unknown,
  actionLabel?: string,
): string {
  let message = "请求失败";
  if (error instanceof DatabaseConnectorApiError) {
    message = toReadableErrorMessage(error);
  } else if (error instanceof Error && error.message) {
    message = error.message;
  } else if (
    error &&
    typeof error === "object" &&
    "message" in error &&
    typeof (error as { message?: unknown }).message === "string"
  ) {
    message = (error as { message: string }).message;
  } else {
    message = String(error);
  }

  return actionLabel ? `${actionLabel}：${message}` : message;
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(buildApiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as RequestErrorPayload;
    throw new DatabaseConnectorApiError(
      response.status,
      normalizeErrorDetail(payload, response.status),
    );
  }

  return response.json() as Promise<T>;
}

export function listDatabaseConnectorCapabilities() {
  return requestJson<DatabaseConnectorCapability[]>(
    "/api/database-connectors/capabilities",
    {
      headers: undefined,
    },
  );
}

export function listDatabaseConnectors() {
  return requestJson<DatabaseConnector[]>("/api/database-connectors", {
    headers: undefined,
  });
}

export function createDatabaseConnector(payload: DatabaseConnectorDraftPayload) {
  return requestJson<DatabaseConnector>("/api/database-connectors", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateDatabaseConnector(
  connectorId: string,
  payload: UpdateDatabaseConnectorPayload,
) {
  return requestJson<DatabaseConnector>(`/api/database-connectors/${connectorId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteDatabaseConnector(connectorId: string) {
  return requestJson<{ success: boolean; message: string }>(
    `/api/database-connectors/${connectorId}`,
    {
      method: "DELETE",
      headers: undefined,
    },
  );
}

export function testDatabaseConnectorDraft(payload: DatabaseConnectorDraftPayload) {
  return requestJson<DatabaseConnectorTestResult>("/api/database-connectors/test", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function testSavedDatabaseConnector(connectorId: string) {
  return requestJson<DatabaseConnectorTestResult>(
    `/api/database-connectors/${connectorId}/test`,
    {
      method: "POST",
      headers: undefined,
    },
  );
}

export function listSessionDatabaseAttachments(sessionId: string) {
  return requestJson<SessionDatabaseAttachment[]>(
    `/api/database-connectors/sessions/${sessionId}/attachments`,
    {
      headers: undefined,
    },
  );
}

export function attachDatabaseConnector(
  sessionId: string,
  connectorId: string,
  options?: { sync_defaults?: boolean },
) {
  return requestJson<SessionDatabaseAttachment>(
    `/api/database-connectors/sessions/${sessionId}/attachments`,
    {
      method: "POST",
      body: JSON.stringify({
        connector_id: connectorId,
        sync_defaults: options?.sync_defaults ?? false,
      }),
    },
  );
}

export function detachDatabaseConnector(sessionId: string, connectorId: string) {
  return requestJson<{ success: boolean; message: string }>(
    `/api/database-connectors/sessions/${sessionId}/attachments/${connectorId}`,
    {
      method: "DELETE",
      headers: undefined,
    },
  );
}

export async function fetchBuiltinSessionDatabaseSchema(sessionId: string) {
  const response = await apiFetch(
    buildApiUrl("/api/database/schema", { session_id: sessionId }),
  );

  if (!response.ok) {
    const payload = (await response.json().catch(() => ({}))) as RequestErrorPayload;
    throw new DatabaseConnectorApiError(
      response.status,
      normalizeErrorDetail(payload, response.status),
    );
  }

  return response.json() as Promise<BuiltinSessionDatabaseSchema>;
}

export function listRuntimeDatabaseHandles(sessionId: string) {
  return requestJson<RuntimeDatabaseHandlesResponse>(
    `/api/database/runtime/handles?session_id=${encodeURIComponent(sessionId)}`,
    {
      headers: undefined,
    },
  );
}

export function queryRuntimeDatabase(
  sessionId: string,
  payload: RuntimeDatabaseQueryPayload,
) {
  return requestJson<RuntimeDatabaseQueryResponse>("/api/database/runtime/query", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      ...payload,
    }),
  });
}

export function executeRuntimeDatabase(
  sessionId: string,
  payload: RuntimeDatabaseExecutePayload,
) {
  return requestJson<RuntimeDatabaseExecuteResponse>("/api/database/runtime/execute", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionId,
      ...payload,
    }),
  });
}

export function listRuntimeDatabaseTables(
  sessionId: string,
  handle: string,
) {
  return requestJson<RuntimeDatabaseListTablesResponse>(
    `/api/database/runtime/tables?session_id=${encodeURIComponent(sessionId)}&handle=${encodeURIComponent(handle)}`,
    { headers: undefined },
  );
}

export function describeRuntimeDatabaseTable(
  sessionId: string,
  tableName: string,
  handle: string,
) {
  return requestJson<RuntimeDatabaseDescribeTableResponse>(
    `/api/database/runtime/tables/${encodeURIComponent(tableName)}?session_id=${encodeURIComponent(sessionId)}&handle=${encodeURIComponent(handle)}`,
    { headers: undefined },
  );
}
