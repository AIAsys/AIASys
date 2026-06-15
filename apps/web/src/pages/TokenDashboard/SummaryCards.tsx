import { Card, CardContent } from "@/components/ui/card";
import type { HeatmapResponse } from "@/types/tokenUsage";

function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

export function SummaryCards({ data }: { data: HeatmapResponse | null }) {
  if (!data) return null;

  return (
    <div className="grid grid-cols-3 gap-4">
      <Card>
        <CardContent className="pt-6">
          <div className="text-sm text-muted-foreground">总消耗</div>
          <div className="text-2xl font-bold mt-1">
            {formatTokens(data.total_tokens)}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">tokens</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="text-sm text-muted-foreground">输入 Token</div>
          <div className="text-2xl font-bold mt-1">
            {formatTokens(data.total_input)}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">prompt</div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="pt-6">
          <div className="text-sm text-muted-foreground">输出 Token</div>
          <div className="text-2xl font-bold mt-1">
            {formatTokens(data.total_output)}
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">completion</div>
        </CardContent>
      </Card>
    </div>
  );
}