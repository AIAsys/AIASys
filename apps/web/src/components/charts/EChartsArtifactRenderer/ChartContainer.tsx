import { useMemo } from "react";
import { cn } from "@/lib/utils";

interface ChartContainerProps {
  variant: "chat" | "workspace";
  containerRef: React.RefObject<HTMLDivElement | null>;
}

export function ChartContainer({ variant, containerRef }: ChartContainerProps) {
  const chartClass = useMemo(
    () =>
      variant === "workspace"
        ? "h-full min-h-[360px] w-full rounded-lg bg-background"
        : "h-[360px] w-full rounded-lg bg-background",
    [variant]
  );

  return <div ref={containerRef} className={cn(chartClass)} />;
}
