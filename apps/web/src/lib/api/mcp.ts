/**
 * MCP API 客户端（三层合并模型）
 */

import { ApiRequestError, apiRequest as sharedApiRequest } from "@/lib/api/httpClient";

// MCP Server 配置类型
export interface MCPServerConfig {
  name: string;
  type: "streamable-http" | "stdio" | "sse";
  url?: string;
  headers?: Record<string, string>;
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  enabled: boolean;
  description?: string;
  timeout_ms?: number;
  is_system_default?: boolean;
}

export interface MCPStoreEnvField {
  name: string;
  required: boolean;
  description?: string;
  default_value?: string;
}

// 我的默认中的 MCP server
export interface MCPStoreServer {
  name: string;
  display_name: string;
  type: string;
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  env?: Record<string, string>;
  env_schema?: Record<string, string>;
  env_fields?: MCPStoreEnvField[];
  readme_excerpt?: string;
  description?: string;
  timeout_ms?: number;
  is_system_default: boolean;
  auto_attach_modes?: string[];
  enabled_tools?: string[];
}

export interface MCPStoreListResponse {
  servers: MCPStoreServer[];
  total: number;
}

// 工作区 MCP server（合并后的有效配置）
export interface MCPWorkspaceServer {
  name: string;
  display_name: string;
  type: string;
  url?: string;
  command?: string;
  args?: string[];
  headers?: Record<string, string>;
  env?: Record<string, string>;
  env_schema?: Record<string, string>;
  description?: string;
  timeout_ms?: number;
  enabled: boolean;
  is_system_default: boolean;
  auto_attach_modes?: string[];
  enabled_tools?: string[];
}

export interface MCPWorkspaceListResponse {
  servers: MCPWorkspaceServer[];
  total: number;
}

// MCP 工具信息
export interface MCPToolInfo {
  name: string;
  description?: string;
}

// MCP 测试结果
export interface MCPTestResult {
  name: string;
  status: "connected" | "disconnected" | "error";
  tools_count: number;
  tools: MCPToolInfo[];
  error_message?: string;
  latency_ms?: number;
}

// 工作区 MCP server 工具列表响应
export interface MCPWorkspaceToolsResponse {
  server_name: string;
  tools: MCPToolInfo[];
  enabled_tools: string[];
}

// 通用 API 请求函数
async function apiRequest<T>(
  method: string,
  endpoint: string,
  body?: unknown
): Promise<T> {
  try {
    return await sharedApiRequest<T>(endpoint, {
      method,
      body: body && method !== "GET" ? body : undefined,
    });
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) {
      throw new Error("NOT_FOUND");
    }
    throw error;
  }
}

// ===== 我的默认 API =====

export async function getMCPStoreList(): Promise<MCPStoreListResponse> {
  return apiRequest("GET", "/api/mcp/store");
}

export async function saveMCPStoreServer(
  config: MCPServerConfig
): Promise<{ success: boolean; message: string }> {
  return apiRequest("POST", "/api/mcp/store", config);
}

export async function deleteMCPStoreServer(name: string): Promise<{ success: boolean; message: string }> {
  return apiRequest("DELETE", `/api/mcp/store/${encodeURIComponent(name)}`);
}

export async function updateMCPStoreEnv(
  name: string,
  env: Record<string, string>
): Promise<{ success: boolean; message: string }> {
  return apiRequest("PUT", `/api/mcp/store/${encodeURIComponent(name)}/env`, { env });
}

// ===== 工作区配置 API =====

export async function getMCPWorkspaceList(
  workspaceId: string,
  scope?: "effective" | "workspace"
): Promise<MCPWorkspaceListResponse> {
  const query = scope ? `?scope=${scope}` : "";
  return apiRequest("GET", `/api/mcp/workspaces/${encodeURIComponent(workspaceId)}${query}`);
}

export async function addMCPWorkspaceServer(
  workspaceId: string,
  serverName: string
): Promise<{ success: boolean; message: string }> {
  return apiRequest("POST", `/api/mcp/workspaces/${encodeURIComponent(workspaceId)}/servers/${encodeURIComponent(serverName)}`);
}

export async function removeMCPWorkspaceServer(
  workspaceId: string,
  serverName: string
): Promise<{ success: boolean; message: string }> {
  return apiRequest("DELETE", `/api/mcp/workspaces/${encodeURIComponent(workspaceId)}/servers/${encodeURIComponent(serverName)}`);
}

// ===== 健康检查 =====

export async function testMCPConnection(
  name: string,
  workspaceId?: string
): Promise<MCPTestResult> {
  if (workspaceId) {
    return apiRequest(
      "POST",
      `/api/mcp/workspaces/${encodeURIComponent(workspaceId)}/servers/${encodeURIComponent(name)}/test`,
    );
  }
  return apiRequest("POST", `/api/mcp/store/${encodeURIComponent(name)}/test`);
}

// ===== 工具列表管理 =====

export async function getMCPWorkspaceServerTools(
  workspaceId: string,
  serverName: string
): Promise<MCPWorkspaceToolsResponse> {
  return apiRequest(
    "GET",
    `/api/mcp/workspaces/${encodeURIComponent(workspaceId)}/servers/${encodeURIComponent(serverName)}/tools`
  );
}

export async function updateMCPWorkspaceServerEnabledTools(
  workspaceId: string,
  serverName: string,
  enabledTools: string[]
): Promise<{ success: boolean; message: string }> {
  return apiRequest(
    "PUT",
    `/api/mcp/workspaces/${encodeURIComponent(workspaceId)}/servers/${encodeURIComponent(serverName)}/tools`,
    { enabled_tools: enabledTools }
  );
}
