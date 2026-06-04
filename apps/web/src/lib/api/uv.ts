import { apiRequest } from "@/lib/api/httpClient";

export interface UvStatusResponse {
  installed: boolean;
  version: string | null;
  path: string | null;
  message: string | null;
}

export async function getUvStatus(): Promise<UvStatusResponse> {
  return apiRequest<UvStatusResponse>("/api/system/uv", { cache: "no-store" });
}

export async function installUv(): Promise<UvStatusResponse> {
  return apiRequest<UvStatusResponse>("/api/system/uv", {
    method: "POST",
    cache: "no-store",
  });
}
