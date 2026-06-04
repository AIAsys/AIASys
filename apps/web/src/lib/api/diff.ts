import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";

export type DiffStatus = "added" | "deleted" | "modified" | "unchanged" | "skipped";
export type DiffScope = "workspace" | "global";

export interface DiffStats {
  additions: number;
  deletions: number;
  left_lines: number;
  right_lines: number;
}

export interface TextDiffSide {
  content: string;
  label?: string | null;
}

export interface TextDiffRequest {
  left: TextDiffSide;
  right: TextDiffSide;
  include_text?: boolean;
}

export interface TextDiffResponse {
  left_label: string;
  right_label: string;
  left_text?: string | null;
  right_text?: string | null;
  unified_diff: string;
  status: DiffStatus;
  format: "unified";
  can_show_content: boolean;
  skip_reason?: string | null;
  stats: DiffStats;
}

export interface DiffPathRef {
  scope: DiffScope;
  path: string;
  workspace_id?: string | null;
  label?: string | null;
}

export interface FileDiffRequest {
  left: DiffPathRef;
  right: DiffPathRef;
  include_text?: boolean;
}

export interface FileDiffResponse extends TextDiffResponse {
  left_exists: boolean;
  right_exists: boolean;
  left_size?: number | null;
  right_size?: number | null;
  left_sha256?: string | null;
  right_sha256?: string | null;
  is_binary: boolean;
  is_too_large: boolean;
}

export interface DirectoryDiffRequest {
  left: DiffPathRef;
  right: DiffPathRef;
  include_unchanged?: boolean;
  max_files?: number;
}

export interface DirectoryDiffEntry {
  path: string;
  status: DiffStatus;
  left_size?: number | null;
  right_size?: number | null;
  left_sha256?: string | null;
  right_sha256?: string | null;
}

export interface DirectoryDiffResponse {
  left_label: string;
  right_label: string;
  files: DirectoryDiffEntry[];
  counts: Record<DiffStatus, number>;
  total_files: number;
  included_files: number;
  include_unchanged: boolean;
  max_files: number;
}

export function compareTextDiff(request: TextDiffRequest) {
  return apiRequest<TextDiffResponse>(API_ENDPOINTS.DIFF_TEXT, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function compareFileDiff(request: FileDiffRequest) {
  return apiRequest<FileDiffResponse>(API_ENDPOINTS.DIFF_FILES, {
    method: "POST",
    body: JSON.stringify(request),
  });
}

export function compareDirectoryDiff(request: DirectoryDiffRequest) {
  return apiRequest<DirectoryDiffResponse>(API_ENDPOINTS.DIFF_DIRECTORIES, {
    method: "POST",
    body: JSON.stringify(request),
  });
}
