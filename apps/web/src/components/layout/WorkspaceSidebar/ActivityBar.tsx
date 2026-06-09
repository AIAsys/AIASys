import type { ReactNode } from "react";
import { useRef, useState } from "react";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";

import { cn } from "@/lib/utils";

export interface ActivityBarItem<TView extends string> {
  id: TView;
  label: string;
  icon: ReactNode;
  disabled?: boolean;
}

interface ActivityBarProps<TView extends string> {
  items: Array<ActivityBarItem<TView>>;
  activeView: TView;
  isSidebarCollapsed: boolean;
  canToggleSidebar?: boolean;
  onSelectView: (view: TView) => void;
  onToggleSidebar: () => void;
  onReorder?: (newOrder: TView[]) => void;
}

export function ActivityBar<TView extends string>({
  items,
  activeView,
  isSidebarCollapsed,
  canToggleSidebar = true,
  onSelectView,
  onToggleSidebar,
  onReorder,
}: ActivityBarProps<TView>) {
  const toggleTitle = !canToggleSidebar
    ? "当前视图不使用侧栏"
    : isSidebarCollapsed
      ? "展开侧栏"
      : "收起侧栏";

  const [draggedId, setDraggedId] = useState<TView | null>(null);
  const draggedIdRef = useRef<TView | null>(null);
  const [dropTarget, setDropTarget] = useState<{
    id: TView;
    before: boolean;
  } | null>(null);
  const dragEndTimeRef = useRef<number>(0);

  const handleDragStart =
    (itemId: TView) => (e: React.DragEvent<HTMLButtonElement>) => {
      draggedIdRef.current = itemId;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", itemId);
      setDraggedId(itemId);
      setDropTarget(null);
    };

  const handleDragOver =
    (itemId: TView) => (e: React.DragEvent<HTMLButtonElement>) => {
      e.preventDefault();
      if (!draggedIdRef.current || draggedIdRef.current === itemId) return;

      e.dataTransfer.dropEffect = "move";
      const rect = e.currentTarget.getBoundingClientRect();
      const before = e.clientY < rect.top + rect.height / 2;

      setDropTarget((current) =>
        current?.id === itemId && current.before === before
          ? current
          : { id: itemId, before },
      );
    };

  const handleBarDragLeave = (event: React.DragEvent<HTMLElement>) => {
    const nextTarget = event.relatedTarget;
    if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
      setDropTarget(null);
    }
  };

  const handleDrop =
    (itemId: TView) => (e: React.DragEvent<HTMLButtonElement>) => {
      e.preventDefault();
      const draggedItemId = draggedIdRef.current;
      draggedIdRef.current = null;
      const currentDropTarget = dropTarget;
      setDraggedId(null);
      setDropTarget(null);

      if (!draggedItemId || draggedItemId === itemId || !onReorder) return;

      const before =
        currentDropTarget?.id === itemId
          ? currentDropTarget.before
          : e.clientY <
            e.currentTarget.getBoundingClientRect().top +
              e.currentTarget.getBoundingClientRect().height / 2;

      const draggedItem = items.find((i) => i.id === draggedItemId);
      if (!draggedItem) return;

      const nextItems = items.filter((i) => i.id !== draggedItemId);
      const targetIndex = nextItems.findIndex((i) => i.id === itemId);
      if (targetIndex === -1) return;

      const insertIndex = before ? targetIndex : targetIndex + 1;
      nextItems.splice(insertIndex, 0, draggedItem);

      const unchanged = nextItems.every((item, index) => item.id === items[index]?.id);
      if (unchanged) return;

      onReorder(nextItems.map((i) => i.id));
    };

  const handleDragEnd = () => {
    draggedIdRef.current = null;
    dragEndTimeRef.current = Date.now();
    setDraggedId(null);
    setDropTarget(null);
  };

  return (
    <aside
      className="flex h-full w-12 shrink-0 flex-col items-center border-r border-border bg-sidebar py-2 text-sidebar-foreground"
      onDragLeave={handleBarDragLeave}
    >
      <div className="flex flex-1 flex-col items-center gap-1">
        {items.map((item) => {
          const active = item.id === activeView;
          const isDragged = draggedId === item.id;
          const showBefore =
            dropTarget?.id === item.id && dropTarget.before && !isDragged;
          const showAfter =
            dropTarget?.id === item.id && !dropTarget.before && !isDragged;

          return (
            <div key={item.id} className="relative flex flex-col items-center transition-all duration-200 ease-in-out">
              {showBefore && (
                <div className="absolute -top-[3px] left-1 right-1 z-10 h-0.5 rounded-full bg-tertiary" />
              )}
              <button
                type="button"
                title={item.label}
                aria-label={item.label}
                aria-pressed={active}
                disabled={item.disabled}
                draggable
                onClick={() => {
                  if (Date.now() - dragEndTimeRef.current < 300) return;
                  onSelectView(item.id);
                }}
                onDragStart={handleDragStart(item.id)}
                onDragOver={handleDragOver(item.id)}
                onDrop={handleDrop(item.id)}
                onDragEnd={handleDragEnd}
                className={cn(
                  "relative flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors",
                  "hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  !item.disabled && "cursor-grab active:cursor-grabbing",
                  active && "bg-background text-foreground shadow-sm ring-1 ring-border/50",
                  item.disabled && "cursor-not-allowed opacity-50",
                  isDragged && "opacity-40",
                )}
              >
                {active && !isDragged ? (
                  <span className="absolute left-0 top-2 h-6 w-0.5 rounded-full bg-tertiary" />
                ) : null}
                {item.icon}
              </button>
              {showAfter && (
                <div className="absolute -bottom-[3px] left-1 right-1 z-10 h-0.5 rounded-full bg-tertiary" />
              )}
            </div>
          );
        })}
      </div>

      <button
        type="button"
        title={toggleTitle}
        aria-label={toggleTitle}
        disabled={!canToggleSidebar}
        onClick={onToggleSidebar}
        className={cn(
          "flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-background hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          !canToggleSidebar && "cursor-not-allowed opacity-40",
        )}
      >
        {isSidebarCollapsed ? (
          <PanelLeftOpen className="h-4 w-4" />
        ) : (
          <PanelLeftClose className="h-4 w-4" />
        )}
      </button>
    </aside>
  );
}
