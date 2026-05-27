/**
 * SidebarContainer - 侧边栏容器
 *
 * 处理侧边栏的整体布局和拖拽功能
 * 支持收起/展开状态
 */
import { PanelRight } from "lucide-react";
import { useSidebarContext } from "./context";
import { useSidebarResize } from "./useSidebarResize";

interface SidebarContainerProps {
  children: React.ReactNode;
}

export function SidebarContainer({ children }: SidebarContainerProps) {
  const {
    state: { width, isOpen },
    actions: { onWidthChange, onClose, onOpen },
  } = useSidebarContext();

  const { handleDragStart } = useSidebarResize(width, onWidthChange);

  // 收起状态：显示一个可点击的窄条
  if (!isOpen) {
    // onClose 在展开状态下使用，这里静音 lint 警告
    void onClose;
    return (
      <div
        data-testid="execution-space-collapsed-toggle"
        className="border-l border-border bg-muted hover:bg-accent flex flex-col items-center justify-center gap-2 h-full w-9 cursor-pointer transition-colors z-30 group"
        onClick={onOpen}
        title="展开工作区侧栏"
      >
        <PanelRight
          size={16}
          className="text-muted-foreground group-hover:text-foreground transition-colors"
        />
        <span className="text-[10px] text-muted-foreground group-hover:text-foreground font-medium writing-mode-vertical whitespace-nowrap transition-colors [writing-mode:vertical-rl]">
          工作区侧栏
        </span>
      </div>
    );
  }

  return (
    <>
      <div
        data-testid="execution-space-sidebar"
        className="border-l border-border bg-background flex flex-col h-full shadow-2xl z-30 pointer-events-auto animate-in slide-in-from-right duration-300 relative overflow-hidden"
        style={{ width: `${width}px`, maxWidth: `${width}px` }}
      >
        {/* 拖拽手柄 */}
        <div
          className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-border transition-colors group"
          onMouseDown={handleDragStart}
        >
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-transparent group-hover:bg-border" />
        </div>

        {children}
      </div>
    </>
  );
}
