import type { SessionRuntimeSummary } from "@/types/workspace";
import type { ResolvedMemoryPreview } from "@/types/memory";
import type { TaskExecutionPolicySummary } from "@/types/autoTask";

export type ChatSegment = {
  type:
    | "text"
    | "thought"
    | "tool_call"
    | "tool_output"
    | "think"
    | "monitor"
    | "turn";
  content: string;
  toolName?: string;
  toolCallId?: string;
  toolParams?: string;
  isComplete?: boolean;
  isError?: boolean;
  /** Turn 标记专用字段 */
  turnN?: number;
  /** Monitor 专用字段 */
  monitorId?: string;
  monitorCommand?: string;
  monitorStatus?: string;
  monitorExitCode?: number | null;
};

export type WorkerRecord = {
  name: string;
  status: "running" | "completed" | "failed";
  durationMs?: number;
};

/** 场景ID - 用户可见的场景标识 */
export type WorkspaceKind = "task" | "claw";

export interface WorkspaceRuntimeBindingSummary {
  sandbox_mode?: string | null;
  env_id?: string | null;
  env_vars?: Record<string, string> | null;
}

// 聊天消息类型 - 统一为纯消息流
export type MessageChatItem = {
  type: "message";
  id: string;
  sender: "user" | "ai" | "tool" | "system";
  role?: "user" | "assistant" | "system" | "tool";
  content?: string;
  segments?: ChatSegment[]; // 分段内容 (Thought vs Answer)
  timestamp: Date;
  isStreaming?: boolean;
  isStopped?: boolean; // 用户手动终止标志
  taskId?: string; // 跟踪关联的监控任务（用于打开执行空间）
  workerRecords?: WorkerRecord[];
  attachments?: string[];
};

export type AskUserChatItem = {
  type: "ask_user";
  id: string; // request_id
  request: import("@/types/askUser").AskUserRequest;
  status: "pending" | "approved" | "rejected" | "timeout";
  timestamp: Date;
};

export type CapabilityConfirmationChatItem = {
  type: "capability_confirmation";
  id: string; // tool_call_id
  tool_name: string;
  arguments: Record<string, unknown>;
  prompt: string;
  session_id: string;
  status: "pending" | "approved" | "rejected" | "timeout";
  subagent_name?: string;
  agent_id?: string;
  pattern_key?: string;
  timestamp: Date;
};

export type ChatItem = MessageChatItem | AskUserChatItem | CapabilityConfirmationChatItem;

export type SessionHistoryContentItem = {
  type: string;
  text?: string;
  think?: string;
  image_url?: {
    url?: string;
    detail?: string | null;
  };
  source_path?: string;
};

export type SessionHistoryMessage = {
  id?: string;
  role: "user" | "assistant" | "tool" | "system";
  content: SessionHistoryContentItem[] | string;
  display_content?: SessionHistoryContentItem[] | string;
  reasoning_content?: string | null;
  rewritten_from?: string | null;
  timestamp?: string | null;
  tool_calls?: Array<{
    id: string;
    type: "function";
    function?: {
      name?: string;
      arguments?: string;
    };
  }>;
  tool_call_id?: string;
};

export type SessionConversationArchiveBatch = {
  batch_id: string;
  type: "context_cleared" | string;
  archived_at?: string | null;
  label?: string | null;
  description?: string | null;
  messages: SessionHistoryMessage[];
};

export type SessionRecordsDialogTab = "conversation" | "execution";

// 后端文件信息
export type BackendFileInfo = {
  filename: string;
  file_path: string;
  size: number;
  created_at: number;
};

// 后端会话信息
export type BackendSessionInfo = {
  session_id: string;
  file_count: number;
  updated_at: number;
};

// ==================== 新命名体系：对话（Conversation）====================

/** 对话类型 - 替代旧的 SessionRole */
export type ConversationType = "chat" | "orchestrator" | "worker" | "hosting_agent";

/**
 * 对话（Conversation）- 替代 HistorySession
 *
 * 命名变更对照：
 * - HistorySession -> Conversation
 * - session_role -> conversation_type ("chat" | "orchestrator" | "worker")
 * - task_id -> assignment_id
 * - task_title -> assignment_title
 */
export interface Conversation {
  // 基础字段
  session_id: string;
  title: string;
  updated_at: string;
  message_count: number;
  workspace_file_count: number;

  // 运行态实现字段
  sandbox_mode?: string;
  env_id?: string;

  // 新命名体系字段
  conversation_type?: ConversationType;
  project_id?: string | null;
  team_id?: string | null;
  bound_lead_session_id?: string | null;
  assignment_id?: string | null; // 作业者会话的作业 ID（原 task_id）
  assignment_title?: string | null; // 作业者会话的作业标题（原 task_title）

  // 来源标记
  source?: "auto_task" | "manual" | "automation" | "hosting" | null;
  auto_task_id?: string | null;
  automation_continuation_id?: string | null;
  automation_continuation_target_kind?: string | null;
  bound_host_session_id?: string | null;
}

/**
 * 项目作用域对话摘要 - 替代 ProjectScopedSessionSummary
 * 用于项目空间中的编排者和作业者会话
 */
export interface ProjectScopedConversation extends Conversation {
  conversation_type: "orchestrator" | "worker";
  project_id: string;
}

