export type MemoryScope = "user_default_global_workspace" | "workspace";

export interface ResolvedMemoryPreview {
  version: string;
  snapshot_hash: string;
  rendered_markdown: string;
}

export interface MemoryVersion {
  id: string;
  version_type: string;
  source: string | null;
  created_at: number;
  summary: string;
}

export interface MemoryVersionListResponse {
  versions: MemoryVersion[];
}

export interface MemoryVersionDetailResponse {
  id: string;
  user_id: string;
  scope_key: string;
  version_type: string;
  source: string | null;
  memory_content: string;
  summary_content: string | null;
  created_at: number;
}

export interface RestoreMemoryVersionResponse {
  success: boolean;
  version_id: string;
  restored_scope_key: string;
}
