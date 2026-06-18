/**
 * Agent 文件上传 Hook
 *
 * 用于上传、管理和删除当前任务工作区中的文件。
 * 前端仍按 session 缓存待发送附件，网络请求统一使用 workspace API。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiRequest, ApiRequestError } from "@/lib/api/httpClient";
import type {
  FileInfo,
  FileListResponse,
  FileUploadResponse,
} from "@/types/api";

/** 上传文件信息 */
export interface UploadedFile {
  filename: string;
  file_path: string;
  size: number;
  mtime?: string;
  absolute_path?: string | null;
  resource_type?: "knowledge" | "database" | "graph" | string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
  progress?: number;
}

/** 失败的上传记录（保留原始 File 对象用于重试） */
export interface FailedUpload {
  id: string;
  file: File;
  filename: string;
  error: string;
  sessionId: string;
  workspaceId?: string | null;
}

/** 上传状态 */
export interface UploadState {
  isUploading: boolean;
  files: UploadedFile[];
  error?: string;
  /** 当前上传进度 0-100，null 表示不在上传中 */
  uploadProgress: number | null;
  /** 当前 session 的失败上传列表 */
  failedUploads: FailedUpload[];
}

/** Hook 配置选项 */
export interface UseAgentFileUploadOptions {
  /** 后端基础 URL */
  baseUrl?: string;
  /** 上传成功回调 */
  onUploadSuccess?: (file: UploadedFile) => void;
  /** 上传失败回调 */
  onUploadError?: (error: string) => void;
}

const FILE_LIST_CACHE_TTL_MS = 3000;
const FILE_LIST_PAGE_SIZE = 500;
const CACHE_MAX_SIZE = 50;
const CACHE_EXPIRE_MS = 5 * 60 * 1000;
const workspaceFileListInFlightByEndpoint = new Map<string, Promise<FileInfo[]>>();
const workspaceFileListCacheByEndpoint = new Map<
  string,
  { files: FileInfo[]; loadedAt: number }
>();

function cleanupFileListCache(): void {
  const now = Date.now();
  for (const [key, value] of workspaceFileListCacheByEndpoint.entries()) {
    if (now - value.loadedAt > CACHE_EXPIRE_MS) {
      workspaceFileListCacheByEndpoint.delete(key);
      workspaceFileListInFlightByEndpoint.delete(key);
    }
  }
  if (workspaceFileListCacheByEndpoint.size > CACHE_MAX_SIZE) {
    const entries = Array.from(workspaceFileListCacheByEndpoint.entries());
    entries.sort((a, b) => a[1].loadedAt - b[1].loadedAt);
    const toDelete = entries.slice(0, entries.length - CACHE_MAX_SIZE);
    for (const [key] of toDelete) {
      workspaceFileListCacheByEndpoint.delete(key);
      workspaceFileListInFlightByEndpoint.delete(key);
    }
  }
}

/**
 * 使用 XMLHttpRequest 上传文件，支持进度回调。
 * 相比 fetch，XHR 的 upload.onprogress 可以获取上传字节进度。
 */
async function uploadFileWithProgress(
  url: string,
  formData: FormData,
  onProgress?: (percent: number) => void,
): Promise<Response> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url);
    xhr.withCredentials = true;

    xhr.upload.onprogress = (e: ProgressEvent) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      // 构造一个类 Response 对象，与 apiFetch 返回行为一致
      const response = new Response(xhr.responseText, {
        status: xhr.status,
        statusText: xhr.statusText,
        headers: (() => {
          const h = new Headers();
          const headerStr = xhr.getAllResponseHeaders();
          if (headerStr) {
            for (const line of headerStr.trim().split(/\r?\n/)) {
              const idx = line.indexOf(": ");
              if (idx > 0) {
                h.append(line.slice(0, idx), line.slice(idx + 2));
              }
            }
          }
          return h;
        })(),
      });
      resolve(response);
    };

    xhr.onerror = () => {
      reject(new Error("网络错误，上传失败"));
    };

    xhr.ontimeout = () => {
      reject(new Error("上传超时"));
    };

    xhr.send(formData);
  });
}

