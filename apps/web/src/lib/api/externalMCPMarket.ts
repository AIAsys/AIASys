import { apiRequest } from "@/lib/api/httpClient";
import type {
  ExternalMCPMarketDetailResponse,
  ExternalMCPMarketListResponse,
  ExternalMCPMarketSource,
  ImportExternalMCPRequest,
  ImportExternalMCPResponse,
} from "@/types/externalMCPMarket";

export async function getExternalMCPMarketSources(): Promise<
  ExternalMCPMarketSource[]
> {
  return apiRequest<ExternalMCPMarketSource[]>(
    "/api/mcp/external-market/sources",
  );
}

export async function getExternalMCPMarketItems(params: {
  sourceId: string;
  search?: string;
  pageNumber?: number;
  pageSize?: number;
}): Promise<ExternalMCPMarketListResponse> {
  return apiRequest<ExternalMCPMarketListResponse>(
    "/api/mcp/external-market/items",
    {
      query: {
        source_id: params.sourceId,
        search: params.search || undefined,
        page_number: params.pageNumber ?? 1,
        page_size: params.pageSize ?? 20,
      },
    },
  );
}

export async function getExternalMCPMarketDetail(params: {
  sourceId: string;
  itemId: string;
}): Promise<ExternalMCPMarketDetailResponse> {
  return apiRequest<ExternalMCPMarketDetailResponse>(
    "/api/mcp/external-market/detail",
    {
      query: {
        source_id: params.sourceId,
        item_id: params.itemId,
      },
    },
  );
}

export async function importExternalMCPMarketItem(
  payload: ImportExternalMCPRequest,
): Promise<ImportExternalMCPResponse> {
  return apiRequest<ImportExternalMCPResponse>(
    "/api/mcp/external-market/import",
    {
      method: "POST",
      body: payload,
    },
  );
}
