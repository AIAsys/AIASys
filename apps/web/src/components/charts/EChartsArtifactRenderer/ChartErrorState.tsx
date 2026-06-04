import { AlertCircle } from "lucide-react";

interface ChartErrorStateProps {
  error: string;
}

export function ChartErrorState({ error }: ChartErrorStateProps) {
  return (
    <div className="flex h-full min-h-[220px] flex-col items-center justify-center rounded-xl border border-dashed border-border bg-muted/20 px-6 text-center">
      <AlertCircle className="mb-3 h-8 w-8 text-destructive" />
      <div className="text-sm font-medium text-foreground">图表渲染失败</div>
      <p className="mt-2 max-w-xl text-xs leading-5 text-muted-foreground">
        {error}
      </p>
    </div>
  );
}
