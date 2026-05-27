import { useCallback, useEffect, useState } from "react";

export type WorkspaceSidebarTab =
  | "subagents"
  | "artifacts"
  | "terminal";

export interface SidebarTabRequest {
  tab: WorkspaceSidebarTab;
  key: number;
  targetWorkspaceId?: string | null;
}

export function useSidebarTabRequest(currentWorkspaceId?: string) {
  const [activeTabRequest, setActiveTabRequest] =
    useState<SidebarTabRequest | null>(null);

  const requestSidebarTab = useCallback(
    (tab: WorkspaceSidebarTab, targetWorkspaceId?: string | null) => {
      setActiveTabRequest({
        tab,
        key: Date.now(),
        targetWorkspaceId: targetWorkspaceId ?? currentWorkspaceId ?? null,
      });
    },
    [currentWorkspaceId],
  );

  useEffect(() => {
    if (!activeTabRequest) {
      return;
    }
    if (
      activeTabRequest.targetWorkspaceId &&
      activeTabRequest.targetWorkspaceId !== currentWorkspaceId
    ) {
      return;
    }

    const timeoutId = window.setTimeout(() => {
      setActiveTabRequest((currentRequest) =>
        currentRequest?.key === activeTabRequest.key ? null : currentRequest,
      );
    }, 0);

    return () => window.clearTimeout(timeoutId);
  }, [activeTabRequest, currentWorkspaceId]);

  return {
    activeTabRequest,
    requestSidebarTab,
  };
}
