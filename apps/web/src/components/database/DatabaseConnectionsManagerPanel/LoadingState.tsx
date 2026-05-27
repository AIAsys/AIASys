import { Loader2 } from "lucide-react";

export function LoadingState() {
  return (
    <div className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-12 text-sm text-muted-foreground">
      <Loader2 className="h-4 w-4 animate-spin" />
      正在加载数据库连接...
    </div>
  );
}
