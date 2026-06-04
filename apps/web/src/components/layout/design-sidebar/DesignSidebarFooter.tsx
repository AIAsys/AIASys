import { useState, useRef } from "react";
import { isSingleUserAuthMode } from "@/config/auth";
import { LogOut, Settings } from "lucide-react";
import { SettingsPanel } from "./SettingsPanel";
import type { SettingsSection } from "@/components/settings/global-settings";

interface DesignSidebarFooterProps {
  avatarChar: string;
  avatarColor: string;
  displayName: string;
  isAuthenticated: boolean;
  onEditProfile: () => void;
  onOpenGlobalSettings?: (section: SettingsSection) => void;
  onLogout: () => void;
}

export function DesignSidebarFooter({
  avatarChar,
  avatarColor,
  displayName,
  isAuthenticated,
  onEditProfile,
  onOpenGlobalSettings,
  onLogout,
}: DesignSidebarFooterProps) {
  const showLogout = isAuthenticated && !isSingleUserAuthMode();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const settingsRef = useRef<HTMLDivElement>(null);

  const toggleSettings = () => setIsSettingsOpen((prev) => !prev);

  return (
    <div className="p-4 border-t border-sidebar-border">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onEditProfile}
          title="编辑个人资料"
          className={`w-8 h-8 rounded-full ${avatarColor} flex items-center justify-center hover:opacity-90 transition-opacity flex-shrink-0`}
        >
          <span className="text-sm font-medium text-white">{avatarChar}</span>
        </button>
        <button
          type="button"
          onClick={onEditProfile}
          title={displayName}
          className="font-medium truncate hover:text-sidebar-primary transition-colors text-left flex-1 min-w-0"
        >
          {displayName}
        </button>
        <div className="flex items-center gap-1 flex-shrink-0">
          {isAuthenticated && (
            <>
              <div ref={settingsRef} className="relative">
                <button
                  type="button"
                  data-testid="sidebar-workspace-tools-menu-trigger"
                  onMouseDown={(e) => e.stopPropagation()}
                  onClick={toggleSettings}
                  className="p-1.5 rounded text-muted-foreground hover:text-sidebar-primary hover:bg-sidebar-accent transition-colors"
                  title="设置"
                >
                  <Settings className="w-4 h-4" />
                </button>
                <div className="absolute bottom-full right-0 mb-1 z-50">
                  <SettingsPanel
                    open={isSettingsOpen}
                    onClose={() => setIsSettingsOpen(false)}
                    onOpenGlobalSettings={onOpenGlobalSettings}
                  />
                </div>
              </div>
              {showLogout ? (
                <button
                  type="button"
                  onClick={onLogout}
                  className="p-1.5 rounded text-muted-foreground hover:text-destructive hover:bg-sidebar-accent transition-colors"
                  title="退出登录"
                >
                  <LogOut className="w-4 h-4" />
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
