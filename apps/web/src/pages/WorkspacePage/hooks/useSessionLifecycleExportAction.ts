import { useCallback } from "react";
import { API_ENDPOINTS } from "@/config/api";
import { apiFetch } from "@/lib/api/httpClient";
import type { SessionExportScope } from "@/types/sessionExport";
import {
  downloadBlob,
  getDownloadFilename,
} from "./sessionLifecycleManagerUtils";
import type { SessionLifecycleActionContext } from "./sessionLifecycleManagerActionTypes";

export function useSessionLifecycleExportAction({
  apiBaseUrl,
  userId,
  exportingSessionId,
  showSuccess,
  showError,
  setExportingSessionId,
}: Pick<
  SessionLifecycleActionContext,
  | "apiBaseUrl"
  | "userId"
  | "exportingSessionId"
  | "showSuccess"
  | "showError"
  | "setExportingSessionId"
>) {
  return useCallback(
    async (targetSessionId: string, scope: SessionExportScope) => {
      if (!targetSessionId || exportingSessionId) {
        return;
      }

      setExportingSessionId(targetSessionId);
      try {
        const exportUrl = `${apiBaseUrl}${API_ENDPOINTS.SESSION_EXPORT(
          userId,
          targetSessionId,
        )}?scope=${scope}`;
        const response = await apiFetch(exportUrl);

        if (!response.ok) {
          let detail = `导出失败: ${response.status}`;
          try {
            const payload = (await response.json()) as { detail?: string };
            if (payload.detail) {
              detail = payload.detail;
            }
          } catch {
            // keep fallback
          }
          throw new Error(detail);
        }

        const blob = await response.blob();
        const fallbackFilename =
          scope === "conversation"
            ? `session_conversation_${targetSessionId}.json`
            : `session_export_${targetSessionId}_${scope}.zip`;
        downloadBlob(blob, getDownloadFilename(response, fallbackFilename));

        const successMessage =
          scope === "conversation"
            ? "对话记录 JSON 导出成功"
            : scope === "workspace"
              ? "工作区 ZIP 导出成功"
              : "会话审计包导出成功";
        showSuccess(successMessage);
      } catch (error) {
        console.error("Session export failed:", error);
        showError(error instanceof Error ? error.message : "会话导出失败");
      } finally {
        setExportingSessionId((current) =>
          current === targetSessionId ? null : current,
        );
      }
    },
    [
      apiBaseUrl,
      exportingSessionId,
      setExportingSessionId,
      showError,
      showSuccess,
      userId,
    ],
  );
}
