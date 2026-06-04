import { API_ENDPOINTS } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";

export interface CapabilityItem {
  capability_id: string;
  kind: "skill_pack" | "mcp_server" | "subagent" | "native_tool" | "runtime_helper";
  display_name: string;
  description: string;
  version: string;
  author: string;
  dependencies: string[];
  config_schema: Record<string, unknown>;
  source: string;
  tool_names: string[];
}

export interface WorkspaceCapabilityItem {
  capability_id: string;
  kind: string;
  display_name: string;
  description: string;
  version: string;
  enabled: boolean;
  source: string;
  status: string;
  error_message: string;
}

export interface CapabilityActionResponse {
  success: boolean;
  capability_id: string;
  message: string;
}

export interface VerifyCapabilityResponse {
  capability_id: string;
  status: string;
  detail: string;
  ok: boolean;
}

export async function listAvailableCapabilities(): Promise<CapabilityItem[]> {
  const data = await apiRequest<{ capabilities: CapabilityItem[]; total: number }>(
    API_ENDPOINTS.CAPABILITIES_AVAILABLE,
    { cache: "no-store" },
  );
  return data.capabilities ?? [];
}

export async function listWorkspaceCapabilities(
  workspaceId: string,
): Promise<WorkspaceCapabilityItem[]> {
  const data = await apiRequest<{
    workspace_id: string;
    capabilities: WorkspaceCapabilityItem[];
    total: number;
  }>(API_ENDPOINTS.WORKSPACE_CAPABILITIES(workspaceId), { cache: "no-store" });
  return data.capabilities ?? [];
}

export async function installCapability(
  workspaceId: string,
  capabilityId: string,
  config?: Record<string, unknown>,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(
    API_ENDPOINTS.WORKSPACE_CAPABILITY_INSTALL(workspaceId),
    {
      method: "POST",
      body: { capability_id: capabilityId, config },
    },
  );
}

export async function uninstallCapability(
  workspaceId: string,
  capabilityId: string,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(
    API_ENDPOINTS.WORKSPACE_CAPABILITY_UNINSTALL(workspaceId),
    {
      method: "POST",
      body: { capability_id: capabilityId },
    },
  );
}

export async function activateCapability(
  workspaceId: string,
  capabilityId: string,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(
    API_ENDPOINTS.WORKSPACE_CAPABILITY_ACTIVATE(workspaceId),
    {
      method: "POST",
      body: { capability_id: capabilityId },
    },
  );
}

export async function deactivateCapability(
  workspaceId: string,
  capabilityId: string,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(
    API_ENDPOINTS.WORKSPACE_CAPABILITY_DEACTIVATE(workspaceId),
    {
      method: "POST",
      body: { capability_id: capabilityId },
    },
  );
}

export async function verifyCapability(
  workspaceId: string,
  capabilityId: string,
): Promise<VerifyCapabilityResponse> {
  return apiRequest<VerifyCapabilityResponse>(
    API_ENDPOINTS.WORKSPACE_CAPABILITY_VERIFY(workspaceId),
    {
      method: "POST",
      body: { capability_id: capabilityId },
    },
  );
}

// ---- global scope ----

export async function listGlobalCapabilities(): Promise<WorkspaceCapabilityItem[]> {
  const data = await apiRequest<{
    workspace_id: string;
    capabilities: WorkspaceCapabilityItem[];
    total: number;
  }>(API_ENDPOINTS.GLOBAL_CAPABILITIES, { cache: "no-store" });
  return data.capabilities ?? [];
}

export async function installGlobalCapability(
  capabilityId: string,
  config?: Record<string, unknown>,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(API_ENDPOINTS.GLOBAL_CAPABILITY_INSTALL, {
    method: "POST",
    body: { capability_id: capabilityId, config },
  });
}

export async function uninstallGlobalCapability(
  capabilityId: string,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(API_ENDPOINTS.GLOBAL_CAPABILITY_UNINSTALL, {
    method: "POST",
    body: { capability_id: capabilityId },
  });
}

export async function activateGlobalCapability(
  capabilityId: string,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(API_ENDPOINTS.GLOBAL_CAPABILITY_ACTIVATE, {
    method: "POST",
    body: { capability_id: capabilityId },
  });
}

export async function deactivateGlobalCapability(
  capabilityId: string,
): Promise<CapabilityActionResponse> {
  return apiRequest<CapabilityActionResponse>(API_ENDPOINTS.GLOBAL_CAPABILITY_DEACTIVATE, {
    method: "POST",
    body: { capability_id: capabilityId },
  });
}

export async function verifyGlobalCapability(
  capabilityId: string,
): Promise<VerifyCapabilityResponse> {
  return apiRequest<VerifyCapabilityResponse>(API_ENDPOINTS.GLOBAL_CAPABILITY_VERIFY, {
    method: "POST",
    body: { capability_id: capabilityId },
  });
}

export interface CapabilitySourceResponse {
  capability_id: string;
  file: string;
  content: string;
}

export interface CapabilitySourceTreeEntry {
  path: string;
  name: string;
  is_dir: boolean;
}

export interface CapabilitySourceTreeResponse {
  capability_id: string;
  entries: CapabilitySourceTreeEntry[];
}

export async function getCapabilitySourceFile(
  capabilityId: string,
  file: string = "SKILL.md",
): Promise<CapabilitySourceResponse | null> {
  try {
    return await apiRequest<CapabilitySourceResponse>(
      API_ENDPOINTS.CAPABILITY_SOURCE(capabilityId, file),
      { cache: "no-store" },
    );
  } catch (error) {
    console.error(
      `[capabilities] getCapabilitySourceFile failed: capabilityId=${capabilityId}, file=${file}`,
      error,
    );
    return null;
  }
}

export async function listCapabilitySourceTree(
  capabilityId: string,
): Promise<CapabilitySourceTreeResponse | null> {
  try {
    return await apiRequest<CapabilitySourceTreeResponse>(
      API_ENDPOINTS.CAPABILITY_SOURCE_TREE(capabilityId),
      { cache: "no-store" },
    );
  } catch (error) {
    console.error(
      `[capabilities] listCapabilitySourceTree failed: capabilityId=${capabilityId}`,
      error,
    );
    return null;
  }
}
