import { useEffect, useRef, useState } from "react";
import { X, Columns2, Rows2, MoreHorizontal, Info } from "lucide-react";

interface CustomMenuItem {
  label: string;
  icon?: React.ReactNode;
  onClick: () => void;
  active?: boolean;
  variant?: "default" | "danger";
}

interface CanvasActionMenuProps {
  onClose: () => void;
  closeLabel?: string;
  onSplitRight?: () => void;
  onSplitDown?: () => void;
  onShowInfo?: () => void;
  infoActive?: boolean;
  customItems?: CustomMenuItem[];
}

export function CanvasActionMenu({
  onClose,
  closeLabel = "关闭标签",
  onSplitRight,
  onSplitDown,
  onShowInfo,
  infoActive = false,
  customItems,
}: CanvasActionMenuProps) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;

    const handlePointerDown = (event: PointerEvent) => {
      if (menuRef.current?.contains(event.target as Node)) return;
      setOpen(false);
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  const hasSplit = Boolean(onSplitRight || onSplitDown);

  return (
    <div className="relative">
      <button
        type="button"
        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        title="更多操作"
        aria-label="更多操作"
        aria-expanded={open}
        onClick={(event) => {
          event.stopPropagation();
          setOpen((current) => !current);
        }}
      >
        <MoreHorizontal className="h-4 w-4" />
      </button>

      {open ? (
        <div
          ref={menuRef}
          role="menu"
          className="absolute right-0 top-9 z-50 w-44 overflow-hidden rounded-xl border border-border bg-background p-1 text-xs text-foreground shadow-xl"
        >
          {hasSplit || onShowInfo || (customItems && customItems.length > 0) ? (
            <>
              {customItems?.map((item) => (
                <button
                  key={item.label}
                  type="button"
                  role="menuitem"
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent focus:bg-accent focus:outline-none ${item.active ? "bg-accent" : ""} ${item.variant === "danger" ? "text-error hover:bg-error-container focus:bg-error-container" : ""}`}
                  onClick={() => {
                    item.onClick();
                    setOpen(false);
                  }}
                >
                  {item.icon ? (
                    <span className="text-muted-foreground">{item.icon}</span>
                  ) : null}
                  {item.label}
                </button>
              ))}
              {onShowInfo ? (
                <button
                  type="button"
                  role="menuitem"
                  className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent focus:bg-accent focus:outline-none ${infoActive ? "bg-accent" : ""}`}
                  onClick={() => {
                    onShowInfo();
                    setOpen(false);
                  }}
                >
                  <Info className="h-3.5 w-3.5 text-muted-foreground" />
                  查看文件信息
                </button>
              ) : null}
              {onSplitRight ? (
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
                  onClick={() => {
                    onSplitRight();
                    setOpen(false);
                  }}
                >
                  <Columns2 className="h-3.5 w-3.5 text-muted-foreground" />
                  向右拆分
                </button>
              ) : null}
              {onSplitDown ? (
                <button
                  type="button"
                  role="menuitem"
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left transition-colors hover:bg-accent focus:bg-accent focus:outline-none"
                  onClick={() => {
                    onSplitDown();
                    setOpen(false);
                  }}
                >
                  <Rows2 className="h-3.5 w-3.5 text-muted-foreground" />
                  向下拆分
                </button>
              ) : null}
              <div className="my-1 border-t border-border" />
            </>
          ) : null}
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-error transition-colors hover:bg-error-container focus:bg-error-container focus:outline-none"
            onClick={() => {
              onClose();
              setOpen(false);
            }}
          >
            <X className="h-3.5 w-3.5" />
            {closeLabel}
          </button>
        </div>
      ) : null}
    </div>
  );
}
