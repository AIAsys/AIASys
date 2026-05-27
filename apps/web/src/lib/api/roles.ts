import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  CreateExpertPayload,
  ExpertDetail as ExpertDetailResponse,
  GlobalCollaborationPolicyResponse,
  GlobalExpertCatalogResponse,
  ExpertRoleVisibilitySource,
  ExpertRoleVisibilityState,
  ExpertRoleSummary,
  WorkspaceCollaborationPolicyResponse,
  UpdateExpertPayload,
  UpdateExpertRoleVisibilityPayload,
  UpdateExpertRoleVisibilityResponse,
  UpdateWorkspaceCollaborationPolicyPayload,
  WorkspaceExpertCatalogResponse,
} from "@/types/expertRoles";

export type RoleManagerScope = "global" | "workspace";

export interface RoleItem {
  name: string;
  displayName: string;
  description: string;
  model: string | null;
  scope: string;
  source: string;
  status: string;
  toolNames: string[];
  toolCount: number;
  permissions: string[];
  capabilities: string[];
  catalogVisible: boolean;
  hostSelectable: boolean;
  defaultEnabled: boolean;
  visibilitySource: ExpertRoleVisibilitySource;
  installedToGlobal: boolean;
  installedToWorkspace: boolean;
  installedScope: "system" | "global" | "workspace";
  lockReason: string | null;
}

export interface RoleDetail {
  name: string;
  displayName: string;
  description: string;
  model: string | null;
  scope: string;
  source: string;
  status: string;
  system_prompt: string;
  tools: string[];
  manifest: Record<string, unknown>;
}

export type RoleCreatePayload = CreateExpertPayload;

export type RoleUpdatePayload = UpdateExpertPayload;

export type RoleVisibilityUpdatePayload = UpdateExpertRoleVisibilityPayload;

const ROLE_QUERY_CACHE_TTL_MS = 1000;

interface RoleQueryCacheEntry<T> {
  expiresAt: number;
  promise: Promise<T>;
}

const roleQueryCache = new Map<string, RoleQueryCacheEntry<unknown>>();

function cachedRoleQuery<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
  const now = Date.now();
  const cached = roleQueryCache.get(key) as RoleQueryCacheEntry<T> | undefined;
  if (cached && cached.expiresAt > now) {
    return cached.promise;
  }

  const promise = fetcher().catch((error) => {
    roleQueryCache.delete(key);
    throw error;
  });
  roleQueryCache.set(key, {
    expiresAt: now + ROLE_QUERY_CACHE_TTL_MS,
    promise,
  });
  return promise;
}

function invalidateRoleQueryCache() {
  roleQueryCache.clear();
}

const DEFAULT_VISIBILITY: ExpertRoleVisibilityState = {
  catalog_visible: true,
  host_selectable: true,
  default_enabled: false,
  visibility_source: "system",
  lock_reason: null,
};

function normalizeRoleVisibility(
  role: Partial<ExpertRoleVisibilityState>,
): ExpertRoleVisibilityState {
  return {
    catalog_visible: role.catalog_visible ?? DEFAULT_VISIBILITY.catalog_visible,
    host_selectable: role.host_selectable ?? DEFAULT_VISIBILITY.host_selectable,
    default_enabled: role.default_enabled ?? DEFAULT_VISIBILITY.default_enabled,
    visibility_source: role.visibility_source ?? DEFAULT_VISIBILITY.visibility_source,
    installed_to_global: role.installed_to_global ?? false,
    installed_to_workspace: role.installed_to_workspace ?? false,
    installed_scope: role.installed_scope ?? "system",
    lock_reason: role.lock_reason ?? null,
  };
}

function normalizeExpertRoleSummary(role: ExpertRoleSummary): ExpertRoleSummary {
  const visibility = normalizeRoleVisibility(role);
  return {
    ...role,
    catalog_visible: visibility.catalog_visible,
    host_selectable: visibility.host_selectable,
    default_enabled: visibility.default_enabled,
    visibility_source: visibility.visibility_source,
    lock_reason: visibility.lock_reason,
  };
}

function normalizeWorkspaceCollaborationPolicy(
  policy: WorkspaceCollaborationPolicyResponse,
): WorkspaceCollaborationPolicyResponse {
  return {
    ...policy,
    available_roles: policy.available_roles.map(normalizeExpertRoleSummary),
  };
}

function normalizeGlobalCollaborationPolicy(
  policy: GlobalCollaborationPolicyResponse,
): GlobalCollaborationPolicyResponse {
  return {
    ...policy,
    available_roles: policy.available_roles.map(normalizeExpertRoleSummary),
  };
}

