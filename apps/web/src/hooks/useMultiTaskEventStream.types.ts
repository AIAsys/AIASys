import type { ExecutionEvent } from "@/types/api";
import type { TaskEvent } from "@/types/task";

export interface TaskState {
  taskId: string;
  label: string;
  events: TaskEvent[];
  isComplete: boolean;
  startedAt: Date;
  error?: string;
}

export interface MultiTaskStreamState {
  tasks: Map<string, TaskState>;
  taskOrder: string[];
  selectedTaskId?: string;
}

export interface WorkspaceFile {
  name: string;
  size: number;
  mtime: string;
  resource_type?: "knowledge" | "database" | "graph" | string;
  schema_kind?: string;
  preview_kind?: string;
  renderer_hint?: string;
  meta?: Record<string, unknown>;
}

export interface NotebookHistoryItem {
  code?: string;
  stdout?: string;
  stderr?: string;
  success?: boolean;
  timestamp?: number;
}

/** Per-session 任务和文件数据 */
export interface PerSessionData {
  state: MultiTaskStreamState;
  files: WorkspaceFile[];
}

export interface UseMultiTaskEventStreamReturn {
  /** Task 列表 */
  taskList: TaskState[];
  /** 当前选中的 Task */
  selectedTask?: TaskState;
  /** 当前选中的 Task ID */
  selectedTaskId?: string;
  /** 是否有运行中的 Task */
  hasAnyRunning: boolean;
  /** 选择 Task */
  selectTask: (taskId: string) => void;
  /** 添加事件到 Task */
  addStreamEvents: (taskId: string, events: TaskEvent[], label?: string) => void;
  /** 添加事件到指定 session 的 Task */
  addStreamEventsForSession: (
    sessionId: string,
    taskId: string,
    events: TaskEvent[],
    label?: string,
  ) => void;
  /** 加载历史事件 */
  loadHistoricalEvents: (
    taskId: string,
    events: ExecutionEvent[],
    label?: string,
  ) => void;
  /** 停止监听 Task */
  stopTask: (taskId: string) => void;
  /** 停止所有监听 */
  stopAll: () => void;
  /** 重置状态（活跃 session） */
  reset: () => void;
  /** 重置指定 session */
  resetSession: (sessionId: string) => void;
  /** 完成 Host Task */
  completeHost: () => void;
  /** 完成所有 Tasks */
  completeAllTasks: () => void;
  /** 工作区文件 */
  workspaceFiles: WorkspaceFile[];
  /** 更新工作区文件 */
  updateWorkspaceFiles: (files: WorkspaceFile[]) => void;
  /** 更新指定 session 的工作区文件 */
  updateWorkspaceFilesForSession: (sessionId: string, files: WorkspaceFile[]) => void;
  /** 同步 Notebook 执行历史 */
  syncNotebookHistory: (taskId: string, sessionId: string) => Promise<void>;
  /** 切换 session */
  switchSession: (fromId: string, toId: string) => void;
  /** 初始化 session */
  initSession: (id: string) => void;
  /** 移除 session */
  removeSession: (id: string) => void;
  /** 设置活跃 session ID */
  setActiveSessionId: (id: string) => void;
}
