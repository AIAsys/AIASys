import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  ExternalSkillMarketDetailResponse,
  ExternalSkillMarketListResponse,
  ExternalSkillMarketSource,
  InstallExternalSkillRequest,
  InstallExternalSkillResponse,
} from "@/types/externalSkillMarket";

export async function getExternalSkillMarketSources(): Promise<
  ExternalSkillMarketSource[]
> {
  return apiRequest<ExternalSkillMarketSource[]>(
    API_ENDPOINTS.SKILLS_EXTERNAL_MARKET_SOURCES,
  );
}

export async function getExternalSkillMarketItems(params: {
  sourceId: string;
  search?: string;
  category?: string;
  sortBy?: string;
  pageNumber?: number;
  pageSize?: number;
}): Promise<ExternalSkillMarketListResponse> {
  return apiRequest<ExternalSkillMarketListResponse>(
    API_ENDPOINTS.SKILLS_EXTERNAL_MARKET_ITEMS,
    {
      query: {
        source_id: params.sourceId,
        search: params.search || undefined,
        category: params.category || undefined,
        sort_by: params.sortBy || "recommended",
        page_number: params.pageNumber ?? 1,
        page_size: params.pageSize ?? 24,
      },
    },
  );
}

export async function getExternalSkillMarketDetail(params: {
  sourceId: string;
  itemId: string;
}): Promise<ExternalSkillMarketDetailResponse> {
  return apiRequest<ExternalSkillMarketDetailResponse>(
    API_ENDPOINTS.SKILLS_EXTERNAL_MARKET_DETAIL,
    {
      query: {
        source_id: params.sourceId,
        item_id: params.itemId,
      },
    },
  );
}

export async function installExternalSkillMarketItem(params: {
  workspaceId: string;
  payload: InstallExternalSkillRequest;
}): Promise<InstallExternalSkillResponse> {
  return apiRequest<InstallExternalSkillResponse>(
    API_ENDPOINTS.SKILLS_EXTERNAL_MARKET_INSTALL(params.workspaceId),
    {
      method: "POST",
      body: params.payload,
    },
  );
}