function roleItemFromSummary(
  role: ExpertRoleSummary,
  scope: RoleManagerScope,
): RoleItem {
  const normalizedRole = normalizeExpertRoleSummary(role);
  const visibility = normalizeRoleVisibility(normalizedRole);
  return {
    name: normalizedRole.role_id,
    displayName: normalizedRole.display_name || normalizedRole.role_id,
    description: normalizedRole.description,
    model: normalizedRole.default_model,
    scope,
    source: normalizedRole.source,
    status: "active",
    toolNames: normalizedRole.tool_names,
    toolCount: normalizedRole.tool_count,
    permissions: normalizedRole.permissions,
    capabilities: normalizedRole.capabilities,
    catalogVisible: visibility.catalog_visible,
    hostSelectable: visibility.host_selectable,
    defaultEnabled: visibility.default_enabled,
    visibilitySource: visibility.visibility_source,
    installedToGlobal: normalizedRole.installed_to_global ?? false,
    installedToWorkspace: normalizedRole.installed_to_workspace ?? false,
    installedScope: normalizedRole.installed_scope ?? "system",
    lockReason: visibility.lock_reason,
  };
}

function roleItemFromDetail(detail: ExpertDetailResponse): RoleItem {
  const visibility = normalizeRoleVisibility(detail);
  return {
    name: detail.name,
    displayName: detail.name,
    description: detail.description,
    model: detail.model ?? null,
    scope: detail.scope,
    source: detail.source,
    status: "active",
    toolNames: detail.tools ?? [],
    toolCount: detail.tools?.length ?? 0,
    permissions: [],
    capabilities: [],
    catalogVisible: visibility.catalog_visible,
    hostSelectable: visibility.host_selectable,
    defaultEnabled: visibility.default_enabled,
    visibilitySource: visibility.visibility_source,
    installedToGlobal: Boolean(detail.scope === "global"),
    installedToWorkspace: Boolean(detail.scope === "workspace"),
    installedScope: detail.scope === "workspace" ? "workspace" : detail.scope === "global" ? "global" : "system",
    lockReason: visibility.lock_reason,
  };
}

function roleDetailFromExpert(detail: ExpertDetailResponse): RoleDetail {
  return {
    ...roleItemFromDetail(detail),
    system_prompt: detail.system_prompt,
    tools: detail.tools ?? [],
    manifest: {},
  };
}

export async function listRoles(workspaceId: string): Promise<RoleItem[]> {
  const catalog = await cachedRoleQuery(
    `workspace-catalog:${workspaceId}`,
    () => apiRequest<WorkspaceExpertCatalogResponse>(
      API_ENDPOINTS.WORKSPACE_EXPERTS(workspaceId),
      { cache: "no-store" },
    ),
  );
  return catalog.roles
    .map(normalizeExpertRoleSummary)
    .map((role) => roleItemFromSummary(role, "workspace"));
}

export async function listGlobalRoles(): Promise<RoleItem[]> {
  const catalog = await cachedRoleQuery(
    "global-catalog",
    () => apiRequest<GlobalExpertCatalogResponse>(
      API_ENDPOINTS.GLOBAL_EXPERTS,
      { cache: "no-store" },
    ),
  );
  return catalog.roles
    .map(normalizeExpertRoleSummary)
    .map((role) => roleItemFromSummary(role, "global"));
}

export function listRolesForScope(
  scope: RoleManagerScope,
  workspaceId?: string | null,
): Promise<RoleItem[]> {
  if (scope === "global") {
    return listGlobalRoles();
  }
  if (!workspaceId) {
    return Promise.resolve([]);
  }
  return listRoles(workspaceId);
}

export async function listInstalledRolesForScope(
  scope: RoleManagerScope,
  workspaceId?: string | null,
): Promise<RoleItem[]> {
  if (scope === "global") {
    const policy = await getGlobalExpertPolicy();
    return policy.available_roles
      .map(normalizeExpertRoleSummary)
      .map((role) => roleItemFromSummary(role, "global"));
  }
  if (!workspaceId) {
    return [];
  }
  const policy = await getWorkspaceExpertPolicy(workspaceId);
  return policy.available_roles
    .map(normalizeExpertRoleSummary)
    .map((role) => roleItemFromSummary(role, "workspace"));
}

export function getWorkspaceRoleDetail(
  workspaceId: string,
  name: string,
): Promise<RoleDetail> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.WORKSPACE_EXPERT_DETAIL(workspaceId, name),
    { cache: "no-store" },
  ).then(roleDetailFromExpert);
}

export function getGlobalRoleDetail(name: string): Promise<RoleDetail> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.GLOBAL_EXPERT_DETAIL(name),
    { cache: "no-store" },
  ).then(roleDetailFromExpert);
}

