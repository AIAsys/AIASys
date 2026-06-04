/**
 * Agent 配置类型定义
 */

export type AgentMode = "analysis";
export type MergeStrategy = "replace" | "append" | "merge";

/**
 * 工具覆盖配置
 */
export interface ToolOverride {
  name: string;
  enabled?: boolean;
  description?: string;
  timeout?: number;
}

/**
 * 工具配置
 */
export interface ToolsConfig {
  selection_mode: "inherit" | "explicit";
  enabled_tools: string[];
  disabled_tools: string[];
  extra_tools: string[];
  tool_overrides: Record<string, ToolOverride>;
  tool_strategy: "auto" | "search" | "deferred" | "passthrough";
}

/**
 * 提示词配置
 */
export interface PromptConfig {
  content: string;
  strategy: MergeStrategy;
}

/**
 * 用户配置响应
 */
export interface UserConfigResponse {
  mode: AgentMode;
  enabled: boolean;
  prompt_content?: string;
  enabled_tools: string[];
  disabled_tools: string[];
  tool_strategy: "auto" | "search" | "deferred" | "passthrough";
  reserved_context_size?: number;
  compaction_trigger_ratio?: number;
}

/**
 * 当前会话编辑配置响应
 */
export interface EditableConfigResponse {
  mode: AgentMode;
  enabled: boolean;
  prompt_content?: string;
  enabled_tools: string[];
  disabled_tools: string[];
  tool_strategy: "auto" | "search" | "deferred" | "passthrough";
  reserved_context_size: number;
  compaction_trigger_ratio: number;
  source: "system_default" | "user_default" | "workspace_override" | "session_override" | string;
  runtime_source: "system_default" | "user_default" | "workspace_override" | "session_override" | string;
  has_local_override: boolean;
  has_local_runtime_override: boolean;
}

/**
 * 合并后的配置响应
 */
export interface MergedConfigResponse {
  mode: AgentMode;
  is_customized: boolean;
  prompt_source: string;
  enabled_tools: string[];
  disabled_tools: string[];
  tool_strategy: "auto" | "search" | "deferred" | "passthrough";
  system_prompt_preview: string;
  reserved_context_size: number;
  compaction_trigger_ratio: number;
  runtime_source: string;
}

/**
 * 系统默认配置响应（管理员）
 */
export interface SystemConfigResponse {
  mode: AgentMode;
  config_path: string;
  config: {
    agent: {
      name: string;
      model: string;
      tools: string[];
      exclude_tools?: string[];
      system_prompt_path: string;
    };
  };
  prompt_content: string;
}
