import { apiRequest } from "@/lib/api/httpClient";

interface DraftCleanupResponse {
  total?: number;
}

interface AvailableDraftResponse {
  available?: boolean;
  session_id?: string;
  age_seconds?: number;
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

export async function requestAvailableDraftId(
  apiBaseUrl: string,
): Promise<string | null> {
  try {
    const data = await apiRequest<AvailableDraftResponse>(`${apiBaseUrl}/api/sessions/available-draft`);
    if (data.available && data.session_id) {
      return data.session_id;
    }
    return null;
  } catch {
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
    const conversationId = options?.conversationId ?? _sessionId;
    if (conversationId) {
      url.searchParams.set("conversation_id", conversationId);
    }
  } else if (_sessionId) {
    url.searchParams.set("session_id", _sessionId);
  }
  withAppNavigate.appNavigate?.(`${url.pathname}${url.search}`, { replace: true });
}
