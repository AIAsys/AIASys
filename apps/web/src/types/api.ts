/**
 * API 请求/响应类型定义
 * 与后端 API 保持一致
 */

// ==================== SSE 事件类型 ====================

export interface SSEEvent {
  type: string;
}

/** 内容事件 (SDK 格式) - 对应 SDK 的 content 数组项 */
export interface ContentEvent extends SSEEvent {
  type: "content";
  content_type: "text" | "think";
  text?: string; // 当 content_type === "text"
  think?: string; // 当 content_type === "think"
}

/** Host Agent 工具调用 */
export interface ToolCallEvent extends SSEEvent {
  type: "tool_call";
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
}

/** Host Agent 工具结果 (SDK 格式) */
export interface ToolResultEvent extends SSEEvent {
  type: "tool_result";
  tool_call_id: string;
  tool_name?: string; // 工具名称（可选，后端不一定提供）
  content: string; // SDK 使用 content 而非 output
  is_error: boolean;
}

/** SubAgent 内容事件 */
export interface SubagentContentEvent extends SSEEvent {
  type: "subagent_content";
  content_type: "text" | "think";
  text?: string;
  think?: string;
  task_tool_call_id: string;
}

/** SubAgent 包装事件（包含 payload） */
export interface SubagentEvent extends SSEEvent {
  type: "subagent_event";
  task_tool_call_id: string;
  subagent_name?: string;
  payload: {
    type:
      | "subagent_content"
      | "subagent_tool_call"
      | "subagent_tool_result"
      | "subagent_step_begin";
    content_type?: "text" | "think";
    text?: string;
    think?: string;
    tool_call_id?: string;
    tool_name?: string;
    arguments?: Record<string, unknown>;
    content?: string;
    is_error?: boolean;
    step_n?: number;
    task_tool_call_id?: string;
  };
}

/** SubAgent 工具调用 */
export interface SubagentToolCallEvent extends SSEEvent {
  type: "subagent_tool_call";
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  task_tool_call_id: string;
}

/** SubAgent 工具结果 */
export interface SubagentToolResultEvent extends SSEEvent {
  type: "subagent_tool_result";
  tool_call_id: string;
  tool_name?: string; // 加入 tool_name 方便过滤和渲染
  content: string;
  is_error: boolean;
  task_tool_call_id: string;
}

/** SubAgent 步骤开始 */
export interface SubagentStepEvent extends SSEEvent {
  type: "subagent_step_begin";
  step_n: number;
  task_tool_call_id: string;
}

/** Token 使用统计 */
export interface TokenUsageEvent extends SSEEvent {
  type: "token_usage";
  input: number;
  output: number;
  /** 当前上下文占用 token 数（后端推送，前端可直接刷新右栏） */
  context_tokens?: number;
}

/** 文件变化事件 */
export interface FileChangesEvent extends SSEEvent {
  type: "file_changes";
  changes: Array<{
    path: string;
    type: "added" | "modified" | "deleted";
    size?: number;
  }>;
}

/** 状态事件 */
export interface StatusEvent extends SSEEvent {
  type: "status";
  message: string;
}

/** 错误事件 */
export interface ErrorEvent extends SSEEvent {
  type: "error";
  message: string;
}

/** Turn 开始事件 */
export interface TurnBeginEvent extends SSEEvent {
  type: "turn_begin";
  turn_n: number;
}

export interface ThinkEvent extends SSEEvent {
  type: "think";
  content: string;
}

/** Monitor 后台命令输出事件 */
export interface MonitorOutputEvent extends SSEEvent {
  type: "monitor.output";
  monitor_id: string;
  command: string;
  status: string;
  exit_code: number | null;
  output: string;
  output_offset: number;
  created_at: number;
  completed_at: number | null;
}

export interface BudgetLimitedEvent extends SSEEvent {
  type: "budget_limited";
  text: string;
}

export interface BudgetUpdatedEvent extends SSEEvent {
  type: "budget_updated";
  token_budget: number | null;
  tokens_used: number;
  time_budget_seconds?: number | null;
  time_used_seconds?: number;
  status: "active" | "budget_limited";
}

export interface AskUserRequestEvent extends SSEEvent {
  type: "ask_user_request";
  request: import("@/types/askUser").AskUserRequest;
}

/** 上下文压缩事件 */
export interface CompactionEvent extends SSEEvent {
  type: "compaction";
  phase: "begin" | "done";
  tokens_before?: number;
  tokens_after?: number;
  saved_tokens?: number;
  summary_tokens?: number;
}

/** 能力确认请求（运行时审批） */
export interface CapabilityConfirmationEvent extends SSEEvent {
  type: "capability_confirmation";
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  content: string;
}

/** 子 Agent 能力确认请求 */
export interface SubagentCapabilityConfirmationEvent extends SSEEvent {
  type: "subagent_capability_confirmation";
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  content: string;
  task_tool_call_id: string;
  agent_id?: string;
  subagent_name?: string;
}

/** 系统警告事件（Auto-Nudge, Loop Guard 等） */
export interface SystemWarningEvent extends SSEEvent {
  type: "system_warning";
  message: string;
}

/** 心跳事件（保活检测，后端每 15 秒发送一次） */
export interface HeartbeatEvent extends SSEEvent {
  type: "heartbeat";
}

