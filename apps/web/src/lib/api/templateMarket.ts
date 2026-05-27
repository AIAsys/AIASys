import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  ExternalTemplateMarketSource,
  ExternalTemplateMarketListResponse,
  ExternalTemplateMarketDetailResponse,
  InstallExternalTemplateRequest,
} from "@/types/templateMarket";

export async function listTemplateMarketSources(): Promise<
  ExternalTemplateMarketSource[]
> {
  const data = await apiRequest<{
    sources: ExternalTemplateMarketSource[];
  }>(API_ENDPOINTS.TEMPLATE_MARKET_SOURCES, { cache: "no-store", timeoutMs: 10000 });
  return data.sources ?? [];
}

export async function listTemplateMarketItems(
  sourceId: string,
  search?: string,
  category?: string,
): Promise<ExternalTemplateMarketListResponse> {
  return apiRequest<ExternalTemplateMarketListResponse>(
    API_ENDPOINTS.TEMPLATE_MARKET_ITEMS,
    {
      cache: "no-store",
      timeoutMs: 10000,
      query: {
        source_id: sourceId,
        search: search || undefined,
        category: category || undefined,
      },
    },
  );
}

export async function getTemplateMarketDetail(
  sourceId: string,
  itemId: string,
): Promise<ExternalTemplateMarketDetailResponse> {
  return apiRequest<ExternalTemplateMarketDetailResponse>(
    API_ENDPOINTS.TEMPLATE_MARKET_DETAIL,
    {
      cache: "no-store",
      timeoutMs: 10000,
      query: { source_id: sourceId, item_id: itemId },
    },
  );
}

export async function installTemplateMarketItem(
  payload: InstallExternalTemplateRequest,
): Promise<{ installed: boolean; template_id: string }> {
  return apiRequest<{ installed: boolean; template_id: string }>(
    API_ENDPOINTS.TEMPLATE_MARKET_INSTALL,
    {
      method: "POST",
      timeoutMs: 15000,
      body: payload,
    },
  );
}