export function getRoleDetail(
  workspaceId: string,
  name: string,
): Promise<RoleDetail> {
  return getWorkspaceRoleDetail(workspaceId, name);
}

export function getRoleDetailForScope(
  scope: RoleManagerScope,
  name: string,
  workspaceId?: string | null,
): Promise<RoleDetail> {
  if (scope === "global") {
    return getGlobalRoleDetail(name);
  }
  if (!workspaceId) {
    return Promise.reject(new Error("缺少工作区 ID"));
  }
  return getWorkspaceRoleDetail(workspaceId, name);
}

export function createWorkspaceRole(
  workspaceId: string,
  payload: RoleCreatePayload,
): Promise<RoleItem> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.WORKSPACE_EXPERTS(workspaceId),
    {
      method: "POST",
      body: payload,
    },
  ).then((detail) => {
    invalidateRoleQueryCache();
    return roleItemFromDetail(detail);
  });
}

export function createGlobalRole(
  payload: RoleCreatePayload,
): Promise<RoleItem> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.GLOBAL_EXPERTS,
    {
      method: "POST",
      body: { ...payload, scope: "global" },
    },
  ).then((detail) => {
    invalidateRoleQueryCache();
    return roleItemFromDetail(detail);
  });
}

export function createRole(
  workspaceId: string,
  payload: RoleCreatePayload,
): Promise<RoleItem> {
  return createWorkspaceRole(workspaceId, payload);
}

export function createRoleForScope(
  scope: RoleManagerScope,
  payload: RoleCreatePayload,
  workspaceId?: string | null,
): Promise<RoleItem> {
  if (scope === "global") {
    return createGlobalRole(payload);
  }
  if (!workspaceId) {
    return Promise.reject(new Error("缺少工作区 ID"));
  }
  return createWorkspaceRole(workspaceId, { ...payload, scope: "workspace" });
}

export function enableGlobalBuiltinRole(name: string): Promise<RoleItem> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.GLOBAL_EXPERT_ENABLE(name),
    {
      method: "POST",
      body: { role_id: name },
    },
  ).then((detail) => {
    invalidateRoleQueryCache();
    return roleItemFromDetail(detail);
  });
}

export function enableWorkspaceBuiltinRole(
  workspaceId: string,
  name: string,
): Promise<RoleItem> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.WORKSPACE_EXPERT_ENABLE(workspaceId, name),
    {
      method: "POST",
      body: { role_id: name },
    },
  ).then((detail) => {
    invalidateRoleQueryCache();
    return roleItemFromDetail(detail);
  });
}

export function updateWorkspaceRole(
  workspaceId: string,
  name: string,
  payload: RoleUpdatePayload,
): Promise<RoleItem> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.WORKSPACE_EXPERT_DETAIL(workspaceId, name),
    {
      method: "PUT",
      body: payload,
    },
  ).then((detail) => {
    invalidateRoleQueryCache();
    return roleItemFromDetail(detail);
  });
}

export function updateGlobalRole(
  name: string,
  payload: RoleUpdatePayload,
): Promise<RoleItem> {
  return apiRequest<ExpertDetailResponse>(
    API_ENDPOINTS.GLOBAL_EXPERT_DETAIL(name),
    {
      method: "PUT",
      body: payload,
    },
  ).then((detail) => {
    invalidateRoleQueryCache();
    return roleItemFromDetail(detail);
  });
}

export function updateRole(
  workspaceId: string,
  name: string,
  payload: RoleUpdatePayload,
): Promise<RoleItem> {
  return updateWorkspaceRole(workspaceId, name, payload);
}

export function updateRoleForScope(
  scope: RoleManagerScope,
  name: string,
  payload: RoleUpdatePayload,
  workspaceId?: string | null,
): Promise<RoleItem> {
  if (scope === "global") {
    return updateGlobalRole(name, payload);
  }
  if (!workspaceId) {
    return Promise.reject(new Error("缺少工作区 ID"));
  }
  return updateWorkspaceRole(workspaceId, name, payload);
}

export function deleteWorkspaceRole(
  workspaceId: string,
  name: string,
): Promise<{ success: boolean; name: string }> {
  return apiRequest<{ success: boolean; name: string }>(
    API_ENDPOINTS.WORKSPACE_EXPERT_DETAIL(workspaceId, name),
    { method: "DELETE" },
  ).then((result) => {
    invalidateRoleQueryCache();
    return result;
  });
}

