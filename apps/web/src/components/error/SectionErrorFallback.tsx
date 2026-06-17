import { AlertCircle } from "lucide-react";

interface SectionErrorFallbackProps {
  error: Error;
  reset: () => void;
}

/**
 * 紧凑的错误展示组件，用于局部 ErrorBoundary。
 * 高度不超过 200px，避免在面板内部占据过多空间。
 */
export function SectionErrorFallback({ error, reset }: SectionErrorFallbackProps) {
  return (
    <div className="flex max-h-[200px] items-center gap-3 overflow-hidden rounded-lg border border-error/30 bg-error-container/20 p-4">
      <AlertCircle className="h-5 w-5 shrink-0 text-error" />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="text-sm font-medium text-foreground">此区域加载失败</span>
        <span className="truncate text-xs text-muted-foreground">
          {error.message}
        </span>
      </div>
      <button
        type="button"
        onClick={reset}
        className="inline-flex shrink-0 items-center justify-center rounded-md border border-border bg-background px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-accent"
      >
        重试
      </button>
    </div>
  );
}
