import { useEffect, useRef, useState } from "react";
import { getErrorMessage } from "@/lib/utils";
import { fetchWorkspaceTextContent } from "@/utils/workspaceFiles";
import type { EChartsType } from "echarts";
import type { ChartExportController, RenderPlan } from "./types";

interface UseChartRendererProps {
  artifactPath?: string;
  artifactContent?: string;
  sessionId?: string;
  token?: string;
}

interface UseChartRendererReturn {
  renderPlan: RenderPlan | null;
  isLoading: boolean;
  error: string | null;
  containerRef: React.RefObject<HTMLDivElement | null>;
  exportController: ChartExportController;
}

function normalizeExportFilename(filename?: string): string {
  const fallbackName = "echarts-chart";
  const normalizedName = (filename || fallbackName)
    .replace(/\.(chart\.)?echarts\.json$/i, "")
    .replace(/[\\/:*?"<>|]+/g, "-")
    .trim();

  return normalizedName || fallbackName;
}

export function useChartRenderer({
  artifactPath,
  artifactContent,
  sessionId,
  token,
}: UseChartRendererProps): UseChartRendererReturn {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [renderPlan, setRenderPlan] = useState<RenderPlan | null>(null);
  const [canExportPng, setCanExportPng] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function loadArtifact() {
      setIsLoading(true);
      setError(null);

      try {
        const { buildRenderPlan } = await import("./chartBuilders");
        
        const readTextFile = async (path: string) =>
          await fetchWorkspaceTextContent(path, sessionId, token);
        
        const rawContent =
          artifactContent ??
          (artifactPath
            ? await fetchWorkspaceTextContent(artifactPath, sessionId, token)
            : null);

        if (!rawContent) {
          throw new Error("图表资产内容为空");
        }

        const nextPlan = await buildRenderPlan(rawContent, readTextFile);
        if (!cancelled) {
          setRenderPlan(nextPlan);
        }
      } catch (loadError) {
        if (!cancelled) {
          setRenderPlan(null);
          setError(getErrorMessage(loadError));
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadArtifact();
    return () => {
      cancelled = true;
    };
  }, [artifactContent, artifactPath, sessionId, token]);

  useEffect(() => {
    if (!renderPlan || !containerRef.current) {
      return;
    }

    const currentPlan = renderPlan;
    let disposed = false;
    let resizeObserver: ResizeObserver | null = null;
    let disposeChart: (() => void) | null = null;

    async function renderChart() {
      const echartsModule = await import("echarts");
      if (disposed || !containerRef.current) {
        return;
      }

      const registerMap = echartsModule.registerMap as (
        mapName: string,
        geoJson: unknown,
      ) => void;

      for (const registration of currentPlan.mapRegistrations) {
        registerMap(registration.mapName, registration.geoJson);
      }

      const chart = echartsModule.init(containerRef.current, undefined, {
        renderer: currentPlan.renderer,
      });
      chartRef.current = chart;
      setCanExportPng(true);

      chart.setOption(currentPlan.option, true);
      chart.resize();

      resizeObserver = new ResizeObserver(() => {
        chart.resize();
      });
      resizeObserver.observe(containerRef.current);

      disposeChart = () => {
        resizeObserver?.disconnect();
        chartRef.current = null;
        setCanExportPng(false);
        chart.dispose();
      };
    }

    void renderChart();

    return () => {
      disposed = true;
      disposeChart?.();
      resizeObserver?.disconnect();
    };
  }, [renderPlan]);

  const exportController: ChartExportController = {
    canExportPng,
    exportPng: (filename?: string) => {
      const chart = chartRef.current;
      if (!chart) {
        return;
      }

      const dataUrl = chart.getDataURL({
        type: "png",
        pixelRatio: 2,
        backgroundColor: "#FFFFFF",
        excludeComponents: ["toolbox", "graphic"],
      });
      const link = document.createElement("a");
      link.href = dataUrl;
      link.download = `${normalizeExportFilename(filename)}.png`;
      document.body.appendChild(link);
      link.click();
      link.remove();
    },
  };

  return { renderPlan, isLoading, error, containerRef, exportController };
}
