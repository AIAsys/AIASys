import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "./httpClient";

export type RuntimeStoragePathKey =
  | "data_dir"
  | "workspaces_dir"
  | "logs_dir";

export interface RuntimeStoragePathSetting {
  key: RuntimeStoragePathKey;
  effective_path: string;
  configured_path: string;
  pending_path?: string | null;
  overridden_by_env?: string | null;
  editable: boolean;
}

export interface RuntimeStorageSettingsResponse {
  paths: RuntimeStoragePathSetting[];
  restart_required: boolean;
  config_path: string;
}

export interface RuntimeStoragePathValidationResponse {
  path: string;
  ok: boolean;
  exists: boolean;
  is_directory: boolean;
  readable: boolean;
  writable: boolean;
  created: boolean;
  message: string;
}

export interface RuntimeStorageMigrationItem {
  key: RuntimeStoragePathKey;
  source_path: string;
  target_path: string;
  source_exists: boolean;
  target_exists: boolean;
  target_empty: boolean;
  will_copy: boolean;
  ok: boolean;
  message: string;
}

export interface RuntimeStorageMigrationResponse {
  migration_id?: string | null;
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  paths: Partial<Record<RuntimeStoragePathKey, string>>;
  config_paths?: Partial<Record<RuntimeStoragePathKey, string>>;
  items: RuntimeStorageMigrationItem[];
  warnings: string[];
  errors: string[];
  progress: {
    total_items?: number;
    completed_items?: number;
    current_key?: string | null;
  };
  can_start?: boolean;
  message?: string | null;
}

export async function getRuntimeStorageSettings(): Promise<RuntimeStorageSettingsResponse> {
  return apiRequest<RuntimeStorageSettingsResponse>(
    API_ENDPOINTS.STORAGE_SETTINGS,
    { cache: "no-store" },
  );
}

export async function saveRuntimeStorageSettings(
  paths: Partial<Record<RuntimeStoragePathKey, string | null>>,
): Promise<RuntimeStorageSettingsResponse> {
  return apiRequest<RuntimeStorageSettingsResponse>(
    API_ENDPOINTS.STORAGE_SETTINGS,
    {
      method: "PUT",
      body: { paths },
    },
  );
}

export async function validateRuntimeStoragePath(
  path: string,
  create = true,
): Promise<RuntimeStoragePathValidationResponse> {
  return apiRequest<RuntimeStoragePathValidationResponse>(
    API_ENDPOINTS.STORAGE_SETTINGS_VALIDATE_PATH,
    {
      method: "POST",
      body: { path, create },
    },
  );
}

export async function getRuntimeStorageMigrationStatus(): Promise<RuntimeStorageMigrationResponse> {
  return apiRequest<RuntimeStorageMigrationResponse>(
    API_ENDPOINTS.STORAGE_SETTINGS_MIGRATION,
    { cache: "no-store" },
  );
}

export async function previewRuntimeStorageMigration(
  paths: Partial<Record<RuntimeStoragePathKey, string | null>>,
): Promise<RuntimeStorageMigrationResponse> {
  return apiRequest<RuntimeStorageMigrationResponse>(
    API_ENDPOINTS.STORAGE_SETTINGS_MIGRATION_PREVIEW,
    {
      method: "POST",
      body: { paths },
    },
  );
}

export async function startRuntimeStorageMigration(
  paths: Partial<Record<RuntimeStoragePathKey, string | null>>,
): Promise<RuntimeStorageMigrationResponse> {
  return apiRequest<RuntimeStorageMigrationResponse>(
    API_ENDPOINTS.STORAGE_SETTINGS_MIGRATION_START,
    {
      method: "POST",
      body: { paths },
    },
  );
}
