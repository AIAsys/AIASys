import { memo, useMemo } from "react";

import { cn } from "@/lib/utils";
import { getArtifactDisplayName } from "./utils";
import { useChartRenderer } from "./useChartRenderer";
import { ChartCard } from "./ChartCard";
import { ChartLoadingState } from "./ChartLoadingState";
import { ChartErrorState } from "./ChartErrorState";
import { ChartContainer } from "./ChartContainer";
import type { EChartsArtifactRendererProps } from "./types";

export const EChartsArtifactRenderer = memo(function EChartsArtifactRenderer({
  artifactPath,
  artifactContent,
  sessionId,
  token,
  variant = "chat",
  className,
}: EChartsArtifactRendererProps) {
  const {
    renderPlan,
    isLoading,
    error,
    containerRef,
    exportController,
  } = useChartRenderer({
    artifactPath,
    artifactContent,
    sessionId,
    token,
  });

  const sourceLabel = useMemo(
    () => getArtifactDisplayName(artifactPath),
    [artifactPath]
  );

  const chartHeightClass = useMemo(
    () =>
      variant === "workspace"
        ? "h-full min-h-[360px]"
        : "h-[360px]",
    [variant]
  );

  return (
    <ChartCard
      renderPlan={renderPlan}
      sourceLabel={sourceLabel}
      variant={variant}
      className={className}
      canExportPng={!isLoading && !error && exportController.canExportPng}
      onExportPng={() => exportController.exportPng(sourceLabel)}
    >
      <div className={cn(chartHeightClass)}>
        {isLoading ? (
          <ChartLoadingState />
        ) : error ? (
          <ChartErrorState error={error} />
        ) : (
          <ChartContainer variant={variant} containerRef={containerRef} />
        )}
      </div>
    </ChartCard>
  );
});
