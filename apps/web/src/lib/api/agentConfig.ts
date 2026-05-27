/**
 * Agent 配置 API
 */

import { apiFetch } from "./httpClient";
import type {
  EditableConfigResponse,
  AgentMode,
  MergeStrategy,
  MergedConfigResponse,
  SystemConfigResponse,
  UserConfigResponse,
} from "@/types/agentConfig";

/**
 * 获取合并后的配置（预览用）
 */
export async function getMergedConfig(
  mode: AgentMode,
  sessionId?: string,
  workspaceId?: string,
): Promise<MergedConfigResponse> {
  const res = await apiFetch(`/api/agent-config/${mode}`, {
    query: {
      session_id: sessionId,
      workspace_id: workspaceId,
    },
  });
  if (!res.ok) {
    throw new Error("获取配置失败");
  }
  return res.json();
}

/**
 * 获取用户自定义配置（编辑用）
 */
export async function getUserConfig(mode: AgentMode): Promise<UserConfigResponse> {
  const res = await apiFetch(`/api/agent-config/${mode}/user`);
  if (!res.ok) {
    throw new Error("获取用户配置失败");
  }
  return res.json();
}

/**
 * 获取当前会话编辑配置
 */
export async function getSessionEditorConfig(
  mode: AgentMode,
  sessionId: string,
): Promise<EditableConfigResponse> {
  const res = await apiFetch(`/api/agent-config/${mode}/editor`, {
    query: {
      session_id: sessionId,
    },
  });
  if (!res.ok) {
    throw new Error("获取当前会话配置失败");
  }
  return res.json();
}

/**
 * 获取工作区编辑配置
 */
export async function getWorkspaceEditorConfig(
  mode: AgentMode,
  workspaceId: string,
): Promise<EditableConfigResponse> {
  const res = await apiFetch(`/api/agent-config/${mode}/workspace/editor`, {
    query: {
      workspace_id: workspaceId,
    },
  });
  if (!res.ok) {
    throw new Error("获取工作区配置失败");
  }
  return res.json();
}

/**
 * 更新提示词覆盖
 */
export async function updatePrompt(
  mode: AgentMode,
  content: string,
  sessionId?: string,
  workspaceId?: string,
): Promise<void> {
  const res = await apiFetch(`/api/agent-config/${mode}/prompt`, {
    method: "PUT",
    query: {
      session_id: sessionId,
      workspace_id: workspaceId,
    },
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
  });
  if (!res.ok) {
    throw new Error("保存提示词失败");
  }
}

/**
 * 更新工具配置
 */
export async function updateTools(
  mode: AgentMode,
  tools: {
    enabledTools?: string[];
    disabledTools?: string[];
    extraTools?: string[];
    toolStrategy?: "auto" | "search" | "deferred" | "passthrough";
  },
  sessionId?: string,
  workspaceId?: string,
): Promise<void> {
  const res = await apiFetch(`/api/agent-config/${mode}/tools`, {
    method: "PUT",
    query: {
      session_id: sessionId,
      workspace_id: workspaceId,
    },
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      enabled_tools: tools.enabledTools,
      disabled_tools: tools.disabledTools ?? [],
      extra_tools: tools.extraTools ?? [],
      tool_strategy: tools.toolStrategy ?? "auto",
    }),
  });
  if (!res.ok) {
    throw new Error("保存工具配置失败");
  }
}

/**
 * 更新运行时自动压缩配置
 */
export async function updateRuntimeConfig(
  mode: AgentMode,
  runtimeConfig: {
    reserved_context_size?: number;
    compaction_trigger_ratio?: number;
  },
  sessionId?: string,
  workspaceId?: string,
): Promise<void> {
  const res = await apiFetch(`/api/agent-config/${mode}/runtime`, {
    method: "PUT",
    query: {
      session_id: sessionId,
      workspace_id: workspaceId,
    },
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(runtimeConfig),
  });
  if (!res.ok) {
    throw new Error("保存自动压缩策略失败");
  }
}

/**
 * 重置为系统默认配置
 */
export async function resetToDefault(mode: AgentMode): Promise<void> {
  const res = await apiFetch(`/api/agent-config/${mode}/reset`, {
    method: "POST",
    query: {},
  });
  if (!res.ok) {
    throw new Error("重置配置失败");
  }
}

export async function resetAgentConfigToDefault(
  mode: AgentMode,
  sessionId?: string,
  workspaceId?: string,
): Promise<void> {
  const res = await apiFetch(`/api/agent-config/${mode}/reset`, {
    method: "POST",
    query: {
      session_id: sessionId,
      workspace_id: workspaceId,
    },
  });
  if (!res.ok) {
    throw new Error("重置配置失败");
  }
}

/**
 * 验证配置有效性
 */
export async function validateConfig(mode: AgentMode): Promise<{
  valid: boolean;
  errors: string[];
}> {
  const res = await apiFetch(`/api/agent-config/${mode}/validate`, {
    method: "POST",
  });
  if (!res.ok) {
    throw new Error("验证配置失败");
  }
  return res.json();
}

/**
 * 获取任务模型路由配置
 */
export async function getTaskModels(): Promise<{
  task_models: Record<string, string>;
  available_models: string[];
}> {
  const res = await apiFetch("/api/agent-config/task-models");
  if (!res.ok) {
    throw new Error("获取任务模型路由失败");
  }
  return res.json();
}

/**
 * 更新任务模型路由配置
 */
export async function updateTaskModels(
  taskModels: Record<string, string>
): Promise<void> {
  const res = await apiFetch("/api/agent-config/task-models", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task_models: taskModels }),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || "保存任务模型路由失败");
  }
}

// ==================== 管理员 API ====================

/**
 * 获取系统默认配置（仅管理员）
 */
export async function getSystemConfig(
  mode: AgentMode
): Promise<SystemConfigResponse> {
  const res = await apiFetch(`/api/agent-config/admin/system/${mode}`);
  if (!res.ok) {
    throw new Error("获取系统配置失败");
  }
  return res.json();
}

/**
 * 更新系统默认提示词（仅管理员）
 */
export async function updateSystemPrompt(
  mode: AgentMode,
  content: string,
  strategy: MergeStrategy = "replace"
): Promise<void> {
  const res = await apiFetch(`/api/agent-config/admin/system/${mode}/prompt`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content, strategy }),
  });
  if (!res.ok) {
    throw new Error("更新系统提示词失败");
  }
}
