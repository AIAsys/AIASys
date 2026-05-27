import { useCallback, useEffect, useRef } from "react";
import type { UseCodeExecutorReturn } from "../../../hooks/useCodeExecutor/executorTypes";
import type { TaskWorkspaceSummary } from "../../../types";

function workspaceHasSession(
  workspace: TaskWorkspaceSummary | undefined,
  sessionId: string | null | undefined,
): boolean {
  if (!workspace || !sessionId) {
    return false;
  }
  return (
    workspace.current_conversation?.session_id === sessionId ||
    Boolean(
      workspace.conversations?.some(
        (conversation) => conversation.session_id === sessionId,
      ),
    )
  );
}

function getPreferredWorkspaceSessionId(
  workspace: TaskWorkspaceSummary | undefined,
): string | null {
  if (!workspace) {
    return null;
  }
  return (
    workspace.current_conversation?.session_id ||
    workspace.conversations?.[0]?.session_id ||
    null
  );
}

function workspaceConversationListIncomplete(
  workspace: TaskWorkspaceSummary | undefined,
): boolean {
  if (!workspace) {
    return false;
  }

  return (workspace.conversations?.length ?? 0) < workspace.conversation_count;
}

function shouldPreserveRouteSessionDuringHydration(
  workspace: TaskWorkspaceSummary | undefined,
  routeSessionId: string | null,
): boolean {
  if (!workspace || !routeSessionId) {
    return false;
  }

  return (
    !workspaceHasSession(workspace, routeSessionId) &&
    workspaceConversationListIncomplete(workspace)
  );
}

interface UseAnalysisRouteSyncParams {
  currentWorkspace?: TaskWorkspaceSummary;
  currentWorkspaceId?: string;
  executor: Pick<UseCodeExecutorReturn, "handleSelectSession" | "sessionId">;
  isLoadingWorkspaces: boolean;
  leaveProjectWorkspace: () => void;
  workspaces: TaskWorkspaceSummary[];
}

interface UseAnalysisRouteSyncReturn {
  navigateToWorkspaceConversation: (
    workspaceId: string,
    sessionId: string,
  ) => void;
}

