import type { MCPServerConfig } from "@/lib/api/mcp";

export interface ExternalMCPMarketSource {
  source_id: string;
  display_name: string;
  description?: string | null;
  supports_public_catalog: boolean;
  supports_account_sync: boolean;
  requires_token_for_account_sync: boolean;
}

export interface ExternalMCPMarketItem {
  source_id: string;
  item_id: string;
  display_name: string;
  publisher?: string | null;
  description?: string | null;
  logo_url?: string | null;
  categories: string[];
  tags: string[];
  view_count?: number | null;
  is_hosted?: boolean | null;
}

export interface ExternalMCPTemplatePreview {
  server_key: string;
  import_name: string;
  transport_type: "streamable-http" | "sse" | "stdio";
  target?: string | null;
  args: string[];
  env_keys: string[];
  header_keys: string[];
}

export interface ExternalMCPEnvField {
  name: string;
  required: boolean;
  description?: string | null;
  default_value?: string | null;
}

export interface ExternalMCPMarketListResponse {
  source: ExternalMCPMarketSource;
  items: ExternalMCPMarketItem[];
  total_count: number;
  page_number: number;
  page_size: number;
}

export interface ExternalMCPMarketDetailResponse {
  source: ExternalMCPMarketSource;
  item: ExternalMCPMarketItem;
  env_fields: ExternalMCPEnvField[];
  template_previews: ExternalMCPTemplatePreview[];
  readme_excerpt?: string | null;
  can_import: boolean;
  import_disabled_reason?: string | null;
}

export interface ImportExternalMCPRequest {
  source_id: string;
  item_id: string;
  enabled?: boolean;
  env_overrides?: Record<string, string>;
}

export interface ImportExternalMCPResponse {
  source_id: string;
  item_id: string;
  imported_names: string[];
  imported_servers: MCPServerConfig[];
  message: string;
}
