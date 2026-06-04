import React from "react";
import type { AskUserRequest } from "@/types/askUser";
import type { AgentStreamState, StreamCallbacks } from "@/hooks/useAgentStream";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { TaskState } from "@/hooks/useMultiTaskEventStream";
import type { WorkspaceFile } from "@/types/task";
import type { ChatItem, Conversation } from "../../types";

export interface UseCodeExecutorProps {
  apiBaseUrl: string;
  initialSessionId?: string | null;
  workspaceId?: string | null;
  workspaceIdRef?: { readonly current: string | null | undefined };
  onAskUserRequest?: (request: AskUserRequest, sessionId: string) => void;
  /** 选中的模型ID，'system' 表示使用系统默认配置 */
  selectedModelId?: string;
  /** 是否启用 thinking 模式 */
  thinkingEnabled?: boolean;
  /** thinking 强度 */
  thinkingEffort?: string;
}

export interface SessionSelectionOptions {
  /** silent 选择不更新 analysis URL（用于 hidden session） */
  silent?: boolean;
}

export interface SessionDeletionOptions {
  /** 调用方已经先完成前台切换，本次删除不再触发 active-session hidden draft 兜底 */
  suppressActiveFallback?: boolean;
}

export interface WorkspaceRefreshOptions {
  /** 用户手动刷新或文件变更后跳过短缓存，直接重新读取后端列表 */
  force?: boolean;
}

export interface UseCodeExecutorReturn {
  isRightSidebarOpen: boolean;
  setIsRightSidebarOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
  userClosedSidebar: boolean;
  setUserClosedSidebar: (closed: boolean) => void;
  sidebarWidth: number;
  setSidebarWidth: (width: number) => void;
  sidebarMode: "expanded" | "collapsed";
  setSidebarMode: (
    mode:
      | "expanded"
      | "collapsed"
      | ((prev: "expanded" | "collapsed") => "expanded" | "collapsed"),
  ) => void;
  showImportModal: boolean;
  setShowImportModal: (show: boolean) => void;
  messagesEndRef: React.RefObject<HTMLDivElement | null>;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  toasts: Array<{ id: string; message: string; type: "success" | "error" }>;
  chatItems: ChatItem[];
  inputValue: string;
  setInputValue: (value: string) => void;
  isPrewarming: boolean;
  // Execution Returns
  agentState: AgentStreamState;
  runAgentStream: (
    input: string,
    sessionId: string,
    callbacks?: StreamCallbacks,
    modelId?: string,
    attachments?: string[],
    workspaceId?: string | null,
    thinkingEnabled?: boolean,
    thinkingEffort?: string,
  ) => Promise<void>;
  resetAgentStream: () => void;
  taskList: TaskState[];
  currentTaskList: TaskState[];
  selectedTask: TaskState | undefined;
  selectedTaskId: string | undefined;
  selectTask: (taskId: string) => void;
  sessionId: string;
  handleNewSession: () => Promise<string>;
  prepareNewSession: () => Promise<string>;
  activatePreparedSession: (sessionId: string) => Promise<string>;
  refreshWorkspaceForSession: (
    sessionId: string,
    options?: WorkspaceRefreshOptions,
  ) => Promise<void>;
  refreshExecutionHistoryCurrentSession: () => Promise<void>;
  clearCurrentConversationView: () => Promise<void>;
  handleSelectSession: (
    sid: string,
    options?: SessionSelectionOptions,
  ) => Promise<void>;
  handleDeleteSession: (
    sid: string,
    options?: SessionDeletionOptions,
  ) => Promise<void>;
  /** 仅清理前端 per-session 缓存（chat/upload/multi-task），不调后端删除 API */
  removeSessionFrontendState: (sid: string) => void;
  uploadedFiles: UploadedFile[];
  removeFile: (filename: string) => void;
  handleUploadFiles: (files: File[] | FileList) => Promise<void>;
  handleFileChange: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  handleAddFileClick: () => void;
  conversations: Conversation[]; // 替代 historySessions
  updateSessionTitle: (
    sessionId: string,
    title: string,
  ) => Promise<void>;
  handleImportSuccess: () => Promise<void>;
  handleViewExecutionSpace: () => void;
  handleSubmit: (
    overridePrompt?: string,
    options?: { skipUserEcho?: boolean; attachmentPaths?: string[] },
  ) => Promise<void>;
  rewriteUserMessage: (
    messageId: string,
    content: string,
    originalContent?: string,
  ) => Promise<void>;
  handleKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  handleWorkerClick: (workerName: string) => void;
  handleStop: () => void;
  isRunning: boolean;
  tokenUsageRevision: number;
  hasChatContent: boolean;
  currentHasAnyRunning: boolean;
  executionSummary: unknown;
  isLoadingHistory: boolean;
  isRestoringSession: boolean;
  workspaceFiles: WorkspaceFile[];
  updateWorkspaceFiles: (files: WorkspaceFile[]) => void;
  deleteWorkspaceFile: (filename: string) => Promise<boolean>;
  deleteWorkspaceFolder: (folderPath: string) => Promise<boolean>;
  moveFile: (source: string, target: string) => Promise<boolean>;
  readWorkspaceFileContent: (path: string) => Promise<string | null>;
  isUploading: boolean;
  /** 当前所有正在运行的 session ID 集合 */
  runningSessionIds: Set<string>;
  /** 更新指定 session 的聊天内容 */
  updateSessionChatItems: (
    sessionId: string,
    updater: (prev: ChatItem[]) => ChatItem[],
  ) => void;
}
