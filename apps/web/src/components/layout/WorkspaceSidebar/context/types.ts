/**
 * * WorkspaceSidebar Context Types
 *
 * 定义 Sidebar 所需的状态、动作和元数据接口
 */
import type { TaskState } from "@/hooks/useMultiTaskEventStream";
import type { WorkspaceFile } from "@/types/task";
import type {
  SessionStatusInfo,
  TaskWorkspaceSummary,
} from "@/pages/DataAnalysisPage/types";
import type { SubAgentTask } from "../SubAgentTaskCard";

export type SidebarTab =
  | "monitor"
  | "subagents"
  | "artifacts"
  | "search"
  | "database"
  | "settings"
  | "channel"
  | "auto-tasks"
  | "env"
  | "terminal"
  | "file-changes";

// Context 状态接口
export interface SidebarState {
  /** 侧边栏是否打开 */
  isOpen: boolean;
  /** 当前宽度 */
  width: number;
  /** 所有任务列表（原有代码执行任务）- 将逐步迁移到 subAgentTasks */
  taskList: TaskState[];
  /** Sub Agent 子任务列表（新增） */
  subAgentTasks?: SubAgentTask[];
  /** 当前选中的任务 */
  selectedTask?: TaskState;
  /** 当前选中的 Sub Agent 任务 ID */
  selectedSubAgentTaskId?: string;
  /** 当前选中的任务 ID */
  selectedTaskId?: string;
  /** 是否正在加载历史 */
  isLoadingHistory: boolean;
  /** 当前活动的 Tab */
  activeTab: SidebarTab;
  /** 当前任务工作区摘要 */
  workspaceSummary?: TaskWorkspaceSummary;
  /** 当前会话状态摘要 */
  sessionStatus?: SessionStatusInfo | null;
  /** 当前会话是否为自动研究模式 */
  /** 研究会话状态 */
  /** 是否正在加载研究状态 */
  /** 工作区文件列表 */
  workspaceFiles: WorkspaceFile[];
  /** 会话 ID */
  sessionId?: string;
  /** 会话标题 */
  sessionTitle?: string | null;
  /** 当前会话消息数 */
  messageCount?: number;
  /** 执行记录总数 */
  executionRecordCount?: number;
  /** 最近一次运行态 */
  lastRuntimeState?: string | null;
  /** 当前会话是否仍在运行 */
  isSessionRunning?: boolean;
  /** isSessionRunning 变为 true 的时间戳（ms），用于计算已运行时长 */
  runningStartedAt?: number;
  /** 当前是否正在压缩对话 */
  isCompactingConversation: boolean;
  /** 当前是否正在重置代码运行态 */
  isRestartingRuntime: boolean;
  /** 是否正在导出 */
  isExporting: boolean;
  /** 当前选中的工具 (用于工具预览) */
  selectedTool?: {
    toolName: string;
    toolParams?: Record<string, unknown>;
    toolOutput?: string;
    taskId?: string;
  } | null;
}

// Context Actions 接口
export interface SidebarActions {
  /** 关闭侧边栏 */
  onClose: () => void;
  /** 打开侧边栏 */
  onOpen: () => void;
  /** 选择任务 */
  onSelectTask: (taskId: string) => void;
  /** 宽度变化回调 */
  onWidthChange?: (width: number) => void;
  /** 删除文件 */
  onDeleteFile?: (filename: string) => Promise<boolean>;
  /** 删除文件夹 */
  onDeleteFolder?: (folderPath: string) => Promise<boolean>;
  /** 读取文件内容 */
  onReadFileContent?: (filename: string) => Promise<string | null>;
  /** 刷新当前工作区文件列表 */
  onRefreshWorkspaceFiles?: () => Promise<void>;
  /** 移动/重命名文件 */
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  /** 设置活动 Tab */
  setActiveTab: (tab: SidebarTab) => void;
  /** 设置导出状态 */
  setIsExporting: (value: boolean) => void;
  /** 导出工作区 */
  exportWorkspace: () => Promise<void>;
  /** 导出单个 Markdown 文件 */
  exportWorkspaceFile: (
    filename: string,
    format: "md" | "docx" | "pdf",
  ) => Promise<void>;
  /** 设置当前选中的工具 */
  setSelectedTool: (
    tool: {
      toolName: string;
      toolParams?: Record<string, unknown>;
      toolOutput?: string;
      taskId?: string;
    } | null,
  ) => void;
  /** 查看执行记录 */
  onViewExecutionRecords?: () => Promise<void> | void;
  /** 压缩当前对话 */
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
  /** 重建当前运行态 */
  onRestartRuntime?: () => Promise<void> | void;
  /** 打开数据库连接管理 */
  onManageDatabaseConnections?: () => void;
  /** 新建数据库连接 */
  onCreateDatabaseConnection?: () => void;
  /** 打开知识库管理 */
  onOpenKnowledgeBaseDialog?: () => void;
  /** 打开知识图谱管理 */
  onOpenKnowledgeGraphDialog?: () => void;
  /** 打开工作区设置 */
  onOpenWorkspaceSettings?: () => void;
}

// Context Meta 接口
export interface SidebarMeta {
  /** 滚动容器引用 */
  scrollRef: React.RefObject<HTMLDivElement | null>;
}

// 完整的 Context Value 接口
export interface SidebarContextValue {
  state: SidebarState;
  actions: SidebarActions;
  meta: SidebarMeta;
}
// 研究会话状态
export interface ResearchSessionState {
  session_id: string;
  topic: string;
  description?: string;
  current_phase: string;
  phases: ResearchPhase[];
  checkpoints: ResearchCheckpoint[];
  status: "running" | "paused" | "completed" | "failed";
  created_at: string;
  updated_at: string;
}

export interface ResearchPhase {
  id: string;
  name: string;
  description: string;
  status: "pending" | "in_progress" | "completed" | "needs_approval" | "failed";
  order: number;
  started_at?: string;
  completed_at?: string;
}

export interface ResearchCheckpoint {
  id: string;
  phase_id: string;
  name: string;
  description: string;
  status: "pending" | "completed" | "needs_approval" | "rework";
  requires_approval: boolean;
  deliverables?: string[];
  auto_check_results?: {
    passed: boolean;
    message?: string;
  };
  started_at?: string;
  completed_at?: string;
}
