import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import {
  Braces,
  ChevronDown,
  FolderCog,
  LayoutTemplate,
  Puzzle,
  Server,
  ServerCog,
  Settings,
  Store,
  Terminal,
  Zap,
} from "lucide-react";
import { useAuthState } from "@/contexts/AuthContext";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import type { SettingsSection } from "@/components/settings/global-settings";

interface SettingsPanelProps {
  open: boolean;
  onClose: () => void;
  anchorRef?: React.RefObject<HTMLElement | null>;
  onOpenGlobalSettings?: (section: SettingsSection) => void;
}

function MenuItem({
  icon,
  label,
  onClick,
  testId,
  disabled,
  disabledTooltip,
}: {
  icon: React.ReactNode;
  label: string;
  onClick?: () => void;
  testId?: string;
  disabled?: boolean;
  disabledTooltip?: string;
}) {
  const content = (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      disabled={disabled}
      className={`w-full flex items-center gap-2 px-2.5 py-1.5 rounded-md text-sm transition-colors ${
        disabled
          ? "text-foreground opacity-50 cursor-not-allowed"
          : "text-foreground hover:bg-accent cursor-pointer"
      }`}
    >
      <span className="text-muted-foreground flex-shrink-0">{icon}</span>
      <span>{label}</span>
    </button>
  );

  if (disabled && disabledTooltip) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="block">{content}</span>
        </TooltipTrigger>
        <TooltipContent>{disabledTooltip}</TooltipContent>
      </Tooltip>
    );
  }

  return content;
}

function SectionHeader({
  label,
  collapsed,
  onToggle,
}: {
  label: string;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      className="w-full flex items-center gap-1.5 px-2 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
    >
      <ChevronDown
        className={`w-3 h-3 transition-transform ${collapsed ? "-rotate-90" : ""}`}
      />
      <span>{label}</span>
    </button>
  );
}

function Divider() {
  return <div className="my-1 h-px bg-border" />;
}

function SettingsPanelContent({
  open,
  onClose,
  onOpenGlobalSettings,
}: Omit<SettingsPanelProps, "anchorRef">) {
  const { user } = useAuthState();
  const userId = user?.id;
  const panelRef = useRef<HTMLDivElement>(null);
  const [collapsedSections, setCollapsedSections] = useState<Set<string>>(
    () => new Set(["tasks"]),
  );

  useEffect(() => {
    if (!open) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (
        panelRef.current &&
        !panelRef.current.contains(e.target as Node)
      ) {
        onClose();
      }
    };

    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [open, onClose]);

  const toggleSection = (key: string) => {
    setCollapsedSections((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div
      ref={panelRef}
      className="w-52 bg-background text-foreground border border-border shadow-md rounded-md p-1.5 animate-in fade-in-0 zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95"
      data-state={open ? "open" : "closed"}
    >
      {/* 全局控制面板总入口 */}
      <MenuItem
        icon={<Settings className="w-4 h-4" />}
        label="全局控制面板"
        testId="sidebar-workspace-tools-global-settings"
        onClick={() => {
          onClose();
          onOpenGlobalSettings?.("llm");
        }}
      />

      <Divider />

      {/* 能力市场 — expanded by default */}
      <SectionHeader
        label="能力市场"
        collapsed={collapsedSections.has("market")}
        onToggle={() => toggleSection("market")}
      />
      {!collapsedSections.has("market") && (
        <>
          <MenuItem
            icon={<Puzzle className="w-4 h-4" />}
            label="能力管理"
            testId="sidebar-workspace-tools-capabilities"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("capabilities");
            }}
          />
          <MenuItem
            icon={<Zap className="w-4 h-4" />}
            label="默认工具配置"
            testId="sidebar-workspace-tools-tool-strategy"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("tool-strategy");
            }}
          />
        </>
      )}

      <Divider />

      {/* 环境与配置 — expanded by default */}
      <SectionHeader
        label="环境与配置"
        collapsed={collapsedSections.has("env")}
        onToggle={() => toggleSection("env")}
      />
      {!collapsedSections.has("env") && (
        <>
          <MenuItem
            icon={<Server className="w-4 h-4" />}
            label="模型配置"
            testId="sidebar-workspace-tools-llm-config"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("llm");
            }}
          />
          <MenuItem
            icon={<Braces className="w-4 h-4" />}
            label="全局环境变量"
            testId="sidebar-workspace-tools-global-env-vars"
            disabled={!userId}
            disabledTooltip="需要登录"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("env-vars");
            }}
          />
          <MenuItem
            icon={<FolderCog className="w-4 h-4" />}
            label="存储位置"
            testId="sidebar-workspace-tools-storage-settings"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("storage");
            }}
          />
          <MenuItem
            icon={<ServerCog className="w-4 h-4" />}
            label="Python 与执行资源"
            testId="sidebar-workspace-tools-execution-resources"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("execution-resources");
            }}
          />
        </>
      )}

      <Divider />

      {/* 全局任务管理 — collapsed by default */}
      <SectionHeader
        label="全局任务管理"
        collapsed={collapsedSections.has("tasks")}
        onToggle={() => toggleSection("tasks")}
      />
      {!collapsedSections.has("tasks") && (
        <>
          <MenuItem
            icon={<Zap className="w-4 h-4" />}
            label="自动化任务"
            testId="sidebar-workspace-tools-auto-task-management"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("auto-tasks");
            }}
          />
          <MenuItem
            icon={<Terminal className="w-4 h-4" />}
            label="监控任务"
            testId="sidebar-workspace-tools-monitor-management"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("monitor-tasks");
            }}
          />
        </>
      )}

      <Divider />

      {/* 模板 — expanded by default */}
      <SectionHeader
        label="模板"
        collapsed={collapsedSections.has("templates")}
        onToggle={() => toggleSection("templates")}
      />
      {!collapsedSections.has("templates") && (
        <>
          <MenuItem
            icon={<Store className="w-4 h-4" />}
            label="模板市场"
            testId="sidebar-workspace-tools-template-market"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("template-market");
            }}
          />
          <MenuItem
            icon={<LayoutTemplate className="w-4 h-4" />}
            label="模板管理"
            testId="sidebar-workspace-tools-template-management"
            onClick={() => {
              onClose();
              onOpenGlobalSettings?.("template-management");
            }}
          />
        </>
      )}
    </div>
  );
}

export function SettingsPanel({
  open,
  anchorRef,
  ...rest
}: SettingsPanelProps) {
  const [style, setStyle] = useState<CSSProperties>({});

  useEffect(() => {
    if (!open || !anchorRef?.current) return;

    const rect = anchorRef.current.getBoundingClientRect();
    const panelWidth = 208; // w-52 = 13rem ≈ 208px
    const panelHeight = 420;

    let left = rect.right + 4;
    let top = rect.top;

    // If panel would go off the right edge, align to the left of the anchor
    if (left + panelWidth > window.innerWidth - 8) {
      left = rect.left - panelWidth - 4;
    }

    // If panel would go off the bottom, shift up
    if (top + panelHeight > window.innerHeight - 8) {
      top = Math.max(8, window.innerHeight - panelHeight - 8);
    }

    setStyle({
      position: "fixed",
      top,
      left,
      zIndex: 50,
    });
  }, [open, anchorRef]);

  if (!open) return null;

  const content = <SettingsPanelContent open={open} {...rest} />;

  if (anchorRef) {
    return createPortal(
      <div style={style}>{content}</div>,
      document.body,
    );
  }

  return content;
}
