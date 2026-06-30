/**
 * LLM Provider API 客户端 - 简化版
 * 
 * 只管理服务商配置（base_url + api_key）
 * 模型配置由后端 Agent Runtime 自动处理
 */

import { apiRequest as sharedApiRequest } from "@/lib/api/httpClient";

// 接口格式类型 — 系统不关心具体服务商，只认接口格式
export type ProviderType = "openai_chat_completions" | "openai_responses" | "anthropic_messages";

// 模型用途类型
export type ModelType = "chat" | "embedding";

/**
 * 根据接口格式类型推断默认上下文长度
 * 不再硬编码任何模型映射，只按接口格式给保守默认值
 */
export function inferModelMaxContextSize(providerType: ProviderType): number {
  switch (providerType) {
    case "anthropic_messages":
      return 200000;
    case "openai_responses":
      return 128000;
    case "openai_chat_completions":
    default:
      return 128000;
  }
}

export function inferModelDefaults(providerType: ProviderType) {
  const max_context_size = inferModelMaxContextSize(providerType);
  const capabilities: ModelCapability[] = ["thinking", "image_in"];
  if (providerType === "openai_responses") {
    capabilities.push("always_thinking");
  }
  return { max_context_size, capabilities };
}

// LLM Provider 配置
export interface LLMProviderConfig {
  id: string;
  name: string;
  type: ProviderType;
  base_url: string;
  api_key?: string;  // 创建/更新时使用
  api_key_masked?: string;  // 查看时返回脱敏版本
  custom_headers?: Record<string, string>;
  env?: Record<string, string>;
  reasoning_key?: string | null;
  reasoning_format?: "general" | "deepseek-style" | null;
  enabled: boolean;
  is_default: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

// Provider（与后端响应一致）
export type LLMProviderConfigWithMeta = LLMProviderConfig

// Provider 模板（仅作为前端默认值参考）
export interface ProviderTemplate {
  name: string;
  type: ProviderType;
  base_url: string;
  description?: string;
}

// Provider 列表响应
export interface ProviderListResponse {
  providers: LLMProviderConfigWithMeta[];
  total: number;
}

// Provider 测试结果
export interface ProviderTestResult {
  provider_id: string;
  status: "success" | "error" | "timeout";
  latency_ms?: number;
  error_message?: string;
  tested_at: string;
}

// ==================== Model Types ====================

// 模型能力
export type ModelCapability = "image_in" | "video_in" | "thinking" | "always_thinking";

// LLM Model 配置
export interface LLMModelConfig {
  id: string;
  name: string;      // 显示名称
  provider: string;  // 关联的 provider ID
  model: string;     // 实际模型名称
  model_type?: ModelType;  // 模型用途类型
  dimension?: number;      // 向量维度（仅 embedding 模型）
  max_context_size: number;
  capabilities?: ModelCapability[];
  enabled?: boolean;
  is_default: boolean;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

// Model（与后端响应一致）
export type LLMModelConfigWithMeta = LLMModelConfig

// Model 列表响应
export interface ModelListResponse {
  models: LLMModelConfigWithMeta[];
  total: number;
}

export interface LLMModelDefaults {
  default_chat_model: string | null;
  default_embedding_model: string | null;
}

// 通用 API 请求函数
async function apiRequest<T>(
  method: string,
  endpoint: string,
  body?: unknown,
): Promise<T> {
  return sharedApiRequest<T>(endpoint, {
    method,
    body: body && method !== "GET" ? body : undefined,
  });
}

/**
 * 获取服务商模板（仅作为前端默认值参考）
 */
export async function getProviderTemplates(): Promise<Record<string, ProviderTemplate>> {
  return apiRequest("GET", "/api/llm/templates");
}

/**
 * 初始化默认配置
 */
export async function initializeDefaults(): Promise<{ message: string }> {
  return apiRequest("POST", "/api/llm/initialize");
}

// ==================== Provider API ====================

/**
 * 获取服务商列表
 */
export async function getProviders(enabledOnly = false): Promise<ProviderListResponse> {
  const params = new URLSearchParams();
  params.append("enabled_only", enabledOnly.toString());
  return apiRequest("GET", `/api/llm/providers?${params.toString()}`);
}

/**
 * 获取服务商详情
 */
export async function getProvider(
  id: string): Promise<LLMProviderConfig> {
  return apiRequest("GET", `/api/llm/providers/${id}`, undefined);
}

/**
 * 创建服务商
 */
export async function createProvider(
  config: Omit<LLMProviderConfig, "created_at" | "updated_at" | "api_key_masked">): Promise<LLMProviderConfig> {
  return apiRequest("POST", "/api/llm/providers", config);
}

/**
 * 更新服务商
 */
export async function updateProvider(
  id: string,
  updates: Partial<Omit<LLMProviderConfig, "id" | "created_at" | "updated_at" | "api_key_masked">>): Promise<LLMProviderConfig> {
  return apiRequest("PATCH", `/api/llm/providers/${id}`, updates);
}

/**
 * 删除服务商
 */
export async function deleteProvider(
  id: string): Promise<{ success: boolean }> {
  return apiRequest("DELETE", `/api/llm/providers/${id}`, undefined);
}

/**
 * 测试服务商连通性
 */
export async function testProvider(
  id: string): Promise<ProviderTestResult> {
  return apiRequest("POST", `/api/llm/providers/${id}/test`, undefined);
}

// ==================== Remote Model Fetching ====================

// 远程模型信息
export interface RemoteModelInfo {
  model_name: string;
  owned_by?: string;
  display_name?: string;
  context_length?: number;
  supports_reasoning?: boolean;
  supports_image_in?: boolean;
  supports_video_in?: boolean;
}

// 获取远程模型列表结果
export interface FetchModelsResult {
  provider_id: string;
  models: RemoteModelInfo[];
  success: boolean;
  error_message?: string;
  unsupported: boolean;
}

// 批量创建模型请求
export interface BatchCreateModelsRequest {
  provider_id: string;
  models: RemoteModelInfo[];
}

/**
 * 从 Provider API 获取可用模型列表
 */
export async function fetchProviderModels(
  providerId: string): Promise<FetchModelsResult> {
  return apiRequest("POST", `/api/llm/providers/${providerId}/fetch-models`, undefined);
}

/**
 * 批量创建模型（幂等，已存在的跳过）
 */
export async function batchCreateModels(
  request: BatchCreateModelsRequest): Promise<ModelListResponse> {
  return apiRequest("POST", "/api/llm/models/batch", request);
}

// ==================== Model API ====================

/**
 * 获取模型列表
 */
export async function getModels(enabledOnly = false, providerId?: string): Promise<ModelListResponse> {
  const params = new URLSearchParams();
  if (enabledOnly) {
    params.append("enabled_only", "true");
  }
  if (providerId) {
    params.append("provider_id", providerId);
  }
  const queryString = params.toString();
  const endpoint = `/api/llm/models${queryString ? `?${queryString}` : ""}`;
  
  return apiRequest("GET", endpoint, undefined);
}

function getModelByIdEndpoint(id: string, suffix = ""): string {
  const params = new URLSearchParams({ model_id: id });
  return `/api/llm/models/by-id${suffix}?${params.toString()}`;
}

/**
 * 获取模型详情
 */
export async function getModel(
  id: string): Promise<LLMModelConfig> {
  return apiRequest("GET", getModelByIdEndpoint(id), undefined);
}

/**
 * 创建模型
 */
export async function createModel(
  config: Omit<LLMModelConfig, "created_at" | "updated_at">): Promise<LLMModelConfig> {
  return apiRequest("POST", "/api/llm/models", config);
}

/**
 * 更新模型
 */
export async function updateModel(
  id: string,
  updates: Partial<Omit<LLMModelConfig, "id" | "created_at" | "updated_at">>): Promise<LLMModelConfig> {
  return apiRequest("PATCH", getModelByIdEndpoint(id), updates);
}

/**
 * 删除模型
 */
export async function deleteModel(
  id: string): Promise<{ success: boolean }> {
  return apiRequest("DELETE", getModelByIdEndpoint(id), undefined);
}

/**
 * 设置默认模型
 */
export async function setDefaultModel(
  id: string): Promise<LLMModelConfig> {
  return apiRequest("POST", getModelByIdEndpoint(id, "/default"), undefined)
}

export async function getModelDefaults(): Promise<LLMModelDefaults> {
  return apiRequest("GET", "/api/llm/defaults", undefined);
}

export async function updateModelDefaults(
  defaults: LLMModelDefaults,
): Promise<LLMModelDefaults> {
  return apiRequest("PUT", "/api/llm/defaults", defaults);
}
