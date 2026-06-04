export interface ExternalSkillMarketSource {
  source_id: string;
  display_name: string;
  description?: string | null;
  supports_public_catalog: boolean;
  supports_workspace_install: boolean;
  install_available: boolean;
  install_unavailable_reason?: string | null;
}

export interface ExternalSkillMarketItem {
  source_id: string;
  item_id: string;
  slug: string;
  display_name: string;
  description?: string | null;
  summary?: string | null;
  description_zh?: string | null;
  version?: string | null;
  homepage_url?: string | null;
  categories: string[];
  labels?: Record<string, string> | null;
  owner_name?: string | null;
  source?: string | null;
  icon_url?: string | null;
  downloads?: number | null;
  installs?: number | null;
  stars?: number | null;
  score?: number | null;
  rank?: number | null;
}

export interface ExternalSkillMarketListResponse {
  source: ExternalSkillMarketSource;
  items: ExternalSkillMarketItem[];
  available_categories: string[];
  total_count: number;
  page_number: number;
  page_size: number;
}

export interface ExternalSkillMarketDetailResponse {
  source: ExternalSkillMarketSource;
  item: ExternalSkillMarketItem;
  readme_excerpt?: string | null;
  entry_relative_path?: string | null;
  included_files: string[];
  can_install: boolean;
  install_disabled_reason?: string | null;
}

export interface InstallExternalSkillRequest {
  source_id: string;
  item_id: string;
  force?: boolean;
}

export interface InstallExternalSkillResponse {
  source_id: string;
  item_id: string;
  workspace_id: string;
  skill_name: string;
  message: string;
}
