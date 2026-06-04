import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type { SessionHistoryMessage, SessionStatusInfo } from "@/pages/WorkspacePage/types";

export interface RewriteSessionMessageResponse {
  success: boolean;
  message_id: string;
  dropped_count: number;
  archive?: {
    archived_at?: string;
    archive_file?: string;
  } | null;
  messages?: SessionHistoryMessage[];
  current_messages?: SessionHistoryMessage[];
  session?: SessionStatusInfo;
}

export async function rewriteSessionFromMessage(
  apiBaseUrl: string,
  params: {
    userId: string;
    sessionId: string;
    messageId: string;
    content: string;
    confirmDropTail: boolean;
  },
): Promise<RewriteSessionMessageResponse> {
  const endpoint = API_ENDPOINTS.SESSION_REWRITE_FROM_MESSAGE(
    params.userId,
    params.sessionId,
  );
  return apiRequest<RewriteSessionMessageResponse>(`${apiBaseUrl}${endpoint}`, {
    method: "POST",
    body: {
      message_id: params.messageId,
      content: params.content,
      preserve_attachments: true,
      confirm_drop_tail: params.confirmDropTail,
    },
  });
}

export async function exportConversation(
  userId: string,
  sessionId: string,
): Promise<Blob> {
  const response = await fetch(
    API_ENDPOINTS.SESSION_EXPORT(userId, sessionId) + "?scope=conversation",
    {
      method: "GET",
      credentials: "include",
    },
  );
  if (!response.ok) {
    const detail = await response.text().catch(() => "导出失败");
    throw new Error(detail);
  }
  return response.blob();
}
