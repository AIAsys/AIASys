import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { DiffStatus } from "@/lib/api/diff";

export type FileHistoryScope = "workspace" | "global";

export interface FileHistoryEntry {
  id: string;
  file_path: string;
  timestamp: string;
  operation: string;
  source: string;
  source_detail?: string | null;
  size: number;
  sha256: string;
  target_path?: string | null;
}

export interface FileHistoryListResponse {
  scope: FileHistoryScope;
  workspace_id: string;
  filename: string;
  entries: FileHistoryEntry[];
}

export interface FileHistoryContentResponse {
  entry: FileHistoryEntry;
  content: string;
  size: number;
}

export interface FileHistoryDiffResponse {
  entry: FileHistoryEntry;
  current_exists: boolean;
  diff: string;
  status: DiffStatus;
  left_label?: string | null;
  right_label?: string | null;
  left_text?: string | null;
  right_text?: string | null;
  can_show_content: boolean;
  skip_reason?: string | null;
  additions: number;
  deletions: number;
}

export interface FileHistoryRestoreResponse {
  success: boolean;
  filename: string;
  restored_entry_id: string;
  size: number;
}

interface FileHistoryRequestOptions {
  headers?: HeadersInit;
}

function fileHistoryEndpoint(
  scope: FileHistoryScope,
  kind: "list" | "content" | "diff" | "restore",
  workspaceId: string,
  value: string,
) {
  if (scope === "global") {
    switch (kind) {
      case "list":
        return API_ENDPOINTS.GLOBAL_WORKSPACE_HISTORY_LIST(workspaceId, value);
      case "content":
        return API_ENDPOINTS.GLOBAL_WORKSPACE_HISTORY_CONTENT(workspaceId, value);
      case "diff":
        return API_ENDPOINTS.GLOBAL_WORKSPACE_HISTORY_DIFF(workspaceId, value);
      case "restore":
        return API_ENDPOINTS.GLOBAL_WORKSPACE_HISTORY_RESTORE(workspaceId, value);
    }
  }

  switch (kind) {
    case "list":
      return API_ENDPOINTS.WORKSPACE_FILE_HISTORY_LIST(workspaceId, value);
    case "content":
      return API_ENDPOINTS.WORKSPACE_FILE_HISTORY_CONTENT(workspaceId, value);
    case "diff":
      return API_ENDPOINTS.WORKSPACE_FILE_HISTORY_DIFF(workspaceId, value);
    case "restore":
      return API_ENDPOINTS.WORKSPACE_FILE_HISTORY_RESTORE(workspaceId, value);
  }
  throw new Error("未知文件历史接口");
}

export function listFileHistory(
  scope: FileHistoryScope,
  workspaceId: string,
  filename: string,
  options: FileHistoryRequestOptions = {},
) {
  return apiRequest<FileHistoryListResponse>(
    fileHistoryEndpoint(scope, "list", workspaceId, filename),
    {
      method: "GET",
      headers: options.headers,
    },
  );
}

export function getFileHistoryContent(
  scope: FileHistoryScope,
  workspaceId: string,
  entryId: string,
  options: FileHistoryRequestOptions = {},
) {
  return apiRequest<FileHistoryContentResponse>(
    fileHistoryEndpoint(scope, "content", workspaceId, entryId),
    {
      method: "GET",
      headers: options.headers,
    },
  );
}

export function getFileHistoryDiff(
  scope: FileHistoryScope,
  workspaceId: string,
  entryId: string,
  options: FileHistoryRequestOptions = {},
) {
  return apiRequest<FileHistoryDiffResponse>(
    fileHistoryEndpoint(scope, "diff", workspaceId, entryId),
    {
      method: "GET",
      headers: options.headers,
    },
  );
}

export function restoreFileHistoryEntry(
  scope: FileHistoryScope,
  workspaceId: string,
  entryId: string,
  options: FileHistoryRequestOptions = {},
) {
  return apiRequest<FileHistoryRestoreResponse>(
    fileHistoryEndpoint(scope, "restore", workspaceId, entryId),
    {
      method: "POST",
      headers: options.headers,
    },
  );
}
