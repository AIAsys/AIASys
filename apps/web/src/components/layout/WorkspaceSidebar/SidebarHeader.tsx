import { Button } from "@/components/ui/button";
import {
  Download,
  Loader2,
  Terminal,
  User,
  X,
} from "lucide-react";
import React from "react";

interface SidebarHeaderProps {
  sessionId?: string;
  sessionTitle?: string | null;
  isExporting: boolean;
  // Worker session 相关
  boundLeadSessionId?: string | null;
  onSwitchToLeadSession?: () => void;
  onExport: () => void;
  onClose: () => void;
}

export const SidebarHeader: React.FC<SidebarHeaderProps> = ({
  sessionId,
  sessionTitle: _sessionTitle,
  isExporting,
  boundLeadSessionId,
  onSwitchToLeadSession,
  onExport,
  onClose,
}) => {
  // 是否显示切换到主控会话按钮：仅当绑定了主控时才显示
  const canSwitchToLead = Boolean(boundLeadSessionId) && Boolean(onSwitchToLeadSession);
  void _sessionTitle;

  return (
    <div className="border-b border-border bg-muted">
      <div className="flex items-center justify-between px-4 py-2.5 pl-6">
        <div className="flex items-center gap-2">
          <Terminal size={15} className="text-foreground" />
          <h2 className="text-sm font-semibold text-foreground">当前工作区</h2>
        </div>
        <div className="flex items-center gap-0.5">
          {sessionId ? (
            <button
              onClick={onExport}
              disabled={isExporting}
              className={`flex items-center gap-1 rounded-md p-1.5 transition-all ${
                isExporting
                  ? "cursor-not-allowed text-muted-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              }`}
              title="导出当前工作区为 ZIP"
            >
              {isExporting ? (
                <Loader2 size={15} className="animate-spin" />
              ) : (
                <Download size={15} />
              )}
            </button>
          ) : null}
          <button
            onClick={onClose}
            className="p-1.5 text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Close Sidebar"
          >
            <X size={18} />
          </button>
        </div>
      </div>

      {sessionId && canSwitchToLead ? (
        <div
          data-testid="execution-space-session-summary"
          className="px-4 pb-3 pl-6"
        >
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 gap-1.5 text-[11px]"
            onClick={() => {
              void onSwitchToLeadSession?.();
            }}
          >
            <User className="h-3.5 w-3.5" />
            <span>切换到主控会话</span>
          </Button>
        </div>
      ) : null}
    </div>
  );
};
