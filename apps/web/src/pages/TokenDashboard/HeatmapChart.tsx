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

export function HeatmapChart({ daily }: { daily: DailyUsage[] }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<EChartsType | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function initChart() {
      const echarts = await import("echarts");
      if (cancelled || !containerRef.current) return;

      if (chartRef.current) {
        chartRef.current.dispose();
      }

      const chart = echarts.init(containerRef.current, undefined, {
        renderer: "canvas",
      });
      chartRef.current = chart;

      const heatmapData = getHeatmapData(daily);
      const maxVal = getMaxValue(daily);

      // 确定日期范围
      const startDate = daily.length > 0
        ? new Date(daily[0].date)
        : new Date();
      const endDate = daily.length > 0
        ? new Date(daily[daily.length - 1].date)
        : new Date();
      // 扩展到整年范围以便日历布局完整
      const yearStart = String(startDate.getFullYear());
      const yearEnd = String(endDate.getFullYear());

      chart.setOption({
        tooltip: {
          formatter: (params: { data: [string, number] }) => {
            const [date, value] = params.data;
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
          top: 20,
          left: 30,
          right: 20,
          range: [yearStart, yearEnd],
          cellSize: ["auto", 14],
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

      return () => {
        window.removeEventListener("resize", handleResize);
      };
    }

    initChart().catch(console.error);

    return () => {
      cancelled = true;
      if (chartRef.current) {
        chartRef.current.dispose();
        chartRef.current = null;
      }
    };
  }, [daily]);

  return (
    <div
      ref={containerRef}
      className="w-full"
      style={{ height: 180 + Math.ceil(daily.length / 365) * 130 }}
    />
  );
}