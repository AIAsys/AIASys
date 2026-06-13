import { type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/**
 * Standardized empty state for sidebar tab panels.
 *
 * Pattern: 48px icon + title + description + optional action button.
 */
export function PanelEmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full flex-col items-center justify-center px-6 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted/40 text-muted-foreground">
          {icon}
        </div>
      ) : null}
      <div className="mt-3 text-sm font-medium text-foreground">{title}</div>
      {description ? (
        <div className="mt-1 max-w-[260px] text-xs leading-5 text-muted-foreground">
          {description}
        </div>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}

/**
 * Standardized error state with optional retry button.
 */
export function PanelErrorState({
  title = "加载失败",
  description,
  onRetry,
  className,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-full flex-col items-center justify-center px-6 text-center",
        className,
      )}
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-error-container/60 text-error">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-6 w-6"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
      </div>
      <div className="mt-3 text-sm font-medium text-foreground">{title}</div>
      {description ? (
        <div className="mt-1 max-w-[260px] text-xs leading-5 text-muted-foreground">
          {description}
        </div>
      ) : null}
      {onRetry ? (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-4 h-8 gap-1.5 rounded-lg px-3 text-[12px]"
          onClick={onRetry}
        >
          重试
        </Button>
      ) : null}
    </div>
  );
}

/**
 * Standardized loading skeleton for sidebar tab panels.
 *
 * Replaces ad-hoc spinner patterns with consistent skeleton blocks.
 */
export function PanelLoadingSkeleton({
  lines = 3,
  showHeader = true,
  className,
}: {
  lines?: number;
  showHeader?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full flex-col px-5 py-4", className)}>
      {showHeader && (
        <div className="mb-4 space-y-2">
          <Skeleton className="h-5 w-32" />
          <Skeleton className="h-3 w-48" />
        </div>
      )}
      <div className="space-y-3">
        {Array.from({ length: lines }).map((_, index) => (
          <div key={index} className="space-y-2 rounded-xl border border-border/60 bg-card p-3">
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-3 w-1/2" />
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Compact inline loading indicator for smaller panels.
 */
export function PanelLoadingInline({ text = "加载中..." }: { text?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-8 text-xs text-muted-foreground">
      <svg
        xmlns="http://www.w3.org/2000/svg"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-4 w-4 animate-spin"
      >
        <path d="M21 12a9 9 0 1 1-6.219-8.56" />
      </svg>
      {text}
    </div>
  );
}
