import { useCallback, useState } from "react";
import { API_BASE_URL, API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiFetch, apiRequest } from "@/lib/api/httpClient";

export type BackendFileInfo = {
  filename: string;
  file_path: string;
  size: number;
  modified_at: number;
};

export type BackendSessionInfo = {
  session_id: string;
  workspace_id?: string | null;
  file_count: number;
  updated_at: number;
};

interface UseFileImportProps {
  baseUrl?: string;
  targetSessionId: string;
  targetWorkspaceId?: string | null;
  onImportSuccess?: () => void;
}

const SOURCE_FILE_LIST_PAGE_SIZE = 500;

export function useFileImport({
  baseUrl = API_BASE_URL,
  targetSessionId,
  targetWorkspaceId,
  onImportSuccess,
}: UseFileImportProps) {
  const [sessions, setSessions] = useState<BackendSessionInfo[]>([]);
  const [sourceSessionFiles, setSourceSessionFiles] = useState<
    BackendFileInfo[]
  >([]);
  const [isLoadingSessions, setIsLoadingSessions] = useState(false);
  const [isLoadingSourceFiles, setIsLoadingSourceFiles] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const toUnixSeconds = (value: unknown): number => {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value > 1_000_000_000_000
        ? Math.floor(value / 1000)
        : Math.floor(value);
    }
    if (typeof value === "string") {
      const parsed = Date.parse(value);
      if (!Number.isNaN(parsed)) {
        return Math.floor(parsed / 1000);
      }
    }
    return Math.floor(Date.now() / 1000);
  };

  // 加载历史对话列表
  const loadSessions = useCallback(async () => {
    setIsLoadingSessions(true);
    setError(null);
    try {
      const userId = getCurrentUserId();
      const endpoint = `${baseUrl}/api/sessions/${userId}`;
      const payload = await apiRequest<{
        sessions?: Array<{
          session_id?: string;
          workspace_id?: string | null;
          workspace_file_count?: number;
          updated_at?: string | number | null;
          created_at?: string | number | null;
        }>;
      }>(endpoint);

      const normalized = Array.isArray(payload.sessions)
        ? payload.sessions
            .filter((item) => typeof item?.session_id === "string")
            .map((item) => ({
              session_id: item.session_id as string,
              workspace_id:
                typeof item.workspace_id === "string" ? item.workspace_id : null,
              file_count:
                typeof item.workspace_file_count === "number"
                  ? item.workspace_file_count
                  : 0,
              updated_at: toUnixSeconds(item.updated_at ?? item.created_at),
            }))
        : [];

      setSessions(normalized);
    } catch (e) {
      setError(`加载历史对话失败: ${(e as Error).message}`);
    } finally {
      setIsLoadingSessions(false);
    }
  }, [baseUrl]);

  // 加载源对话的文件列表
  const loadSourceSessionFiles = useCallback(
    async (sid: string) => {
      const sourceId = sid.trim();
      if (!sourceId) return;

      setIsLoadingSourceFiles(true);
      setError(null);
      setSourceSessionFiles([]);

      try {
        const sourceWorkspaceId =
          sessions.find((session) => session.session_id === sourceId)?.workspace_id ?? null;
        if (!sourceWorkspaceId) {
          setSourceSessionFiles([]);
          setError("源对话未绑定工作区，无法从当前资源接口读取文件");
          return;
        }

        const files: BackendFileInfo[] = [];
        let offset = 0;
        let hasMore = true;

        while (hasMore) {
          const endpoint = `${baseUrl}${API_ENDPOINTS.WORKSPACE_FILE_LIST(
            sourceWorkspaceId,
            {
              recursive: true,
              limit: SOURCE_FILE_LIST_PAGE_SIZE,
              offset,
            },
          )}`;
          const payload = await apiRequest<{
            files?: Array<{
              name?: string;
              size?: number;
              modified?: number;
            }>;
            has_more?: boolean;
            next_offset?: number | null;
          }>(endpoint);
          const pageFiles = Array.isArray(payload.files)
            ? payload.files
                .filter((file) => typeof file?.name === "string")
                .map((file) => ({
                  filename: file.name as string,
                  file_path: `/workspace/${file.name}`,
                  size: typeof file.size === "number" ? file.size : 0,
                  modified_at:
                    typeof file.modified === "number" ? file.modified : Date.now(),
                }))
            : [];
          files.push(...pageFiles);
          if (payload.has_more && typeof payload.next_offset === "number") {
            offset = payload.next_offset;
          } else {
            hasMore = false;
          }
        }
        setSourceSessionFiles(files);
      } catch (e) {
        setError(`加载源对话文件失败: ${(e as Error).message}`);
      } finally {
        setIsLoadingSourceFiles(false);
      }
    },
    [baseUrl, sessions],
  );

  // 导入选中的文件
  const importFiles = useCallback(
    async (sourceSessionId: string, filenames: string[]) => {
      if (!targetSessionId || !targetWorkspaceId || !sourceSessionId || filenames.length === 0)
        return;

      setIsImporting(true);
      setError(null);
      try {
        const sourceWorkspaceId =
          sessions.find((session) => session.session_id === sourceSessionId)?.workspace_id ?? null;
        if (!sourceWorkspaceId) {
          throw new Error("源对话未绑定工作区，无法导入文件");
        }
        const imported: string[] = [];

        for (const filename of filenames) {
          const downloadEndpoint =
            `${baseUrl}${API_ENDPOINTS.WORKSPACE_FILE_DOWNLOAD(sourceWorkspaceId, filename)}`;
          const downloadResponse = await apiFetch(downloadEndpoint, {
            method: "GET",
          });

          if (!downloadResponse.ok) {
            const detail = await downloadResponse.text();
            throw new Error(
              `下载源文件失败 (${filename}): ${downloadResponse.status} - ${detail}`,
            );
          }

          const blob = await downloadResponse.blob();
          const formData = new FormData();
          formData.append("file", blob, filename);

          const uploadEndpoint =
            `${baseUrl}${API_ENDPOINTS.WORKSPACE_FILE_UPLOAD(targetWorkspaceId)}`;
          const uploadResponse = await apiFetch(uploadEndpoint, {
            method: "POST",
            body: formData,
          });

          if (!uploadResponse.ok) {
            const detail = await uploadResponse.text();
            throw new Error(
              `导入目标对话失败 (${filename}): ${uploadResponse.status} - ${detail}`,
            );
          }

          imported.push(filename);
        }

        const result = {
          success: true,
          imported_files: imported,
          source_session_id: sourceSessionId,
          target_session_id: targetSessionId,
        };
        onImportSuccess?.();
        return result;
      } catch (e) {
        setError(`导入失败: ${(e as Error).message}`);
        throw e;
      } finally {
        setIsImporting(false);
      }
    },
    [baseUrl, targetSessionId, targetWorkspaceId, sessions, onImportSuccess],
  );

  return {
    sessions,
    sourceSessionFiles,
    isLoadingSessions,
    isLoadingSourceFiles,
    isImporting,
    error,
    setError,
    loadSessions,
    loadSourceSessionFiles,
    importFiles,
  };
}