export type AgentEvent =
  | ContentEvent
  | ToolCallEvent
  | ToolResultEvent
  | SubagentEvent
  | SubagentContentEvent
  | SubagentToolCallEvent
  | SubagentToolResultEvent
  | SubagentStepEvent
  | TurnBeginEvent
  | TokenUsageEvent
  | FileChangesEvent
  | StatusEvent
  | ErrorEvent
  | MonitorOutputEvent
  | BudgetLimitedEvent
  | BudgetUpdatedEvent
  | AskUserRequestEvent
  | CapabilityConfirmationEvent
  | SubagentCapabilityConfirmationEvent
  | CompactionEvent
  | SystemWarningEvent
  | HeartbeatEvent;

// ==================== Agent 执行 ====================

export interface AgentExecuteRequest {
  prompt: string;
  user_id?: string;
  workspace_id?: string;
  session_id: string;
  model?: string;
  model_id?: string;
  /** 当前轮附带的工作区文件 */
  attachments?: string[];
  /** 当前轮引用的外部资源 */
  references?: string[];
  /** 是否启用 reasoning / thinking 模式 */
  thinking_enabled?: boolean;
  /** thinking 强度：low / medium / high */
  thinking_effort?: string;
}

// ==================== Skills ====================

/** 会话中的 Skill（包含启用状态） */
export interface SessionSkill {
  name: string;
  display_name?: string;
  description: string;
  enabled: boolean;
  installed_at?: string;
  source?: string; // "installed" | "custom"
}

/** 市场中的 Skill */
export interface MarketSkill {
  name: string;
  display_name?: string;
  description: string;
  installed: boolean;
  globally_enabled?: boolean;
  source?: string; // "builtin" | "store" | "workspace"
  versions?: string[];
  env_fields?: Array<{
    name: string;
    required?: boolean;
    description?: string;
    default_value?: string | null;
  }>;
  hash_status?: string; // "synced" | "modified" | "outdated" | "custom" | "unknown"
  version?: string | null;
}

/** Skill 仓库中的 Skill */
export interface StoreSkill {
  name: string;
  display_name: string;
  description: string;
  source: string;
  entry_relative_path: string;
  versions: string[];
  globally_enabled?: boolean;
  env_fields?: Array<{
    name: string;
    required?: boolean;
    description?: string;
    default_value?: string | null;
  }>;
}

/** Skill 仓库 Skill 列表响应 */
export interface StoreSkillsListResponse {
  skills: StoreSkill[];
  total: number;
}

export interface WorkspaceSkillPackage {
  name: string;
  display_name: string;
  description: string;
  source: string;
  entry_relative_path: string;
  hash_status: string;
  version: string | null;
}

export interface WorkspaceSkillsListResponse {
  workspace_id: string;
  skills: WorkspaceSkillPackage[];
  total: number;
  workspace_skill_dir: string;
  container_mount_path: string;
}

export interface SkillInstallRequest {
  skill_name: string;
  force?: boolean;
}

export interface SkillInstallResponse {
  success: boolean;
  skill_name: string;
  message: string;
}

export interface SkillEntryResponse {
  name: string;
  display_name: string;
  description: string;
  entry_relative_path: string;
  content: string;
  env_fields?: Array<{
    name: string;
    required?: boolean;
    description?: string;
    default_value?: string | null;
  }>;
}

export interface SkillReadmeResponse {
  content: string;
  found: boolean;
}

export interface SkillEnableRequest {
  skill_name: string;
  version?: string | null;
  force?: boolean;
}

export interface SkillDisableRequest {
  skill_name: string;
}

export interface SkillEnableResponse {
  success: boolean;
  skill_name: string;
  enabled: boolean;
  message: string;
}

// ==================== 文件 ====================

export interface FileInfo {
  name: string;
  size: number;
  modified: number;
  absolute_path?: string | null;
  resource_type?: "knowledge" | "database" | "graph" | string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
}

export interface FileListResponse {
  files: FileInfo[];
  user_id: string;
  session_id: string;
  directory?: string;
  recursive?: boolean;
  limit?: number;
  offset?: number;
  returned?: number;
  has_more?: boolean;
  next_offset?: number | null;
  total?: number | null;
}

export interface FileUploadResponse {
  success: boolean;
  filename: string;
  path: string;
  size: number;
  uploaded_by: string;
}

export interface FileCreateResponse {
  success: boolean;
  filename: string;
  path: string;
  size: number;
  overwritten: boolean;
  created_by: string;
  meta?: Record<string, unknown> | null;
}

// ==================== 执行历史 ====================

export interface ExecutionEvent {
  event_id: string;
  timestamp: string;
  agent: "host" | "subagent";
  event_type?: string;
  tool_name?: string;
  tool_call_id?: string;
  task_tool_call_id?: string;
  subagent_name?: string;
  content?: string;
  step_n?: number;
  [key: string]: unknown;
}

export interface ExecutionFlowResponse {
  user_id: string;
  session_id: string;
  events: ExecutionEvent[];
  task_count: number;
  task_tool_call_ids: string[];
  count: number;
}

export interface TaskSummary {
  task_tool_call_id: string;
  subagent_name?: string;
  event_count: number;
}

export interface TasksListResponse {
  user_id: string;
  session_id: string;
  tasks: TaskSummary[];
  count: number;
}

// ==================== Session ====================

export interface SessionInfo {
  session_id: string;
  title: string;
  created_at: string;
  message_count: number;
  code_timeout?: number;
}

// ==================== 健康检查 ====================

export interface HealthResponse {
  status: string;
  app: string;
  version: string;
  auth_mode: string;
}
