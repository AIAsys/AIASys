import { Loader2 } from "lucide-react";

export function ChartLoadingState() {
  return (
    <div className="flex h-full min-h-[220px] items-center justify-center text-muted-foreground">
      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
      <span className="text-sm">图表加载中...</span>
    </div>
  );
}