export function useAnalysisRouteSync({
  currentWorkspace,
  currentWorkspaceId,
  executor,
  isLoadingWorkspaces,
  leaveProjectWorkspace,
  workspaces,
}: UseAnalysisRouteSyncParams): UseAnalysisRouteSyncReturn {
  const handledWorkspaceRouteRef = useRef<string | null>(null);
  const analysisWorkspaceIdFromRoute =
    typeof window === "undefined" ||
    window.location.pathname.replace(/\/+$/, "") !== "/analysis"
      ? null
      : new URLSearchParams(window.location.search).get("workspace_id");
  const analysisSessionIdFromRoute =
    typeof window === "undefined" ||
    window.location.pathname.replace(/\/+$/, "") !== "/analysis"
      ? null
      : new URLSearchParams(window.location.search).get("session_id");

  const navigateToWorkspaceConversation = useCallback(
    (workspaceId: string, sessionId: string) => {
      const nextUrl = `/analysis?workspace_id=${encodeURIComponent(
        workspaceId,
      )}&session_id=${encodeURIComponent(sessionId)}`;
      const withAppNavigate = window as Window & {
        appNavigate?: (path: string, options?: { replace?: boolean }) => void;
      };
      if (withAppNavigate.appNavigate) {
        withAppNavigate.appNavigate(nextUrl, { replace: true });
        return;
      }
      window.location.replace(nextUrl);
    },
    [],
  );

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (window.location.pathname.replace(/\/+$/, "") !== "/analysis") {
      return;
    }

    const nextSearch = new URLSearchParams(window.location.search);
    let changed = false;
    const sessionBelongsToCurrentWorkspace = workspaceHasSession(
      currentWorkspace,
      executor.sessionId,
    );
    const preserveRouteSessionDuringHydration =
      shouldPreserveRouteSessionDuringHydration(
        currentWorkspace,
        analysisSessionIdFromRoute,
      );
    const preferredWorkspaceSessionId =
      getPreferredWorkspaceSessionId(currentWorkspace);
    const routeWorkspaceStillExists = Boolean(
      analysisWorkspaceIdFromRoute &&
      workspaces.some(
        (workspace) => workspace.workspace_id === analysisWorkspaceIdFromRoute,
      ),
    );
    const preserveRouteWorkspaceContext =
      isLoadingWorkspaces || routeWorkspaceStillExists;
    const routeSwitchingToAnotherWorkspace = Boolean(
      analysisWorkspaceIdFromRoute &&
      currentWorkspaceId &&
      analysisWorkspaceIdFromRoute !== currentWorkspaceId &&
      routeWorkspaceStillExists,
    );
    const routeSwitchingToAnotherSession = Boolean(
      analysisWorkspaceIdFromRoute &&
      currentWorkspaceId &&
      analysisWorkspaceIdFromRoute === currentWorkspaceId &&
      analysisSessionIdFromRoute &&
      analysisSessionIdFromRoute !== executor.sessionId &&
      workspaceHasSession(currentWorkspace, analysisSessionIdFromRoute),
    );

    // 当用户刚点击左侧工作区切换时，先保留路由上的目标工作区，
    // 或者刚在当前工作区内切到另一个会话时，先保留目标 session，
    // 让后续 effect 去消费这次切换，而不是立刻被旧前台 session 写回去。
    if (routeSwitchingToAnotherWorkspace || routeSwitchingToAnotherSession) {
      return;
    }

    if (!currentWorkspaceId) {
      if (!preserveRouteWorkspaceContext && nextSearch.has("workspace_id")) {
        nextSearch.delete("workspace_id");
        changed = true;
      }
      const shouldKeepSessionRoute =
        Boolean(analysisSessionIdFromRoute) &&
        (analysisSessionIdFromRoute === executor.sessionId ||
          preserveRouteWorkspaceContext);
      if (!shouldKeepSessionRoute && nextSearch.has("session_id")) {
        nextSearch.delete("session_id");
        changed = true;
      }
    } else {
      if (nextSearch.get("workspace_id") !== currentWorkspaceId) {
        nextSearch.set("workspace_id", currentWorkspaceId);
        changed = true;
      }
      const nextSessionId =
        sessionBelongsToCurrentWorkspace && executor.sessionId
          ? executor.sessionId
          : preserveRouteSessionDuringHydration
            ? analysisSessionIdFromRoute
            : preferredWorkspaceSessionId;
      if (nextSessionId && nextSearch.get("session_id") !== nextSessionId) {
        nextSearch.set("session_id", nextSessionId);
        changed = true;
      } else if (!nextSessionId && nextSearch.has("session_id")) {
        nextSearch.delete("session_id");
        changed = true;
      }
    }

    if (!changed) {
      return;
    }

    const nextUrl = nextSearch.toString()
      ? `/analysis?${nextSearch.toString()}`
      : "/analysis";
    const withAppNavigate = window as Window & {
      appNavigate?: (path: string, options?: { replace?: boolean }) => void;
    };
    withAppNavigate.appNavigate?.(nextUrl, { replace: true });
  }, [
    analysisSessionIdFromRoute,
    analysisWorkspaceIdFromRoute,
    currentWorkspace,
    currentWorkspaceId,
    executor.sessionId,
    isLoadingWorkspaces,
    workspaces,
  ]);

  useEffect(() => {
    if (!analysisWorkspaceIdFromRoute) {
      handledWorkspaceRouteRef.current = null;
      return;
    }

    if (isLoadingWorkspaces || workspaces.length === 0) {
      return;
    }

    const routeKey = `${analysisWorkspaceIdFromRoute}:${analysisSessionIdFromRoute ?? ""}`;
    if (handledWorkspaceRouteRef.current === routeKey) {
      return;
    }

    const targetWorkspace = workspaces.find(
      (workspace) => workspace.workspace_id === analysisWorkspaceIdFromRoute,
    );
    if (
      shouldPreserveRouteSessionDuringHydration(
        targetWorkspace,
        analysisSessionIdFromRoute,
      )
    ) {
      return;
    }

    handledWorkspaceRouteRef.current = routeKey;
    const routeSessionBelongsToWorkspace = workspaceHasSession(
      targetWorkspace,
      analysisSessionIdFromRoute,
    );
    const activeSessionBelongsToWorkspace = workspaceHasSession(
      targetWorkspace,
      executor.sessionId,
    );
    const targetSessionId = routeSessionBelongsToWorkspace
      ? analysisSessionIdFromRoute
      : getPreferredWorkspaceSessionId(targetWorkspace);

    if (
      analysisWorkspaceIdFromRoute === currentWorkspaceId &&
      activeSessionBelongsToWorkspace &&
      (!analysisSessionIdFromRoute ||
        analysisSessionIdFromRoute === executor.sessionId)
    ) {
      return;
    }

    if (
      targetWorkspace?.workspace_id &&
      targetSessionId &&
      (!routeSessionBelongsToWorkspace ||
        (!activeSessionBelongsToWorkspace && !analysisSessionIdFromRoute)) &&
      analysisSessionIdFromRoute !== targetSessionId
    ) {
      leaveProjectWorkspace();
      void executor.handleSelectSession(targetSessionId, { silent: true });
      return;
    }

    if (!targetSessionId || targetSessionId === executor.sessionId) {
      return;
    }

    leaveProjectWorkspace();
    void executor.handleSelectSession(targetSessionId, { silent: true });
  }, [
    analysisSessionIdFromRoute,
    analysisWorkspaceIdFromRoute,
    currentWorkspaceId,
    executor,
    isLoadingWorkspaces,
    leaveProjectWorkspace,
    navigateToWorkspaceConversation,
    workspaces,
  ]);

  return {
    navigateToWorkspaceConversation,
  };
}
