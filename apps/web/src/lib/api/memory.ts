import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";

export const WORKSPACE_MEMORY_MIRROR_PATH = "记忆/工作区记忆.md";
export const USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE = "user_default_global_workspace";

function getMirrorPathForScope(scope: string): string | null {
  if (scope === "workspace") {
    return WORKSPACE_MEMORY_MIRROR_PATH;
  }
  return null;
}

export async function syncMemoryMirrorFile(
  scope: string,
  sessionId: string,
  content: string,
): Promise<void> {
  const mirrorPath = getMirrorPathForScope(scope);
  if (!mirrorPath) {
    return;
  }

  const userId = getCurrentUserId();
  await apiRequest(API_ENDPOINTS.FILES_CONTENT(userId, sessionId, mirrorPath), {
    method: "PUT",
    body: {
      content,
    },
  });
}

export async function deleteMemoryMirrorFile(
  scope: string,
  sessionId: string,
): Promise<void> {
  const mirrorPath = getMirrorPathForScope(scope);
  if (!mirrorPath) {
    return;
  }

  const userId = getCurrentUserId();
  await apiRequest(API_ENDPOINTS.FILES_DELETE(userId, sessionId, mirrorPath), {
    method: "DELETE",
  });
}

/**
 * 读取工作区 Memory 原始 Markdown 内容
 */
export async function getWorkspaceMemoryContent(
  sessionId?: string,
  workspaceId?: string,
): Promise<{ content: string; workspace_id: string }> {
  const userId = getCurrentUserId();
  const res = await apiRequest(API_ENDPOINTS.MEMORY_WORKSPACE_CONTENT, {
    query: {
      user_id: userId,
      session_id: sessionId,
      workspace_id: workspaceId,
    },
  });
  return res as { content: string; workspace_id: string };
}

/**
 * 保存工作区 Memory 原始 Markdown 内容
 */
export async function updateWorkspaceMemoryContent(
  content: string,
  sessionId?: string,
  workspaceId?: string,
): Promise<void> {
  const userId = getCurrentUserId();
  await apiRequest(API_ENDPOINTS.MEMORY_WORKSPACE_CONTENT, {
    method: "PUT",
    query: {
      user_id: userId,
      session_id: sessionId,
      workspace_id: workspaceId,
    },
    body: {
      content,
    },
  });
}

export interface ResolveMemoryResponse {
  version: string;
  snapshot_hash: string;
  rendered_markdown: string;
}

export interface MemoryPipelineJobStatus {
  kind: string;
  job_key: string;
  status: string;
  worker_id?: string | null;
  lease_until?: number | null;
  attempt_count: number;
  last_error?: string | null;
  created_at: number;
  updated_at: number;
  completed_at?: number | null;
  workspace_id?: string | null;
  session_id?: string | null;
}

export interface MemoryPipelineStatusResponse {
  user_id: string;
  scope_key: string;
  stage1: {
    total_outputs: number;
    pending_outputs: number;
    latest_output_at?: number | null;
    latest_job?: MemoryPipelineJobStatus | null;
  };
  stage2: {
    latest_consolidated_at?: number | null;
    latest_job?: MemoryPipelineJobStatus | null;
    consolidation?: {
      scope_key: string;
      input_watermark: number;
      output_memory_hash?: string | null;
      output_summary_hash?: string | null;
      updated_at: number;
    } | null;
  };
  state_db_path: string;
  memory_root_path: string;
}

export interface MemoryRetentionResponse {
  success: boolean;
  pruned_count: number;
  pruned_rollout_slugs: string[];
  retained_count: number;
  keep_latest: number;
  max_age_days?: number | null;
}

export interface MemoryFileContentResponse {
  filename: string;
  content: string;
  size: number;
  editable: boolean;
}

/**
 * Resolve memory 预览
 */
export async function resolveMemory(
  sessionId: string,
  workspaceId?: string,
): Promise<ResolveMemoryResponse> {
  const userId = getCurrentUserId();
  return apiRequest(API_ENDPOINTS.MEMORY_RESOLVE, {
    method: "POST",
    body: {
      user_id: userId,
      session_id: sessionId,
      workspace_id: workspaceId,
    },
  });
}

export async function getMemoryPipelineStatus(
  scopeKey: string = USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE,
): Promise<MemoryPipelineStatusResponse> {
  const userId = getCurrentUserId();
  return apiRequest(API_ENDPOINTS.MEMORY_STATUS, {
    query: {
      user_id: userId,
      scope_key: scopeKey,
    },
  });
}

export async function applyMemoryRetention(): Promise<MemoryRetentionResponse> {
  const userId = getCurrentUserId();
  return apiRequest(API_ENDPOINTS.MEMORY_RETENTION, {
    method: "POST",
    body: {
      user_id: userId,
    },
  });
}

export async function getUserDefaultMemoryFileContent(
  workspaceId: string,
  assetPath: string,
): Promise<MemoryFileContentResponse> {
  return apiRequest(API_ENDPOINTS.GLOBAL_WORKSPACE_CONTENT(workspaceId, assetPath));
}

/**
 * 列出版本历史
 */
export async function getMemoryVersions(
  scopeKey: string = USER_DEFAULT_GLOBAL_WORKSPACE_MEMORY_SCOPE,
): Promise<{ versions: Array<{ id: string; version_type: string; source: string | null; created_at: number; summary: string }> }> {
  const userId = getCurrentUserId();
  return apiRequest(API_ENDPOINTS.MEMORY_VERSIONS, {
    query: { user_id: userId, scope_key: scopeKey },
  });
}

/**
 * 读取单个版本完整内容
 */
export async function getMemoryVersion(versionId: string): Promise<{
  id: string;
  user_id: string;
  scope_key: string;
  version_type: string;
  source: string | null;
  memory_content: string;
  summary_content: string | null;
  created_at: number;
}> {
  return apiRequest(API_ENDPOINTS.MEMORY_VERSION_DETAIL(versionId));
}

/**
 * 回滚到指定版本
 */
export async function restoreMemoryVersion(versionId: string): Promise<{
  success: boolean;
  version_id: string;
  restored_scope_key: string;
}> {
  return apiRequest(API_ENDPOINTS.MEMORY_VERSION_RESTORE(versionId), {
    method: "POST",
  });
}
