import { useEffect, useRef, useState, type ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

export function NavItem({
  icon,
  label,
  active = false,
  onClick,
  testId,
}: {
  icon: ReactNode;
  label: string;
  active?: boolean;
  onClick?: () => void;
  testId?: string;
}) {
  return (
    <div
      data-testid={testId}
      className={`flex items-center gap-2.5 px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${active ? "bg-background shadow-sm" : "hover:bg-sidebar-accent"}`}
      onClick={onClick}
    >
      <span className="text-muted-foreground flex-shrink-0">{icon}</span>
      <span className="font-medium text-sm">{label}</span>
    </div>
  );
}

export function CollapsedIconButton({
  icon,
  tooltip,
  onClick,
  testId,
}: {
  icon: ReactNode;
  tooltip: string;
  onClick?: () => void;
  testId?: string;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      onClick={onClick}
      className="w-9 h-9 rounded-lg flex items-center justify-center text-muted-foreground hover:text-foreground hover:bg-sidebar-accent transition-colors"
      title={tooltip}
    >
      {icon}
    </button>
  );
}

export function UnavailableSettingsButton({
  icon,
  buttonClassName,
  message = "用户设置暂不可用",
  ariaLabel = "用户设置",
  onClick,
  side = "top",
  testId,
}: {
  icon: ReactNode;
  buttonClassName: string;
  message?: string;
  ariaLabel?: string;
  onClick?: () => void;
  side?: "top" | "right" | "bottom" | "left";
  testId?: string;
}) {
  const [hoverOpen, setHoverOpen] = useState(false);
  const [clickOpen, setClickOpen] = useState(false);
  const hideTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (hideTimerRef.current !== null) {
        window.clearTimeout(hideTimerRef.current);
      }
    };
  }, []);

  const handleClick = () => {
    onClick?.();
    setClickOpen(true);
    if (hideTimerRef.current !== null) {
      window.clearTimeout(hideTimerRef.current);
    }
    hideTimerRef.current = window.setTimeout(() => {
      setClickOpen(false);
      hideTimerRef.current = null;
    }, 1600);
  };

  return (
    <Tooltip open={hoverOpen || clickOpen} onOpenChange={setHoverOpen}>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-testid={testId}
          onClick={handleClick}
          className={buttonClassName}
          aria-label={ariaLabel}
        >
          {icon}
        </button>
      </TooltipTrigger>
      <TooltipContent side={side} sideOffset={8}>
        {message}
      </TooltipContent>
    </Tooltip>
  );
}
