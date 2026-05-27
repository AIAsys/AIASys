/**
 * LoadingState - 加载状态
 *
 * 显示历史加载中的提示
 */
import { Loader2 } from "lucide-react";

export function LoadingState() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 text-muted-foreground">
      <Loader2 className="h-8 w-8 animate-spin text-tertiary" />
      <div className="space-y-1 text-center">
        <p className="text-sm font-medium text-foreground/80">正在加载工作区侧栏</p>
        <p className="text-xs text-muted-foreground">
          稍后会恢复工作区摘要、资源入口和次级视图。
        </p>
      </div>
    </div>
  );
}
