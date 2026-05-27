import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { FileHistoryEntry } from "@/lib/api/fileHistory";

export type FileChangesScope = "workspace" | "global";

export interface RecentChangeItem {
  file_path: string;
  latest_entry: FileHistoryEntry;
  total_versions: number;
}

export interface RecentChangesResponse {
  scope: FileChangesScope;
  workspace_id: string;
  files: RecentChangeItem[];
}

export function listRecentChanges(
  scope: FileChangesScope,
  workspaceId: string,
  limit: number = 50,
) {
  const endpoint =
    scope === "global"
      ? API_ENDPOINTS.GLOBAL_WORKSPACE_RECENT_CHANGES(workspaceId)
      : API_ENDPOINTS.WORKSPACE_RECENT_CHANGES(workspaceId);
  return apiRequest<RecentChangesResponse>(
    `${endpoint}?limit=${limit}`,
    { method: "GET" },
  );
}