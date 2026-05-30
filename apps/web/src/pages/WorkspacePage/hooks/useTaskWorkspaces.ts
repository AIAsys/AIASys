import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getTaskWorkspace, listTaskWorkspaces } from "@/lib/api/workspaces";
import type { TaskWorkspaceSummary } from "../types";
import { subscribeWorkspaceListRefresh } from "./workspaceListRefreshEvent";

interface UseTaskWorkspacesOptions {
  currentSessionId?: string | null;
}

function workspaceHasSession(
  workspace: TaskWorkspaceSummary,
  sessionId?: string | null,
): boolean {
  if (!sessionId) {
    return false;
  }

  return (
    workspace.current_conversation?.session_id === sessionId ||
    (workspace.conversations || []).some(
      (conversation) => conversation.session_id === sessionId,
    )
  );
}

function toMillis(value?: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

function getWorkspaceActivityTimestamp(workspace: TaskWorkspaceSummary): number {
  const conversationTimestamps = (workspace.conversations || []).map((conversation) =>
    toMillis(conversation.updated_at),
  );
  return Math.max(
    toMillis(workspace.updated_at),
    toMillis(workspace.current_conversation?.updated_at ?? null),
    ...conversationTimestamps,
  );
}

export function useTaskWorkspaces({
  currentSessionId,
}: UseTaskWorkspacesOptions) {
  const [workspaces, setWorkspaces] = useState<TaskWorkspaceSummary[]>([]);
  // 首次渲染前还没有完成工作区列表首轮拉取，必须视作 loading，
  // 否则 /workspace?workspace_id=... 会在首帧被误判成无效路由并提前清掉。
  const [isLoadingWorkspaces, setIsLoadingWorkspaces] = useState(true);
  const latestLoadRequestRef = useRef(0);
  const routeWorkspaceId =
    typeof window === "undefined" ||
    window.location.pathname.replace(/\/+$/, "") !== "/workspace"
      ? undefined
      : new URLSearchParams(window.location.search).get("workspace_id") || undefined;

  const loadWorkspaces = useCallback(async (): Promise<TaskWorkspaceSummary[]> => {
    const requestId = latestLoadRequestRef.current + 1;
    latestLoadRequestRef.current = requestId;

    // 在异步回调内部读取最新 URL，避免将 routeWorkspaceId 放入 deps 导致频繁重建
    const currentRouteWorkspaceId =
      typeof window === "undefined" ||
      window.location.pathname.replace(/\/+$/, "") !== "/workspace"
        ? undefined
        : new URLSearchParams(window.location.search).get("workspace_id") || undefined;

    setIsLoadingWorkspaces(true);
    try {
      const next = await listTaskWorkspaces();
      const routeWorkspace = currentRouteWorkspaceId
        ? next.find((workspace) => workspace.workspace_id === currentRouteWorkspaceId)
        : undefined;

      if (
        currentRouteWorkspaceId &&
        currentSessionId &&
        routeWorkspace &&
        !workspaceHasSession(routeWorkspace, currentSessionId) &&
        (routeWorkspace.conversations?.length ?? 0) < routeWorkspace.conversation_count
      ) {
        try {
          const detail = await getTaskWorkspace(currentRouteWorkspaceId);
          const detailHasRouteSession = workspaceHasSession(detail, currentSessionId);
          if (detailHasRouteSession) {
            const targetIndex = next.findIndex(
              (workspace) => workspace.workspace_id === currentRouteWorkspaceId,
            );
            if (targetIndex >= 0) {
              next[targetIndex] = detail;
            }
          }
        } catch (error) {
          console.warn("Failed to hydrate route workspace detail:", error);
        }
      }

      next.sort(
        (left, right) => getWorkspaceActivityTimestamp(right) - getWorkspaceActivityTimestamp(left),
      );
      if (requestId === latestLoadRequestRef.current) {
        setWorkspaces(next);
      }
      return next;
    } catch (error) {
      console.error("Failed to load workspaces:", error);
      if (requestId === latestLoadRequestRef.current) {
        setWorkspaces([]);
      }
      return [];
    } finally {
      if (requestId === latestLoadRequestRef.current) {
        setIsLoadingWorkspaces(false);
      }
    }
  }, [currentSessionId]);

  useEffect(() => {
    void loadWorkspaces();
  }, [loadWorkspaces]);

  useEffect(() => {
    return subscribeWorkspaceListRefresh(loadWorkspaces);
  }, [loadWorkspaces]);

  const currentWorkspaceId = useMemo(() => {
    const routeWorkspaceExists = routeWorkspaceId
      ? workspaces.some((workspace) => workspace.workspace_id === routeWorkspaceId)
      : false;

    if (!currentSessionId) {
      if (!routeWorkspaceId) {
        return undefined;
      }
      return isLoadingWorkspaces || routeWorkspaceExists
        ? routeWorkspaceId
        : undefined;
    }
    const matched = workspaces.find((workspace) =>
      (workspace.conversations || []).some(
        (conversation) => conversation.session_id === currentSessionId,
      ) ||
      workspace.current_conversation?.session_id === currentSessionId,
    );
    if (matched?.workspace_id) {
      return matched.workspace_id;
    }
    if (!routeWorkspaceId) {
      return undefined;
    }
    return isLoadingWorkspaces || routeWorkspaceExists
      ? routeWorkspaceId
      : undefined;
  }, [currentSessionId, isLoadingWorkspaces, routeWorkspaceId, workspaces]);

  const currentWorkspace = useMemo(
    () =>
      workspaces.find((workspace) => workspace.workspace_id === currentWorkspaceId),
    [currentWorkspaceId, workspaces],
  );

  useEffect(() => {
    if (!currentWorkspace?.workspace_id) {
      return;
    }

    const knownConversationCount = currentWorkspace.conversations?.length ?? 0;
    if (knownConversationCount >= currentWorkspace.conversation_count) {
      return;
    }

    let cancelled = false;

    void getTaskWorkspace(currentWorkspace.workspace_id)
      .then((detail) => {
        if (cancelled) {
          return;
        }
        setWorkspaces((previous) =>
          previous.map((workspace) =>
            workspace.workspace_id === detail.workspace_id ? detail : workspace,
          ),
        );
      })
      .catch((error) => {
        if (!cancelled) {
          console.warn("Failed to hydrate current workspace detail:", error);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [
    currentWorkspace?.conversation_count,
    currentWorkspace?.conversations,
    currentWorkspace?.workspace_id,
  ]);

  return {
    workspaces,
    isLoadingWorkspaces,
    currentWorkspaceId,
    currentWorkspace,
    loadWorkspaces,
  };
}
