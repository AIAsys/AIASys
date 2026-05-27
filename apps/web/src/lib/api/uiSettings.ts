import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "./httpClient";

export interface UISettingsData {
  activityBarOrder?: string[];
  [key: string]: unknown;
}

export async function getUserUISettings(userId: string): Promise<UISettingsData> {
  const response = await apiRequest<{ data: UISettingsData }>(
    API_ENDPOINTS.UI_SETTINGS(userId),
    { cache: "no-store" },
  );
  return response.data ?? {};
}

export async function saveUserUISettings(
  userId: string,
  data: UISettingsData,
): Promise<UISettingsData> {
  const response = await apiRequest<{ data: UISettingsData }>(
    API_ENDPOINTS.UI_SETTINGS(userId),
    {
      method: "PUT",
      body: { data },
    },
  );
  return response.data ?? {};
}
