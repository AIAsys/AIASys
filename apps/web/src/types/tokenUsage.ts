/** Token 用量聚合查询类型 */

export interface DailyUsage {
  date: string;       // "2026-06-15"
  input: number;
  output: number;
  cache_read: number;
  cache_write: number;
  reasoning: number;
  total: number;      // input + output + cache_read + cache_write + reasoning
}

export interface HeatmapResponse {
  granularity: "day" | "week" | "month";
  from: string | null;
  to: string | null;
  total_input: number;
  total_output: number;
  total_tokens: number;
  models: string[];
  daily: DailyUsage[];
}
