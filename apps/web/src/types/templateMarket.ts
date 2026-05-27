export interface ExternalTemplateMarketSource {
  source_id: string;
  display_name: string;
  description?: string;
  supports_public_catalog: boolean;
  supports_install: boolean;
  install_available: boolean;
  install_unavailable_reason?: string;
}

export interface ExternalTemplateMarketItem {
  source_id: string;
  item_id: string;
  name: string;
  description?: string;
  icon: string;
  category: string;
  env_kind: string;
  file_count: number;
  capability_count: number;
  is_installed: boolean;
  official: boolean;
}

export interface ExternalTemplateMarketListResponse {
  source: ExternalTemplateMarketSource;
  items: ExternalTemplateMarketItem[];
  available_categories: string[];
  total_count: number;
}

export interface ExternalTemplateMarketDetailResponse {
  source: ExternalTemplateMarketSource;
  item: ExternalTemplateMarketItem;
  files: Array<{
    relative_path: string;
    content?: string;
    source_path?: string;
  }>;
  recommended_capabilities: Array<{
    capability_id: string;
    kind: string;
    required: boolean;
    auto_activate: boolean;
    config?: Record<string, unknown>;
  }>;
  env_vars: Record<string, string>;
  can_install: boolean;
  install_disabled_reason?: string;
}

export interface InstallExternalTemplateRequest {
  source_id: string;
  item_id: string;
}
