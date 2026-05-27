/**
 * LoadingPlaceholder - 加载占位符
 *
 * 显示 AI 正在处理任务的提示
 */
import { Loader2 } from "lucide-react";

export function LoadingPlaceholder() {
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground py-2 px-3">
      <Loader2 className="h-4 w-4 animate-spin text-warning" />
      <span>正在执行任务</span>
      <span className="inline-flex w-4">
        <span className="animate-pulse">...</span>
      </span>
    </div>
  );
}
