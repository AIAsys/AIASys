import type { ReactNode } from "react";
import { Search } from "lucide-react";

import { cn } from "@/lib/utils";

interface AssetTreePanelHeaderProps {
  title: string;
  description?: string;
  icon: ReactNode;
  fileCount: number;
  directoryCount: number;
  actions?: ReactNode;
  searchQuery?: string;
  searchPlaceholder?: string;
  onSearchChange?: (value: string) => void;
  fileCountTestId?: string;
  directoryCountTestId?: string;
  className?: string;
}

export function AssetTreePanelHeader({
  title,
  description,
  icon,
  fileCount,
  directoryCount,
  actions,
  searchQuery,
  searchPlaceholder = "搜索文件或目录...",
  onSearchChange,
  fileCountTestId,
  directoryCountTestId,
  className,
}: AssetTreePanelHeaderProps) {
  const searchable = Boolean(onSearchChange);
  const countSummary = `${directoryCount} 目录 · ${fileCount} 文件`;

  return (
    <div
      className={cn(
        "flex-shrink-0 border-b border-border bg-background px-3 py-2",
        className,
      )}
    >
      <div className="flex min-w-0 items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center text-muted-foreground">
            {icon}
          </span>
          <span
            className="min-w-0 truncate text-[12px] font-semibold leading-5 text-foreground"
            title={title}
          >
            {title}
          </span>
        </div>
        {actions ? (
          <div className="flex shrink-0 items-center gap-0.5">{actions}</div>
        ) : null}
      </div>

      <div className="mt-0.5 flex min-w-0 items-center gap-2 pl-6 text-[11px] leading-4 text-muted-foreground">
        {description ? (
          <span className="min-w-0 flex-1 truncate" title={description}>
            {description}
          </span>
        ) : null}
        <span
          className="shrink-0 font-mono"
          title={countSummary}
        >
          <span data-testid={directoryCountTestId}>{directoryCount} 目录</span>
          <span className="px-1 text-muted-foreground/50">·</span>
          <span data-testid={fileCountTestId}>{fileCount} 文件</span>
        </span>
      </div>

      {searchable ? (
        <div className="relative mt-2">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder={searchPlaceholder}
            className="h-7 w-full rounded-md border border-input bg-muted/30 pl-8 pr-3 font-mono text-xs transition-colors placeholder:text-muted-foreground/60 focus:bg-background focus:outline-none focus:ring-1 focus:ring-ring"
            value={searchQuery ?? ""}
            onChange={(event) => onSearchChange?.(event.target.value)}
          />
        </div>
      ) : null}
    </div>
  );
}
