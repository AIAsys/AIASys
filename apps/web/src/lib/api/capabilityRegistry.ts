import { apiRequest } from "@/lib/api/httpClient";
import type {
  CapabilityRegistryResponse,
  IntegrationMarketResponse,
} from "@/types/capability";

export async function getCapabilityRegistry(
  analysisSandboxMode?: string | null,
): Promise<CapabilityRegistryResponse> {
  return apiRequest<CapabilityRegistryResponse>("/api/system/capability-registry", {
    query: {
      analysis_sandbox_mode: analysisSandboxMode ?? undefined,
    },
  });
}

export async function getIntegrationsMarket(): Promise<IntegrationMarketResponse> {
  return apiRequest<IntegrationMarketResponse>("/api/system/integrations-market");
}
