import React from "react";

interface TopBarProps {
  sessionId?: string | null;
  sessionTitle?: string | null;
  workspaceTitle?: string | null;
  locked?: boolean;
  hostingActive?: boolean;
}

export const TopBar: React.FC<TopBarProps> = ({
  sessionId,
  sessionTitle,
  workspaceTitle,
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

  return (
    <div className="flex shrink-0 flex-col">
      <div className="flex items-center justify-between gap-3 px-5 pb-3 pt-4">
        <div className="flex min-w-0 items-center gap-3">
          <div className="min-w-0 text-xs text-muted-foreground truncate">
            {displayTitle}
          </div>
        </div>
      </div>
    </div>
  );
};
