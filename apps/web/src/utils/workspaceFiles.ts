import { API_BASE_URL, API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiFetch } from "@/lib/api/httpClient";
import {
  getPreviewUrlOptions,
  inferPreviewType,
  inferWorkspaceRenderableFileType as inferRenderableFileType,
  type PreviewFile,
  type WorkspaceRenderableFileType,
} from "@/utils/filePreviewRegistry";
import { appendAccessToken, stripApiBaseUrl } from "@/utils/urlUtils";

export type { WorkspaceRenderableFileType } from "@/utils/filePreviewRegistry";

export type WorkspacePreviewFileSource =
  | string
  | {
      name: string;
      type?: string;
      size?: number;
      mtime?: string;
      absolute_path?: string | null;
      resource_type?: PreviewFile["resource_type"];
      schema_kind?: string;
      preview_kind?: string;
      renderer_hint?: string;
      meta?: Record<string, unknown>;
    };

export type GlobalWorkspacePreviewFileSource = WorkspacePreviewFileSource & {
  meta?: Record<string, unknown>;
};

function resolveFileApiBaseUrl(preferDirectBackend = false): string {
  if (API_BASE_URL) {
    return API_BASE_URL;
  }

  if (
    preferDirectBackend &&
    typeof window !== "undefined" &&
    window.location.port === "13000"
  ) {
    return `${window.location.protocol}//${window.location.hostname}:13001`;
  }

  return "";
}

function inferWorkspaceSessionId(sessionId?: string): string | undefined {
  if (sessionId) {
    return sessionId;
  }

  if (typeof window === "undefined") {
    return undefined;
  }

  const match = window.location.pathname.match(/\/workspace\/([^/]+)/);
  return match?.[1];
}