/**
 * Agent 文件上传 Hook — 支持 per-session 附件隔离
 */
export function useAgentFileUpload(options: UseAgentFileUploadOptions = {}) {
  const { baseUrl = "", onUploadSuccess, onUploadError } = options;

  const [state, setState] = useState<UploadState>({
    isUploading: false,
    files: [],
    uploadProgress: null,
    failedUploads: [],
  });

  // Per-session 文件附件 Map
  const filesMapRef = useRef<Map<string, UploadedFile[]>>(new Map());
  // Per-session 失败上传 Map
  const failedUploadsMapRef = useRef<Map<string, FailedUpload[]>>(new Map());
  const activeSessionIdRef = useRef<string>("");
  const filesRef = useRef<UploadedFile[]>([]);
  const failedUploadsRef = useRef<FailedUpload[]>([]);

  // Keep refs in sync with state to avoid stale closure in switchSession
  useEffect(() => {
    filesRef.current = state.files;
  }, [state.files]);

  useEffect(() => {
    failedUploadsRef.current = state.failedUploads;
  }, [state.failedUploads]);

  const invalidateFileListCache = useCallback((workspaceId: string) => {
    const endpointPrefix =
      baseUrl + `/api/workspaces/${encodeURIComponent(workspaceId)}/files/list`;
    for (const key of workspaceFileListCacheByEndpoint.keys()) {
      if (key.startsWith(endpointPrefix)) {
        workspaceFileListCacheByEndpoint.delete(key);
      }
    }
    for (const key of workspaceFileListInFlightByEndpoint.keys()) {
      if (key.startsWith(endpointPrefix)) {
        workspaceFileListInFlightByEndpoint.delete(key);
      }
    }
  }, [baseUrl]);

  /** 设置活跃 session ID */
  const setActiveSessionId = useCallback((sessionId: string) => {
    activeSessionIdRef.current = sessionId;
  }, []);

  /** 切换 session 时同步文件状态 */
  const switchSession = useCallback(
    (fromId: string, toId: string) => {
      if (fromId === toId) return;

      // 保存当前 session 的 pending files
      if (fromId) {
        filesMapRef.current.set(fromId, [...filesRef.current]);
        failedUploadsMapRef.current.set(fromId, [...failedUploadsRef.current]);
      }

      // 加载目标 session 的 pending files
      const targetFiles = filesMapRef.current.get(toId) || [];
      const targetFailed = failedUploadsMapRef.current.get(toId) || [];
      setState((prev) => ({
        ...prev,
        files: targetFiles,
        failedUploads: targetFailed,
      }));
      activeSessionIdRef.current = toId;
    },
    [],
  );

  /** 移除 session 的文件数据 */
  const removeSession = useCallback((sessionId: string) => {
    filesMapRef.current.delete(sessionId);
    failedUploadsMapRef.current.delete(sessionId);
  }, []);

  /**
   * 获取文件列表
   */
  const listFiles = useCallback(
    async (
      workspaceId: string,
      options?: { force?: boolean },
    ): Promise<FileInfo[]> => {
      const endpoint = baseUrl + API_ENDPOINTS.WORKSPACE_FILE_LIST(workspaceId, {
        recursive: true,
        limit: FILE_LIST_PAGE_SIZE,
      });
      const cached = workspaceFileListCacheByEndpoint.get(endpoint);
      if (
        !options?.force &&
        cached &&
        Date.now() - cached.loadedAt < FILE_LIST_CACHE_TTL_MS
      ) {
        return cached.files;
      }

      const inFlight = workspaceFileListInFlightByEndpoint.get(endpoint);
      if (inFlight) {
        return inFlight;
      }

      const request: Promise<FileInfo[]> = (async () => {
        const files: FileInfo[] = [];
        let offset = 0;
        let hasMore = true;

        while (hasMore) {
          const pageEndpoint = baseUrl + API_ENDPOINTS.WORKSPACE_FILE_LIST(
            workspaceId,
            {
              recursive: true,
              limit: FILE_LIST_PAGE_SIZE,
              offset,
            },
          );
          try {
            const data = await apiRequest<FileListResponse>(pageEndpoint);
            files.push(...(data.files || []));

            if (data.has_more && typeof data.next_offset === "number") {
              offset = data.next_offset;
            } else {
              hasMore = false;
            }
          } catch (err) {
            if (err instanceof ApiRequestError && err.status === 404) {
              // 工作区不存在时返回空列表
              hasMore = false;
            } else {
              throw err;
            }
          }
        }

        return files;
      })()
        .then((files) => {
          cleanupFileListCache();
          workspaceFileListCacheByEndpoint.set(endpoint, {
            files,
            loadedAt: Date.now(),
          });
          return files;
        })
        .catch((err) => {
          const errorMsg = err instanceof Error ? err.message : "未知错误";
          if (errorMsg.includes("404")) {
            return [];
          }
          onUploadError?.(errorMsg);
          return [];
        })
        .finally(() => {
          if (workspaceFileListInFlightByEndpoint.get(endpoint) === request) {
            workspaceFileListInFlightByEndpoint.delete(endpoint);
          }
        });

      workspaceFileListInFlightByEndpoint.set(endpoint, request);
      return request;
    },
    [baseUrl, onUploadError],
  );

  /**
   * 刷新工作区文件列表
   */
  const reloadWorkspaceFiles = useCallback(
    async (
      workspaceId?: string,
      options?: { force?: boolean },
    ): Promise<UploadedFile[]> => {
      if (!workspaceId) return [];

      const files = await listFiles(workspaceId, options);
      const uploadedFiles: UploadedFile[] = files.map((f) => ({
        filename: f.name,
        file_path: `/workspace/${f.name}`,
        size: f.size,
        mtime: new Date(f.modified * 1000).toISOString(),
        absolute_path: f.absolute_path,
        resource_type: f.resource_type,
        schema_kind: f.schema_kind,
        preview_kind: f.preview_kind,
        renderer_hint: f.renderer_hint,
        meta: f.meta,
      }));

      return uploadedFiles;
    },
    [listFiles],
  );

  /**
   * 上传单个文件
   */
  const uploadFile = useCallback(
    async (
      file: File,
      sessionId: string,
      workspaceId?: string | null,
    ): Promise<UploadedFile | null> => {
      if (!workspaceId) {
        onUploadError?.("未绑定工作区，无法上传文件");
        return null;
      }

      setState((prev) => ({
        ...prev,
        isUploading: true,
        uploadProgress: 0,
        error: undefined,
      }));

      try {
        const endpoint =
          baseUrl + API_ENDPOINTS.WORKSPACE_FILE_UPLOAD(workspaceId);

        const formData = new FormData();
        formData.append("file", file);

        const response = await uploadFileWithProgress(
          endpoint,
          formData,
          (percent) => {
            setState((prev) => ({
              ...prev,
              uploadProgress: percent,
            }));
          },
        );

        if (!response.ok) {
          throw new Error(`上传失败: ${response.status}`);
        }

        invalidateFileListCache(workspaceId);
        const data: FileUploadResponse = await response.json();
        const uploadedFile: UploadedFile = {
          filename: data.filename,
          file_path: data.path,
          size: data.size,
        };

        // 只更新活跃 session 的 state
        if (sessionId === activeSessionIdRef.current) {
          setState((prev) => ({
            ...prev,
            isUploading: false,
            uploadProgress: null,
            files: [...prev.files, uploadedFile],
          }));
        } else {
          // 后台 session 只更新 Map
          const current = filesMapRef.current.get(sessionId) || [];
          filesMapRef.current.set(sessionId, [...current, uploadedFile]);
          setState((prev) => ({ ...prev, isUploading: false, uploadProgress: null }));
        }

        onUploadSuccess?.(uploadedFile);
        return uploadedFile;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        if (errorMsg.includes("404")) {
          // 工作区不存在，不可重试
          setState((prev) => ({
            ...prev,
            isUploading: false,
            uploadProgress: null,
          }));
          return null;
        }

        // 记录失败上传，保留原始 File 对象供重试
        const failedEntry: FailedUpload = {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          file,
          filename: file.name,
          error: errorMsg,
          sessionId,
          workspaceId,
        };
        if (sessionId === activeSessionIdRef.current) {
          setState((prev) => ({
            ...prev,
            isUploading: false,
            uploadProgress: null,
            error: errorMsg,
            failedUploads: [...prev.failedUploads, failedEntry],
          }));
        } else {
          const current = failedUploadsMapRef.current.get(sessionId) || [];
          failedUploadsMapRef.current.set(sessionId, [...current, failedEntry]);
          setState((prev) => ({
            ...prev,
            isUploading: false,
            uploadProgress: null,
          }));
        }
        onUploadError?.(errorMsg);
        return null;
      }
    },
    [baseUrl, invalidateFileListCache, onUploadSuccess, onUploadError],
  );

  /**
   * 删除文件或目录
   */
  const deleteFile = useCallback(
    async (
      filename: string,
      sessionId: string,
      workspaceId?: string | null,
      recursive?: boolean,
    ): Promise<boolean> => {
      if (!workspaceId) {
        onUploadError?.("未绑定工作区，无法删除文件");
        return false;
      }

      try {
        let endpoint =
          baseUrl + API_ENDPOINTS.WORKSPACE_FILE_DELETE(workspaceId, filename);
        if (recursive) {
          endpoint += "?recursive=true";
        }

        await apiRequest<{ success?: boolean; detail?: string }>(endpoint, {
          method: "DELETE",
        });
        invalidateFileListCache(workspaceId);

        // 从状态中移除
        if (sessionId === activeSessionIdRef.current) {
          setState((prev) => ({
            ...prev,
            files: prev.files.filter((f) =>
              recursive
                ? f.filename !== filename && !f.filename.startsWith(`${filename}/`)
                : f.filename !== filename,
            ),
          }));
        } else {
          const current = filesMapRef.current.get(sessionId) || [];
          filesMapRef.current.set(
            sessionId,
            current.filter((f) =>
              recursive
                ? f.filename !== filename && !f.filename.startsWith(`${filename}/`)
                : f.filename !== filename,
            ),
          );
        }

        return true;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        if (errorMsg.includes("404")) {
          return false;
        }
        onUploadError?.(errorMsg);
        return false;
      }
    },
    [baseUrl, invalidateFileListCache, onUploadError],
  );

  /**
   * 移除文件（仅从状态）
   */
  const removeFile = useCallback(
    async (filePath: string, sessionId?: string, workspaceId?: string | null) => {
      const filename = filePath.split(/[/\\]/).pop();
      if (!filename || !sessionId || !workspaceId) return;

      // 乐观更新前保存旧状态
      let previousFiles: UploadedFile[] = [];
      setState((prev) => {
        previousFiles = prev.files;
        return {
          ...prev,
          files: prev.files.filter((f) => f.file_path !== filePath),
        };
      });

      // 调用后端删除
      try {
        await deleteFile(filename, sessionId, workspaceId);
      } catch {
        // 后端删除失败，恢复文件到 UI
        setState((prev) => ({
          ...prev,
          files: previousFiles,
        }));
        onUploadError?.("文件删除失败");
      }
    },
    [deleteFile, onUploadError],
  );

  /**
   * 清空所有文件和失败上传（活跃 session）
   */
  const clearFiles = useCallback(() => {
    setState((prev) => ({ ...prev, files: [], failedUploads: [] }));
  }, []);

  /**
   * 重试某个失败的上传
   */
  const retryUpload = useCallback(
    async (id: string): Promise<void> => {
      const failed = failedUploadsRef.current.find((f) => f.id === id);
      if (!failed) return;

      // 先从失败列表移除（乐观更新）
      if (failed.sessionId === activeSessionIdRef.current) {
        setState((prev) => ({
          ...prev,
          failedUploads: prev.failedUploads.filter((f) => f.id !== id),
        }));
      } else {
        const current = failedUploadsMapRef.current.get(failed.sessionId) || [];
        failedUploadsMapRef.current.set(
          failed.sessionId,
          current.filter((f) => f.id !== id),
        );
      }

      // 重新上传，成功/失败由 uploadFile 内部处理
      await uploadFile(failed.file, failed.sessionId, failed.workspaceId);
    },
    [uploadFile],
  );

  /**
   * 移除某个失败的上传记录
   */
  const removeFailedUpload = useCallback((id: string) => {
    setState((prev) => ({
      ...prev,
      failedUploads: prev.failedUploads.filter((f) => f.id !== id),
    }));
  }, []);

  /**
   * 获取文件名列表
   */
  const getFileNames = useCallback(() => {
    return state.files.map((f) => f.filename);
  }, [state.files]);

  /**
   * 移动/重命名工作区文件
   */
  const moveFile = useCallback(
    async (
      source: string,
      target: string,
      _sessionId: string,
      workspaceId?: string | null,
    ): Promise<boolean> => {
      if (!workspaceId) {
        onUploadError?.("未绑定工作区，无法移动文件");
        return false;
      }

      try {
        const endpoint = baseUrl + API_ENDPOINTS.WORKSPACE_FILE_MOVE(workspaceId);
        await apiRequest<{ success: boolean }>(endpoint, {
          method: "PUT",
          body: { source, target },
        });
        invalidateFileListCache(workspaceId);
        return true;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        if (errorMsg.includes("404")) {
          return false;
        }
        onUploadError?.(errorMsg);
        return false;
      }
    },
    [baseUrl, invalidateFileListCache, onUploadError],
  );

  /**
   * 删除工作区文件或目录
   */
  const deleteWorkspaceFile = useCallback(
    async (
      filename: string,
      sessionId?: string,
      workspaceId?: string | null,
      recursive?: boolean,
    ): Promise<boolean> => {
      if (!sessionId || !workspaceId) return false;
      return deleteFile(filename, sessionId, workspaceId, recursive);
    },
    [deleteFile],
  );

  /**
   * 读取工作区文件内容
   */
  const readWorkspaceFileContent = useCallback(
    async (filename: string, workspaceId?: string | null): Promise<string | null> => {
      if (!workspaceId) {
        onUploadError?.("未绑定工作区，无法读取文件内容");
        return null;
      }

      try {
        const endpoint =
          baseUrl + API_ENDPOINTS.WORKSPACE_FILE_CONTENT(workspaceId, filename);
        const data = await apiRequest<{ content: string }>(endpoint);
        return data.content;
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : "未知错误";
        if (errorMsg.includes("404")) {
          return "";
        }
        onUploadError?.(errorMsg);
        return null;
      }
    },
    [baseUrl, onUploadError],
  );

  /**
   * 刷新文件列表
   */
  const refreshFiles = useCallback(
    async (workspaceId: string): Promise<void> => {
      await reloadWorkspaceFiles(workspaceId);
    },
    [reloadWorkspaceFiles],
  );

  return {
    state,
    uploadProgress: state.uploadProgress,
    failedUploads: state.failedUploads,
    listFiles,
    reloadWorkspaceFiles,
    uploadFile,
    deleteFile,
    moveFile,
    removeFile,
    clearFiles,
    getFileNames,
    refreshFiles,
    deleteWorkspaceFile,
    readWorkspaceFileContent,
    switchSession,
    setActiveSessionId,
    removeSession,
    retryUpload,
    removeFailedUpload,
  };
}
