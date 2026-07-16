import { apiRequest } from "@/lib/api/httpClient";
import { DEFAULT_CONVERSATION_TITLE } from "@/lib/conversationTitles";

interface DraftCleanupResponse {
  total?: number;
}

interface CreateSessionResponse {
  session_id?: string;
  title?: string;
}

type AppNavigateWindow = typeof globalThis & {
  appNavigate?: (path: string, options?: { replace?: boolean }) => void;
};

interface NavigateToAnalysisSessionOptions {
  workspaceId?: string | null;
  conversationId?: string | null;
}

export async function requestDraftCleanup(
  apiBaseUrl: string,
  currentSessionId: string,
): Promise<number> {
  try {
    const data = await apiRequest<DraftCleanupResponse>(`${apiBaseUrl}/api/sessions/cleanup-drafts`, {
      method: "POST",
      body: {
      currentSessionId,
      },
    });
    return data.total || 0;
  } catch {
    return 0;
  }
}

export async function requestCreateSession(
  apiBaseUrl: string,
  sessionId: string,
  workspaceId?: string | null,
  title?: string,
): Promise<CreateSessionResponse | null> {
  try {
    const data = await apiRequest<CreateSessionResponse>(
      `${apiBaseUrl}/api/sessions/create`,
      {
        method: "POST",
        body: {
          session_id: sessionId,
          workspace_id: workspaceId || undefined,
          title: title || DEFAULT_CONVERSATION_TITLE,
          status: "active",
        },
      },
    );
    return data ?? null;
  } catch (err) {
    console.warn("[Session] 创建后端会话失败:", err);
    return null;
  }
}

function getCurrentWorkspaceId(): string | null {
  if (globalThis.location.pathname.replace(/\/+$/, "") !== "/workspace") {
    return null;
  }

  return new URLSearchParams(globalThis.location.search).get("workspace_id");
}

function getCurrentRoutePrefix(): string {
  const path = globalThis.location.pathname.replace(/\/+$/, "");
  if (path === "/workspace") return "/workspace";
  return "/workspace";
}

export function navigateToAnalysisSession(
  _sessionId: string,
  options?: NavigateToAnalysisSessionOptions,
) {
  const withAppNavigate = globalThis as AppNavigateWindow;
  const routePrefix = getCurrentRoutePrefix();
  const url = new URL(routePrefix, globalThis.location.origin);
  const workspaceId =
    options?.workspaceId === undefined
      ? getCurrentWorkspaceId()
      : options.workspaceId;

  if (workspaceId) {
    url.searchParams.set("workspace_id", workspaceId);
    // 同时写入 session_id 和 conversation_id，确保刷新后能正确恢复对话
    if (_sessionId) {
      url.searchParams.set("session_id", _sessionId);
    }
    const conversationId = options?.conversationId ?? _sessionId;
    if (conversationId) {
      url.searchParams.set("conversation_id", conversationId);
    }
  } else if (_sessionId) {
    url.searchParams.set("session_id", _sessionId);
  }
  withAppNavigate.appNavigate?.(`${url.pathname}${url.search}`, { replace: true });
}
