import React from "react";
import { SquareArrowOutUpRight } from "lucide-react";

interface TopBarProps {
  sessionId?: string | null;
  sessionTitle?: string | null;
  workspaceTitle?: string | null;
  workspaceId?: string | null;
  locked?: boolean;
  hostingActive?: boolean;
}

function openWorkspaceInNewWindow(workspaceId?: string | null, sessionId?: string | null) {
  const desktop = window.__AIASYS_DESKTOP__;
  if (!desktop?.openWorkspaceWindow) {
    return;
  }
  void desktop.openWorkspaceWindow({
    workspaceId: workspaceId ?? undefined,
    sessionId: sessionId ?? undefined,
  });
}

export const TopBar: React.FC<TopBarProps> = ({
  sessionId,
  sessionTitle,
  workspaceTitle,
  workspaceId,
  locked: _locked = false,
}) => {
  const hasSession = Boolean(sessionId);
  const normalizedSessionTitle =
    sessionTitle && sessionTitle.trim().length > 0
      ? sessionTitle.trim()
      : null;
  const displayPrimaryTitle = normalizedSessionTitle
    ? normalizedSessionTitle
    : hasSession
      ? "未命名会话"
      : "当前暂无可用会话";
  const displayTitle = workspaceTitle?.trim() || displayPrimaryTitle;
  const isDesktop =
    typeof window !== "undefined" &&
    Boolean(window.__AIASYS_DESKTOP__?.openWorkspaceWindow);

  return (
    <div className="flex shrink-0 flex-col">
      <div className="flex items-center justify-between gap-3 px-5 pb-3 pt-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0 text-xs text-muted-foreground truncate">
            {displayTitle}
          </div>
        </div>
        {isDesktop && workspaceId ? (
          <button
            type="button"
            onClick={() => openWorkspaceInNewWindow(workspaceId, sessionId)}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            title="在新窗口打开当前工作区"
            aria-label="在新窗口打开当前工作区"
          >
            <SquareArrowOutUpRight className="h-3.5 w-3.5" />
          </button>
        ) : null}
      </div>
    </div>
  );
};
