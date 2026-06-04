/**
 * TaskEvent - 执行流面板使用的展示事件格式。
 *
 * AgentEvent 是后端流式响应的传输格式，TaskEvent 是前端任务面板的渲染格式。
 */
export interface TaskEvent {
  event: string;
  type?: string;
  agent_name?: string;
  agent_type?: string;
  agent_role?: "host" | "worker";
  worker_name?: string;
  tool_name?: string;
  content?: string;
  status?: string;
  tool_params?: string | Record<string, unknown>;
  source_agent?: string;
  content_type?: "think" | "text" | "log" | "code";
  is_final?: boolean;
  duration_ms?: number;
  files?: WorkspaceFile[];
  timestamp?: string;
  [key: string]: unknown;
}

export interface WorkspaceFile {
  name: string;
  size: number;
  mtime: string;
  absolute_path?: string | null;
  id?: string;
  isNew?: boolean;
  isModified?: boolean;
  resource_type?: "knowledge" | "database" | "graph" | string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
}

/** 单个任务的执行流展示状态 */
export interface SingleTaskState {
  taskId: string;
  label: string;
  events: TaskEvent[];
  isComplete: boolean;
  error?: string;
  startedAt: Date;
}

/** 多任务流状态 */
export interface MultiTaskStreamState {
  tasks: Map<string, SingleTaskState>;
  taskOrder: string[];
  selectedTaskId?: string;
  workspaceFiles: WorkspaceFile[];
}
