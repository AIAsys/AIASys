import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { WorkspaceFile } from "@/types/task";

export function mapToWorkspaceFiles(files: UploadedFile[]): WorkspaceFile[] {
  return files.map((f) => ({
    name: f.filename,
    size: f.size,
    mtime: f.mtime ?? "",
    absolute_path: f.absolute_path,
    resource_type: f.resource_type,
    schema_kind: f.schema_kind,
    preview_kind: f.preview_kind,
    renderer_hint: f.renderer_hint,
    meta: f.meta,
  }));
}

function normalizeMetadata(value: unknown): string {
  if (!value || typeof value !== "object") {
    return "";
  }
  return JSON.stringify(value);
}

/**
 * 比较两个文件列表是否相同
 * 按文件名排序后比较，避免顺序变化导致的重新渲染
 */
function isFilesEqual(
  filesA: WorkspaceFile[],
  filesB: WorkspaceFile[],
): boolean {
  if (filesA.length !== filesB.length) return false;

  // 按文件名排序后比较
  const sortedA = [...filesA].sort((a, b) => a.name.localeCompare(b.name));
  const sortedB = [...filesB].sort((a, b) => a.name.localeCompare(b.name));

  for (let i = 0; i < sortedA.length; i++) {
    const a = sortedA[i];
    const b = sortedB[i];
    // 比较文件名、大小和修改时间
    if (
      a.name !== b.name ||
      a.size !== b.size ||
      a.mtime !== b.mtime ||
      a.absolute_path !== b.absolute_path ||
      a.resource_type !== b.resource_type ||
      a.schema_kind !== b.schema_kind ||
      a.preview_kind !== b.preview_kind ||
      a.renderer_hint !== b.renderer_hint ||
      normalizeMetadata(a.meta) !== normalizeMetadata(b.meta)
    ) {
      return false;
    }
  }

  return true;
}

export async function refreshWorkspaceFiles(
  reloadWorkspaceFiles: (
    workspaceId?: string,
    options?: { force?: boolean },
  ) => Promise<UploadedFile[]>,
  updateWorkspaceFilesForSession: (
    sessionId: string,
    files: WorkspaceFile[],
  ) => void,
  sessionId?: string,
  workspaceId?: string | null,
  currentFiles?: WorkspaceFile[],
  options?: { force?: boolean },
) {
  if (!sessionId || !workspaceId) return;
  const latest = await reloadWorkspaceFiles(workspaceId, options);
  if (!latest) return;

  const newFiles = mapToWorkspaceFiles(latest);

  // 如果文件列表没有变化，不更新状态（避免闪烁）
  if (currentFiles && isFilesEqual(currentFiles, newFiles)) {
    return;
  }

  updateWorkspaceFilesForSession(sessionId, newFiles);
}
