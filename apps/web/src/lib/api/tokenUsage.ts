import type { HeatmapResponse } from "@/types/tokenUsage";
import { apiRequest } from "@/lib/api/httpClient";

export interface HeatmapQueryParams {
  workspace_id?: string | null;
  model?: string | null;
  from?: string | null;
  to?: string | null;
  granularity?: "day" | "week" | "month";
}

export async function fetchTokenHeatmap(
  params: HeatmapQueryParams = {},
): Promise<HeatmapResponse> {
  const searchParams = new URLSearchParams();

  if (params.workspace_id) {
    searchParams.set("workspace_id", params.workspace_id);
  }
  if (params.model) {
    searchParams.set("model", params.model);
  }
  if (params.from) {
    searchParams.set("from", params.from);
  }
  if (params.to) {
    searchParams.set("to", params.to);
  }
  if (params.granularity) {
    searchParams.set("granularity", params.granularity);
  }

  const query = searchParams.toString();
  const url = query
    ? `/api/token-usage/heatmap?${query}`
    : "/api/token-usage/heatmap";

  return apiRequest<HeatmapResponse>(url, { cache: "no-store" });
}