export interface WorkspaceConversationSummary {
  workspace_id: string;
  conversation_id: string;
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  workspace_kind?: WorkspaceKind;
  execution_policy?: TaskExecutionPolicySummary | null;
  message_count: number;
  status: string;
  branched_from_conversation_id?: string | null;
  last_execution_status?: string | null;
  last_execution_record_id?: string | null;
  execution_record_count?: number;
  source?: "auto_task" | "manual" | "automation" | "hosting" | null;
  conversation_type?: ConversationType;
  bound_host_session_id?: string | null;
  auto_task_id?: string | null;
  automation_continuation_id?: string | null;
  automation_continuation_target_kind?: string | null;
}

export interface TaskWorkspaceSummary {
  workspace_id: string;
  title: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  workspace_kind?: "task" | "claw";
  execution_policy?: TaskExecutionPolicySummary | null;
  runtime_binding?: WorkspaceRuntimeBindingSummary | null;
  status: string;
  current_conversation_id?: string | null;
  conversation_count: number;
  current_conversation?: WorkspaceConversationSummary | null;
  conversations?: WorkspaceConversationSummary[];
  warnings?: string[];
}

// ==================== 会话与工作区 API 响应 ====================

export type ListProjectScopedSessionsResponse = {
  sessions: ProjectScopedConversation[];
  total: number;
};

export type SessionStatusInfo = {
  session_id: string;
  status?: string;
  message_count?: number;
  code_timeout?: number | null;
  title?: string;
  is_empty?: boolean;
  can_edit_mcp?: boolean;
  has_execution_journal?: boolean;
  execution_record_count?: number;
  last_execution_status?: string | null;
  last_execution_record_id?: string | null;
  recovery_policy?: string | null;
  idempotency_policy?: string | null;
  requires_confirmation_for_replay?: boolean;
  last_runtime_state?: string | null;
  rebuild_status?: "completed" | "partial_failed" | "blocked" | null;
  last_replay_run_id?: string | null;
  last_replayed_sequences?: number[];
  last_remaining_sequences?: number[];
  last_failed_sequence?: number | null;
  can_change_recovery_policy?: boolean;
  recovery_policy_lock_reason?: string | null;
  can_edit_agent_config_now?: boolean;
  pending_agent_config_version?: string | null;
  applied_agent_config_version?: string | null;
  current_agent_config_version?: string | null;
  pending_capability_snapshot_version?: string | null;
  applied_capability_snapshot_version?: string | null;
  current_capability_snapshot_version?: string | null;
  current_memory_snapshot_version?: string | null;
  current_memory_snapshot_hash?: string | null;
  applied_memory_snapshot_version?: string | null;
  applied_memory_snapshot_hash?: string | null;
  pending_memory_snapshot_version?: string | null;
  pending_memory_snapshot_hash?: string | null;
  memory_effect?: "next_run_only" | string | null;
  memory_snapshot_preview?: ResolvedMemoryPreview | null;
  agent_config_effect?: "next_run_only" | string | null;
  config_sync_state?: "aligned" | "pending" | string | null;
  rebuild_required?: boolean;
  rebuild_required_reasons?: string[];
  config_state_updated_at?: string | null;
  workspace_capability_summary?: {
    skill_count?: number;
    skill_names?: string[];
    mcp_server_count?: number;
    enabled_mcp_server_count?: number;
    enabled_mcp_server_names?: string[];
    mcp_config_version?: number;
  } | null;
  collaboration_node_summary?: {
    total_count?: number;
    running_count?: number;
    completed_count?: number;
    abnormal_count?: number;
    latest_updated_at?: string | null;
  } | null;
  runtime_summary?: SessionRuntimeSummary | null;
  enabled_expert_role_ids?: string[] | null;
  expert_role_tool_ids?: Record<string, string[]> | null;
  execution_policy?: TaskExecutionPolicySummary | null;
  tasks?: Array<{
    id: string;
    content: string;
    status: "pending" | "in_progress" | "completed" | "cancelled";
    dependencies?: string[];
    created_at?: string;
    updated_at?: string;
    completed_at?: string | null;
  }>;
  task_counts?: {
    pending?: number;
    in_progress?: number;
    completed?: number;
    cancelled?: number;
  };
  plan_state?: {
    mode?: "active" | "inactive";
    approval_status?: "draft" | "pending_approval" | "approved" | "rejected";
    current_plan_file?: string | null;
    pre_plan_permission_mode?: string | null;
    updated_at?: string | null;
  } | null;
};

export type SessionExecutionRecord = {
  record_id: string;
  session_id: string;
  sequence: number;
  status: string;
  language: string;
  code: string;
  started_at: string;
  finished_at: string;
  stdout_ref?: string | null;
  stderr_ref?: string | null;
  artifact_refs?: string[];
  error?: string | null;
  runtime?: {
    sandbox_mode?: string | null;
    env_id?: string | null;
  };
  result_preview?: {
    type?: string;
    text?: string;
  };
  replay_risk?: {
    level?: "low" | "medium" | "high";
    tags?: string[];
    reasons?: string[];
    has_side_effect_risk?: boolean;
  };
};

export type SessionExecutionMaintenanceMarker = {
  marker_id: string;
  type: "context_cleared" | string;
  occurred_at: string;
  label: string;
  description?: string | null;
};

// Worker Debug View 类型
export type WorkerDebugViewState = {
  workerSessionId: string;
  taskTitle: string;
  taskId: string;
} | null;

// ============ Team with Workers Types (T20c) ============

export type ResearchTeamSummary = {
  team_id: string;
  name: string;
  role: string;
  status: "idle" | "dispatching" | "running" | "blocked" | "completed";
  summary: string;
  worker_count: number;
  created_at: string;
  updated_at: string;
};

export type ListResearchTeamsWithWorkersResponse = {
  teams: ResearchTeamSummary[];
  total: number;
};
