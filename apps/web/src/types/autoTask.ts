export interface TaskExecutionPolicySummary {
  mode: "chat_assist" | "auto_explore" | string;
  auto_continue: boolean;
  checkpoint_policy: string;
  human_gate_rules: string[];
  max_parallel_sessions: number;
  max_continuations: number;
  max_runtime_minutes: number;
}

// ── 自动任务 ──

export interface TriggerEventDocument {
  event_id: string;
  workspace_id: string;
  session_id?: string | null;
  source_type: "schedule" | "lifecycle" | "resource" | "human" | "runtime";
  event_name: string;
  payload: Record<string, unknown>;
  created_at: string;
  status: "pending" | "consumed" | "ignored" | "failed";
}

export interface WorkspaceTriggerEventListResponse {
  workspace_id: string;
  trigger_events_path: string;
  trigger_events: TriggerEventDocument[];
}

export interface WorkspaceAutoTask {
  task_id: string;
  workspace_id: string;
  user_id: string;
  prompt: string;
  trigger_type: "once" | "interval" | "cron" | "continuous";
  trigger_value: string;
  status: "active" | "paused" | "disabled" | "completed";
  title: string;
  created_at: string;
  updated_at: string;
  last_run_at?: string | null;
  next_run_at?: string | null;
  fired_count: number;
  consecutive_errors: number;
  last_error?: string | null;
  model?: string | null;
  model_id?: string | null;
  sandbox_mode?: string | null;
  attachments: string[];
  auto_enable_hosting: boolean;
  hosting_bootstrap_mode: "resume_only" | "launch_check";
  overlap_policy: "skip" | "queue" | "parallel";
  pending_run_count: number;
  bind_session_id?: string | null;
  session_strategy?: "bind_session" | "new_each_time";
  continuation_prompt?: string | null;
  max_continuations: number;
  // v0.4.0 新增
  task_category?: "scheduled" | "continuous";
  first_run_policy?: "immediate" | "next_scheduled";
  stop_on_consecutive_errors?: number;
  stop_on_signal?: boolean;
}

export type AutoTask = WorkspaceAutoTask;

export interface WorkspaceAutoTaskListResponse {
  workspace_id: string;
  tasks: WorkspaceAutoTask[];
}

export interface WorkspaceAutoTaskUpsertPayload {
  title: string;
  prompt: string;
  trigger_type: "once" | "interval" | "cron" | "continuous";
  trigger_value: string;
  status?: "active" | "paused" | "disabled" | "completed";
  model?: string | null;
  model_id?: string | null;
  sandbox_mode?: string | null;
  attachments?: string[];
  auto_enable_hosting?: boolean;
  hosting_bootstrap_mode?: "resume_only" | "launch_check";
  overlap_policy?: "skip" | "queue" | "parallel";
  bind_session_id?: string | null;
  session_strategy?: "bind_session" | "new_each_time";
  continuation_prompt?: string | null;
  max_continuations?: number;
  // v0.4.0 新增
  task_category?: "scheduled" | "continuous";
  first_run_policy?: "immediate" | "next_scheduled";
  stop_on_consecutive_errors?: number;
  stop_on_signal?: boolean;
}

export interface WorkspaceAutoTaskRunNowResponse {
  task_id: string;
  result: {
    workspace_id: string;
    task_id: string;
    executed?: boolean;
    execution_reason?: string;
  };
}

export interface GlobalAutoTask extends WorkspaceAutoTask {
  workspace_title?: string | null;
}

export interface GlobalAutoTaskCounts {
  total: number;
  active: number;
  paused: number;
  disabled: number;
  completed: number;
}

export interface GlobalAutoTaskWorkspaceSummary {
  workspace_id: string;
  workspace_title: string;
  counts: GlobalAutoTaskCounts;
}

export interface GlobalAutoTaskLatestRunSummary {
  task_id: string;
  title: string;
  workspace_id: string;
  workspace_title: string;
  last_run_at: string;
  status: WorkspaceAutoTask["status"];
}

export interface GlobalAutoTaskListResponse {
  user_id: string;
  tasks: GlobalAutoTask[];
}

export interface GlobalAutoTaskSummaryResponse {
  user_id: string;
  counts: GlobalAutoTaskCounts;
  workspaces: GlobalAutoTaskWorkspaceSummary[];
  latest_run?: GlobalAutoTaskLatestRunSummary | null;
}
