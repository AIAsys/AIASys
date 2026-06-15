import {
  History,
  PanelLeftOpen,
  Plus,
  Settings,
} from "lucide-react";
import { BrandLogo } from "@/components/branding/BrandLogo";
import {
  CollapsedIconButton,
} from "./DesignSidebarPrimitives";
import type { SettingsSection } from "@/components/settings/global-settings";

interface DesignSidebarCollapsedProps {
  avatarChar: string;
  avatarColor: string;
  displayName: string;
  onExpand?: () => void;
  onNewTask?: () => void;
  onOpenGlobalSettings?: (section: SettingsSection) => void;
  onEditProfile: () => void;
}

export function DesignSidebarCollapsed({
  avatarChar,
  avatarColor,
  displayName,
  onExpand,
  onNewTask,
  onOpenGlobalSettings,
  onEditProfile,
}: DesignSidebarCollapsedProps) {
  return (
    <div className="absolute inset-0 flex flex-col items-center py-4 transition-opacity duration-200 delay-200 opacity-100">
      <div className="mb-3 flex-shrink-0">
        <BrandLogo variant="mark" alt="艾斯" className="w-7 h-7 object-contain" href="/" />
      </div>

      <CollapsedIconButton
        icon={<PanelLeftOpen className="w-[18px] h-[18px]" />}
        tooltip="展开侧边栏"
        onClick={onExpand}
      />

      <div className="mt-2 mb-1">
        <button
          type="button"
          data-testid="sidebar-new-task-collapsed"
          onClick={onNewTask}
          className="w-9 h-9 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 flex items-center justify-center transition-colors"
          title="新建工作区"
        >
          <Plus className="w-[18px] h-[18px]" />
        </button>
      </div>
      <div className="w-6 my-2 border-t border-sidebar-border" />

      <CollapsedIconButton
        icon={<History className="w-[18px] h-[18px]" />}
        tooltip="工作区列表"
        onClick={onExpand}
      />

      <div className="flex-1" />

      <div className="border-t border-sidebar-border pt-3 flex flex-col items-center gap-1">
        <button
          type="button"
          data-testid="sidebar-workspace-tools-menu-trigger-collapsed"
          onMouseDown={(e) => e.stopPropagation()}
          onClick={() => onOpenGlobalSettings?.("llm")}
          className="w-9 h-9 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors"
          title="全局控制面板"
        >
          <Settings className="w-[18px] h-[18px]" />
        </button>
        <button
          type="button"
          onClick={onEditProfile}
          title={displayName}
          className={`w-8 h-8 rounded-full ${avatarColor} flex items-center justify-center hover:opacity-90 transition-opacity`}
        >
          <span className="text-sm font-medium text-white">{avatarChar}</span>
        </button>
      </div>
    </div>
  );
}
