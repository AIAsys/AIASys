import { useCallback, useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { fetchTokenHeatmap } from "@/lib/api/tokenUsage";
import type { HeatmapResponse } from "@/types/tokenUsage";
import { SummaryCards } from "@/pages/TokenDashboard/SummaryCards";
import { HeatmapChart } from "@/pages/TokenDashboard/HeatmapChart";

export interface TokenUsagePanelProps {
  embedded?: boolean;
}

export function TokenUsagePanel({ embedded }: TokenUsagePanelProps) {
  const [data, setData] = useState<HeatmapResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dateRange, setDateRange] = useState<"90d" | "180d" | "365d">("365d");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const now = new Date();
      let from: string | null = null;

      if (dateRange === "90d") {
        const d = new Date(now);
        d.setDate(d.getDate() - 90);
        from = d.toISOString().slice(0, 10);
      } else if (dateRange === "180d") {
        const d = new Date(now);
        d.setDate(d.getDate() - 180);
        from = d.toISOString().slice(0, 10);
      }

      const result = await fetchTokenHeatmap({ from, granularity: "day" });
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [dateRange]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <p className="text-muted-foreground">{error}</p>
        <Button className="mt-4" onClick={loadData}>
          重试
        </Button>
      </div>
    );
  }

  return (
    <div className={`${embedded ? "p-6" : ""} space-y-6`}>
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-foreground">Token 消耗面板</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            查看跨会话的 LLM Token 消耗趋势
          </p>
        </div>
        <div className="flex items-center gap-2">
          {(["90d", "180d", "365d"] as const).map((range) => (
            <Button
              key={range}
              variant={dateRange === range ? "default" : "outline"}
              size="sm"
              onClick={() => setDateRange(range)}
            >
              {range === "90d" ? "近 3 月" : range === "180d" ? "近 6 月" : "近 1 年"}
            </Button>
          ))}
        </div>
      </div>

      <SummaryCards data={data} />

      <Card>
        <CardContent className="pt-6">
          <h3 className="text-sm font-medium text-muted-foreground mb-4">
            每日 Token 消耗
          </h3>
          {data && data.daily.length > 0 ? (
            <HeatmapChart daily={data.daily} />
          ) : (
            <div className="py-20 text-center text-muted-foreground text-sm">
              暂无数据。开始使用 AIASys 后，Token 消耗数据将在这里展示。
            </div>
          )}
        </CardContent>
      </Card>

      {data && data.daily.length > 0 && (
        <Card>
          <CardContent className="pt-6">
            <h3 className="text-sm font-medium text-muted-foreground mb-4">
              每日明细
            </h3>
            <div className="max-h-80 overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="pb-2 font-medium">日期</th>
                    <th className="pb-2 font-medium text-right">输入</th>
                    <th className="pb-2 font-medium text-right">输出</th>
                    <th className="pb-2 font-medium text-right">缓存读取</th>
                    <th className="pb-2 font-medium text-right">合计</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.daily].reverse().map((d) => (
                    <tr key={d.date} className="border-b border-border/50">
                      <td className="py-1.5">{d.date}</td>
                      <td className="py-1.5 text-right font-mono">
                        {(d.input / 1000).toFixed(0)}K
                      </td>
                      <td className="py-1.5 text-right font-mono">
                        {(d.output / 1000).toFixed(0)}K
                      </td>
                      <td className="py-1.5 text-right font-mono">
                        {(d.cache_read / 1000).toFixed(0)}K
                      </td>
                      <td className="py-1.5 text-right font-mono font-semibold">
                        {(d.total / 1000).toFixed(0)}K
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
