export type ExpertRoleSource = "system" | "global" | "workspace" | "custom";

export type ExpertRoleVisibilitySource = "system" | "global" | "workspace";

export interface ExpertRoleSummary {
  role_id: string;
  display_name: string;
  description: string;
  when_to_use: string;
  default_model: string | null;
  tool_policy: "inherit" | "allowlist";
  tool_ids: string[];
  tool_names: string[];
  tool_count: number;
  permissions: string[];
  capabilities: string[];
  supports_background: boolean;
  agent_file: string;
  source: ExpertRoleSource;
  catalog_visible: boolean;
  host_selectable: boolean;
  default_enabled: boolean;
  visibility_source: ExpertRoleVisibilitySource;
  installed_to_global: boolean;
  installed_to_workspace: boolean;
  installed_scope: "system" | "global" | "workspace";
  lock_reason: string | null;
}

export interface ExpertRoleVisibilityState {
  catalog_visible: boolean;
  host_selectable: boolean;
  default_enabled: boolean;
  visibility_source: ExpertRoleVisibilitySource;
  installed_to_global?: boolean;
  installed_to_workspace?: boolean;
  installed_scope?: "system" | "global" | "workspace";
  lock_reason: string | null;
}

export interface UpdateExpertRoleVisibilityPayload {
  catalog_visible?: boolean;
  host_selectable?: boolean;
  default_enabled?: boolean;
}

export interface UpdateExpertRoleVisibilityResponse
  extends ExpertRoleVisibilityState {
  role_id?: string;
}

export interface WorkspaceExpertCatalogResponse {
  workspace_id: string;
  profile_name: string;
  roles: ExpertRoleSummary[];
}

export interface GlobalExpertCatalogResponse {
  scope: "global";
  profile_name: string;
  roles: ExpertRoleSummary[];
}

export interface SessionCollaborationPolicy {
  max_depth: number;
  max_threads: number | null;
  allow_nested_spawn: boolean;
  budget_policy: Record<string, unknown>;
  timeout_policy: Record<string, unknown>;
  stop_policy: Record<string, unknown>;
}

export interface WorkspaceCollaborationPolicyResponse {
  workspace_id: string;
  profile_name: string;
  policy_mode: "workspace";
  configured_enabled_role_ids: string[] | null;
  configured_role_tool_ids: Record<string, string[]> | null;
  effective_enabled_role_ids: string[];
  effective_role_tool_ids: Record<string, string[]>;
  available_roles: ExpertRoleSummary[];
  collaboration_policy: SessionCollaborationPolicy;
  policy_effect: "next_run_only";
}

export interface GlobalCollaborationPolicyResponse {
  scope: "global";
  profile_name: string;
  policy_mode: "global";
  configured_enabled_role_ids: string[] | null;
  configured_role_tool_ids: Record<string, string[]> | null;
  effective_enabled_role_ids: string[];
  effective_role_tool_ids: Record<string, string[]>;
  available_roles: ExpertRoleSummary[];
  collaboration_policy: SessionCollaborationPolicy;
  policy_effect: "next_run_only";
}

export interface UpdateWorkspaceCollaborationPolicyPayload {
  enabled_role_ids?: string[] | null;
  role_tool_ids?: Record<string, string[]> | null;
  collaboration_policy?: SessionCollaborationPolicy | null;
}

export interface ExpertDetail {
  name: string;
  description: string;
  system_prompt: string;
  model?: string | null;
  tools?: string[] | null;
  scope: string;
  source: ExpertRoleSource;
  catalog_visible?: boolean;
  host_selectable?: boolean;
  default_enabled?: boolean;
  visibility_source?: ExpertRoleVisibilitySource;
  lock_reason?: string | null;
}

export interface CreateExpertPayload {
  name: string;
  description: string;
  system_prompt: string;
  model?: string | null;
  tools?: string[] | null;
  scope?: "global" | "workspace";
}

export interface UpdateExpertPayload {
  description?: string | null;
  system_prompt?: string | null;
  model?: string | null;
  tools?: string[] | null;
}
