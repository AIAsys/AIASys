export type CapabilityKind =
  | "native_tool"
  | "mcp_server"
  | "skill_pack"
  | "subagent"
  | "runtime_helper";

export type CapabilityStatus = "active" | "beta" | "planned" | "disabled";

export type CapabilityEvidenceLevel =
  | "declared"
  | "config_backed"
  | "runtime_verified";

export interface CapabilitySecretRequirement {
  name: string;
  location: "header" | "env" | "config";
  required: boolean;
  description?: string | null;
}

export interface CapabilityHealthcheck {
  type: "mcp_connection_test" | "runtime_probe" | "none";
  target?: string | null;
  description?: string | null;
}

export interface CapabilityDescriptor {
  capability_id: string;
  display_name: string;
  kind: CapabilityKind;
  provider: string;
  category_id: string;
  category_label: string;
  description?: string | null;
  default_enabled: boolean;
  default_modes: string[];
  status: CapabilityStatus;
  evidence_level: CapabilityEvidenceLevel;
  config_schema: Record<string, unknown>;
  secret_requirements: CapabilitySecretRequirement[];
  healthcheck?: CapabilityHealthcheck | null;
}

export interface ModeCapabilityPreset {
  mode: "analysis" | string;
  capability_ids: string[];
  source_config_path: string;
  notes?: string | null;
}

export interface CapabilityRegistryResponse {
  analysis_sandbox_mode: string;
  capabilities: CapabilityDescriptor[];
  mode_presets: ModeCapabilityPreset[];
}

export interface IntegrationMarketItem {
  capability_id: string;
  display_name: string;
  kind: CapabilityKind;
  provider: string;
  description?: string | null;
  status: CapabilityStatus;
  evidence_level: CapabilityEvidenceLevel;
  default_modes: string[];
  config_schema: Record<string, unknown>;
  secret_requirements: CapabilitySecretRequirement[];
  healthcheck?: CapabilityHealthcheck | null;
  available: boolean;
  enabled: boolean;
  configured: boolean;
  activation_state: "ready" | "needs_secret" | "disabled";
  activation_message?: string | null;
}

export interface IntegrationManagementHints {
  configure_entry?: "global_mcp_config" | string;
  secret_entry?: "deploy_env" | string;
  supports_healthcheck?: boolean;
  change_effect?: "next_execution_session_recreate" | string;
  supports_hot_reload?: boolean;
  requires_service_reload_for_secret?: boolean;
}

export interface IntegrationEnvVarHints {
  enabled?: string | null;
  secret?: string | null;
  url?: string | null;
  timeout_ms?: string | null;
}

export interface IntegrationMarketResponse {
  items: IntegrationMarketItem[];
  recommended_by_mode: Record<string, string[]>;
  installed_capability_ids: string[];
  active_capability_ids: string[];
}
