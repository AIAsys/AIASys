import type { ReactNode } from "react";
import { ChevronLeft, GripVertical } from "lucide-react";

import { cn } from "@/lib/utils";

interface ActivitySidebarProps {
  title: string;
  width: number;
  isCollapsed: boolean;
  isResizing: boolean;
  children: ReactNode;
  onCollapse: () => void;
  onResizeStart: (event: React.MouseEvent<HTMLDivElement>) => void;
}

export function ActivitySidebar({
  title,
  width,
  isCollapsed,
  isResizing,
  children,
  onCollapse,
  onResizeStart,
}: ActivitySidebarProps) {
  return (
    <aside
      aria-hidden={isCollapsed}
      className={cn(
        "relative flex h-full min-h-0 shrink-0 flex-col bg-background",
        isCollapsed ? "overflow-hidden border-r-0" : "border-r border-border",
        isResizing ? "" : "transition-[width] duration-150",
      )}
      style={{ width: isCollapsed ? 0 : width }}
    >
      {!isCollapsed ? (
        <div className="flex h-12 shrink-0 items-center justify-between gap-2 border-b border-border px-3">
          <div className="min-w-0 truncate text-xs font-semibold text-foreground">
            {title}
          </div>
          <button
            type="button"
            title="收起侧栏"
            aria-label="收起侧栏"
            onClick={onCollapse}
            className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </div>
      ) : null}

      <div className={cn("min-h-0 flex-1 overflow-hidden", isCollapsed && "hidden")}>
        {children}
      </div>

      {!isCollapsed ? (
        <div
          role="separator"
          aria-orientation="vertical"
          title="拖拽调整侧栏宽度"
          className="absolute -right-1 top-0 z-20 flex h-full w-2 cursor-col-resize items-center justify-center"
          onMouseDown={onResizeStart}
        >
          <div
            className={cn(
              "h-full w-px bg-border transition-colors",
              isResizing && "bg-tertiary",
            )}
          />
          <GripVertical className="absolute h-3.5 w-3.5 text-transparent transition-colors hover:text-muted-foreground" />
        </div>
      ) : null}
    </aside>
  );
}
