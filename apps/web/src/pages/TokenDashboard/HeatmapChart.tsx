import { useEffect, useRef } from "react";
import type { EChartsType } from "echarts";
import type { DailyUsage } from "@/types/tokenUsage";

function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function getHeatmapData(daily: DailyUsage[]): [string, number][] {
  return daily.map((d) => [d.date, d.total] as [string, number]);
}

function getMaxValue(daily: DailyUsage[]): number {
  if (daily.length === 0) return 1;
  return Math.max(1, ...daily.map((d) => d.total));
}

function getDateRange(daily: DailyUsage[]): [string, string] {
  if (daily.length === 0) {
    const today = new Date().toISOString().slice(0, 10);
    return [today, today];
  }
  // 前后各扩展一天，让边界单元格显示更完整
  const first = new Date(daily[0].date);
  const last = new Date(daily[daily.length - 1].date);
  first.setDate(first.getDate() - 1);
  last.setDate(last.getDate() + 1);
  return [first.toISOString().slice(0, 10), last.toISOString().slice(0, 10)];
}

export function HeatmapChart({ daily }: { daily: DailyUsage[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);

  useEffect(() => {
    let cancelled = false;
    let cleanupResize: (() => void) | undefined;

    async function initChart() {
      const echarts = await import("echarts");
      if (cancelled || !containerRef.current) return;

      if (chartRef.current) {
        chartRef.current.dispose();
        chartRef.current = null;
      }

      const chart = echarts.init(containerRef.current, undefined, {
        renderer: "canvas",
      });
      chartRef.current = chart;

      const heatmapData = getHeatmapData(daily);
      const maxVal = getMaxValue(daily);
      const [rangeStart, rangeEnd] = getDateRange(daily);

      chart.setOption({
        tooltip: {
          formatter: (params: { data?: [string, number] }) => {
            const data = params.data;
            if (!data) return "";
            const [date, value] = data;
            return `<b>${date}</b><br/>Token 消耗: ${formatTokens(value)}`;
          },
        },
        visualMap: {
          min: 0,
          max: maxVal,
          type: "piecewise",
          orient: "horizontal",
          left: "center",
          bottom: 0,
          pieces: [
            { min: 0, max: 0, label: "0", color: "#ebedf0" },
            { min: 1, max: Math.ceil(maxVal * 0.25), label: "低", color: "#9be9a8" },
            { min: Math.ceil(maxVal * 0.25) + 1, max: Math.ceil(maxVal * 0.5), label: "中低", color: "#40c463" },
            { min: Math.ceil(maxVal * 0.5) + 1, max: Math.ceil(maxVal * 0.75), label: "中高", color: "#30a14e" },
            { min: Math.ceil(maxVal * 0.75) + 1, max: maxVal, label: "高", color: "#216e39" },
          ],
        },
        calendar: {
          top: 28,
          left: 36,
          right: 20,
          range: [rangeStart, rangeEnd],
          cellSize: ["auto", 16],
          yearLabel: { show: true },
          dayLabel: { firstDay: 1, nameMap: "EN" },
          monthLabel: { show: true },
          splitLine: { lineStyle: { color: "#ffffff", width: 3 } },
          itemStyle: {
            borderColor: "#ffffff",
            borderWidth: 3,
            borderRadius: 2,
          },
        },
        series: [
          {
            type: "heatmap",
            coordinateSystem: "calendar",
            data: heatmapData,
            emphasis: {
              itemStyle: {
                shadowBlur: 8,
                shadowColor: "rgba(0, 0, 0, 0.3)",
              },
            },
          },
        ],
      });

      const handleResize = () => chart.resize();
      window.addEventListener("resize", handleResize);
      cleanupResize = () => window.removeEventListener("resize", handleResize);
    }

    initChart().catch(console.error);

    return () => {
      cancelled = true;
      if (cleanupResize) cleanupResize();
      if (chartRef.current) {
        chartRef.current.dispose();
        chartRef.current = null;
      }
    };
  }, [daily]);

  // 高度：按周数估算，最小 240px
  const weeks = Math.max(4, Math.ceil(daily.length / 7));
  const height = Math.max(240, 60 + weeks * 24);

  return (
    <div
      ref={containerRef}
      className="w-full"
      style={{ height }}
    />
  );
}