export function workspacePathToFilename(path: string): string {
  const cleanPath = stripApiBaseUrl(path || "");
  if (cleanPath.startsWith("/workspace/")) {
    return cleanPath.slice("/workspace/".length);
  }
  if (cleanPath.startsWith("/global/")) {
    return cleanPath.slice("/global/".length);
  }
  return cleanPath.replace(/^\.?\//, "");
}

export function inferWorkspaceRenderableFileType(
  path: string,
  declaredType?: string,
): WorkspaceRenderableFileType | null {
  return inferRenderableFileType(stripApiBaseUrl(path || ""), declaredType);
}

export function createWorkspacePreviewFile(
  file: WorkspacePreviewFileSource,
  sessionId?: string | null,
  token?: string,
): PreviewFile {
  const fileName = typeof file === "string" ? file : file.name;
  const normalizedFileName = workspacePathToFilename(fileName);
  const declaredType = typeof file === "string" ? undefined : file.type;
  const type = inferPreviewType(normalizedFileName, declaredType);
  const filePath = `/workspace/${normalizedFileName}`;
  const previewUrlOptions = getPreviewUrlOptions(type);

  return {
    name: normalizedFileName,
    type,
    url: sessionId
      ? resolveWorkspaceFileUrl(filePath, sessionId, token, previewUrlOptions)
      : "",
    downloadUrl: sessionId
      ? resolveWorkspaceDownloadUrl(filePath, sessionId, token)
      : "",
    size: typeof file === "string" ? undefined : file.size,
    mtime: typeof file === "string" ? undefined : file.mtime,
    absolute_path: typeof file === "string" ? undefined : file.absolute_path,
    resource_type: typeof file === "string" ? undefined : file.resource_type,
    schema_kind: typeof file === "string" ? undefined : file.schema_kind,
    preview_kind: typeof file === "string" ? undefined : file.preview_kind,
    renderer_hint: typeof file === "string" ? undefined : file.renderer_hint,
    meta: typeof file === "string" ? undefined : file.meta,
  };
}

export function createGlobalWorkspacePreviewFile(
  file: WorkspacePreviewFileSource,
  workspaceId?: string | null,
  token?: string,
): PreviewFile {
  const fileName = typeof file === "string" ? file : file.name;
  const normalizedFileName = workspacePathToFilename(fileName);
  const declaredType = typeof file === "string" ? undefined : file.type;
  const type = inferPreviewType(normalizedFileName, declaredType);
  const previewUrlOptions = getPreviewUrlOptions(type);
  const sourceMeta = typeof file === "string" ? undefined : file.meta;
  const meta = {
    ...(sourceMeta ?? {}),
    _globalResource: true,
    workspace_id: workspaceId,
    relative_path: normalizedFileName,
  };

  return {
    name: normalizedFileName,
    type,
    url: workspaceId
      ? resolveGlobalWorkspaceFileUrl(
          normalizedFileName,
          workspaceId,
          token,
          previewUrlOptions,
        )
      : "",
    downloadUrl: workspaceId
      ? resolveGlobalWorkspaceDownloadUrl(normalizedFileName, workspaceId, token)
      : "",
    size: typeof file === "string" ? undefined : file.size,
    mtime: typeof file === "string" ? undefined : file.mtime,
    absolute_path: typeof file === "string" ? undefined : file.absolute_path,
    resource_type: typeof file === "string" ? undefined : file.resource_type,
    schema_kind: typeof file === "string" ? undefined : file.schema_kind,
    preview_kind: typeof file === "string" ? undefined : file.preview_kind,
    renderer_hint: typeof file === "string" ? undefined : file.renderer_hint,
    meta,
  };
}

export function resolveWorkspaceFileUrl(
  path: string,
  sessionId?: string,
  token?: string,
  options?: {
    disposition?: "attachment" | "inline";
    preferDirectBackend?: boolean;
  },
): string {
  const cleanPath = stripApiBaseUrl(path || "");
  const isAbsoluteHttpUrl = /^[a-z]+:\/\//i.test(cleanPath);
  const disposition = options?.disposition ?? "attachment";
  const apiBase = resolveFileApiBaseUrl(options?.preferDirectBackend ?? false);

  if (isAbsoluteHttpUrl) {
    return appendAccessToken(cleanPath, token);
  }

  const resolvedSessionId = inferWorkspaceSessionId(sessionId);
  if (!resolvedSessionId) {
    return appendAccessToken(cleanPath, token);
  }

  const userId = getCurrentUserId();
  const filename = cleanPath.startsWith("/workspace/")
    ? workspacePathToFilename(cleanPath)
    : workspacePathToFilename(cleanPath);
  const searchParams = new URLSearchParams({
    user_id: userId,
    disposition,
  });

  // 为内嵌预览追加稳定参数，避免旧 tab 继续复用历史被阻断的缓存响应。
  if (disposition === "inline") {
    searchParams.set("preview_mode", "embed_v1");
  }

  const url =
    `${apiBase}${API_ENDPOINTS.FILES_DOWNLOAD(userId, resolvedSessionId, filename)}?${searchParams.toString()}`;

  return appendAccessToken(url, token);
}

export function resolveGlobalWorkspaceFileUrl(
  path: string,
  workspaceId: string,
  token?: string,
  options?: {
    disposition?: "attachment" | "inline";
    preferDirectBackend?: boolean;
  },
): string {
  const cleanPath = stripApiBaseUrl(path || "");
  const isAbsoluteHttpUrl = /^[a-z]+:\/\//i.test(cleanPath);
  const disposition = options?.disposition ?? "attachment";
  const apiBase = resolveFileApiBaseUrl(options?.preferDirectBackend ?? false);

  if (isAbsoluteHttpUrl) {
    return appendAccessToken(cleanPath, token);
  }

  const filename = workspacePathToFilename(cleanPath);
  const searchParams = new URLSearchParams({ disposition });
  if (disposition === "inline") {
    searchParams.set("preview_mode", "embed_v1");
  }

  const url =
    `${apiBase}${API_ENDPOINTS.GLOBAL_WORKSPACE_DOWNLOAD(workspaceId, filename)}?${searchParams.toString()}`;

  return appendAccessToken(url, token);
}

export function resolveWorkspaceDownloadUrl(
  path: string,
  sessionId?: string,
  token?: string,
): string {
  return resolveWorkspaceFileUrl(path, sessionId, token, {
    disposition: "attachment",
  });
}

export function resolveGlobalWorkspaceDownloadUrl(
  path: string,
  workspaceId: string,
  token?: string,
): string {
  return resolveGlobalWorkspaceFileUrl(path, workspaceId, token, {
    disposition: "attachment",
  });
}

export async function fetchWorkspaceTextContent(
  path: string,
  sessionId?: string,
  token?: string,
): Promise<string> {
  const url = resolveWorkspaceFileUrl(path, sessionId, token);
  const response = await apiFetch(url);

  if (!response.ok) {
    throw new Error(`读取文件失败: ${response.status}`);
  }

  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const data = await response.json();
    return JSON.stringify(data, null, 2);
  }

  return await response.text();
}