export function deleteGlobalRole(
  name: string,
): Promise<{ success: boolean; name: string }> {
  return apiRequest<{ success: boolean; name: string }>(
    API_ENDPOINTS.GLOBAL_EXPERT_DETAIL(name),
    { method: "DELETE" },
  ).then((result) => {
    invalidateRoleQueryCache();
    return result;
  });
}

export function deleteRole(
  workspaceId: string,
  name: string,
): Promise<{ success: boolean; name: string }> {
  return deleteWorkspaceRole(workspaceId, name);
}

export function deleteRoleForScope(
  scope: RoleManagerScope,
  name: string,
  workspaceId?: string | null,
): Promise<{ success: boolean; name: string }> {
  if (scope === "global") {
    return deleteGlobalRole(name);
  }
  if (!workspaceId) {
    return Promise.reject(new Error("缺少工作区 ID"));
  }
  return deleteWorkspaceRole(workspaceId, name);
}

export function updateWorkspaceRoleVisibility(
  workspaceId: string,
  name: string,
  payload: RoleVisibilityUpdatePayload,
): Promise<ExpertRoleVisibilityState> {
  return apiRequest<UpdateExpertRoleVisibilityResponse>(
    API_ENDPOINTS.WORKSPACE_EXPERT_VISIBILITY(workspaceId, name),
    {
      method: "PUT",
      body: payload,
    },
  ).then((visibility) => {
    invalidateRoleQueryCache();
    return normalizeRoleVisibility(visibility);
  });
}

export function updateGlobalRoleVisibility(
  name: string,
  payload: RoleVisibilityUpdatePayload,
): Promise<ExpertRoleVisibilityState> {
  return apiRequest<UpdateExpertRoleVisibilityResponse>(
    API_ENDPOINTS.GLOBAL_EXPERT_VISIBILITY(name),
    {
      method: "PUT",
      body: payload,
    },
  ).then((visibility) => {
    invalidateRoleQueryCache();
    return normalizeRoleVisibility(visibility);
  });
}

export function updateRoleVisibility(
  workspaceId: string,
  name: string,
  payload: RoleVisibilityUpdatePayload,
): Promise<ExpertRoleVisibilityState> {
  return updateWorkspaceRoleVisibility(workspaceId, name, payload);
}

export function updateRoleVisibilityForScope(
  scope: RoleManagerScope,
  name: string,
  payload: RoleVisibilityUpdatePayload,
  workspaceId?: string | null,
): Promise<ExpertRoleVisibilityState> {
  if (scope === "global") {
    return updateGlobalRoleVisibility(name, payload);
  }
  if (!workspaceId) {
    return Promise.reject(new Error("缺少工作区 ID"));
  }
  return updateWorkspaceRoleVisibility(workspaceId, name, payload);
}

export function getWorkspaceExpertPolicy(
  workspaceId: string,
): Promise<WorkspaceCollaborationPolicyResponse> {
  return cachedRoleQuery(
    `workspace-policy:${workspaceId}`,
    () => apiRequest<WorkspaceCollaborationPolicyResponse>(
      API_ENDPOINTS.WORKSPACE_EXPERT_POLICY(workspaceId),
      { cache: "no-store" },
    ),
  ).then(normalizeWorkspaceCollaborationPolicy);
}

export function getGlobalExpertPolicy(): Promise<GlobalCollaborationPolicyResponse> {
  return cachedRoleQuery(
    "global-policy",
    () => apiRequest<GlobalCollaborationPolicyResponse>(
      API_ENDPOINTS.GLOBAL_EXPERT_POLICY,
      { cache: "no-store" },
    ),
  ).then(normalizeGlobalCollaborationPolicy);
}

export function updateWorkspaceExpertPolicy(
  workspaceId: string,
  payload: UpdateWorkspaceCollaborationPolicyPayload,
): Promise<WorkspaceCollaborationPolicyResponse> {
  return apiRequest<WorkspaceCollaborationPolicyResponse>(
    API_ENDPOINTS.WORKSPACE_EXPERT_POLICY(workspaceId),
    {
      method: "PUT",
      body: payload,
    },
  ).then((policy) => {
    invalidateRoleQueryCache();
    return normalizeWorkspaceCollaborationPolicy(policy);
  });
}

export function updateGlobalExpertPolicy(
  payload: UpdateWorkspaceCollaborationPolicyPayload,
): Promise<GlobalCollaborationPolicyResponse> {
  return apiRequest<GlobalCollaborationPolicyResponse>(
    API_ENDPOINTS.GLOBAL_EXPERT_POLICY,
    {
      method: "PUT",
      body: payload,
    },
  ).then((policy) => {
    invalidateRoleQueryCache();
    return normalizeGlobalCollaborationPolicy(policy);
  });
}
