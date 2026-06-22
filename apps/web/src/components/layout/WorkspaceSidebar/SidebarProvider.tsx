/**
 * SidebarProvider - 状态管理解耦
 *
 * 将 Sidebar 的状态管理逻辑从 UI 中抽离
 */
import { useState, useRef, useCallback, useEffect, useMemo } from "react";
import { FileUploadToast, useFileUploadToast } from "@/components/file/FileUploadToast";
import { useSafeTimeout } from "@/hooks/useSafeTimeout";
import type { UploadedFile } from "@/hooks/useAgentFileUpload";
import type { TaskState } from "@/hooks/useMultiTaskEventStream";
import type { WorkspaceFile } from "@/types/task";
import type {
  SessionStatusInfo,
  TaskWorkspaceSummary,
} from "@/pages/WorkspacePage/types";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiFetch } from "@/lib/api/httpClient";
import { SidebarContext } from "./context";
import type { SidebarState, SidebarActions, SidebarMeta, SidebarTab } from "./context";

interface SidebarProviderProps {
  children: React.ReactNode;
  isOpen: boolean;
  taskList: TaskState[];
  selectedTask?: TaskState;
  selectedTaskId?: string;
  onSelectTask: (taskId: string) => void;
  onClose: () => void;
  onOpen: () => void;
  width?: number;
  onWidthChange?: (width: number) => void;
  sessionId?: string;
  sessionTitle?: string | null;
  messageCount?: number;
  executionRecordCount?: number;
  lastRuntimeState?: string | null;
  isSessionRunning?: boolean;
  isCompactingConversation?: boolean;
  isRestartingRuntime?: boolean;
  isLoadingHistory?: boolean;
  workspaceFiles?: WorkspaceFile[];
  pendingUploadedFiles?: Pick<UploadedFile, "filename" | "file_path">[];
  onDeleteFile?: (filename: string) => Promise<boolean>;
  onDeleteFolder?: (folderPath: string) => Promise<boolean>;
  onReadFileContent?: (filename: string) => Promise<string | null>;
  onRefreshWorkspaceFiles?: () => Promise<void>;
  onMoveFile?: (source: string, target: string) => Promise<boolean>;
  onUploadFiles?: (files: File[] | FileList) => Promise<void>;
  onViewExecutionRecords?: () => Promise<void> | void;
  onCompactConversation?: (instruction?: string) => Promise<void> | void;
  onRestartRuntime?: () => Promise<void> | void;
  activeTabRequest?: {
    tab: SidebarTab;
    key: number;
    targetWorkspaceId?: string | null;
  } | null;
  workspaceSummary?: TaskWorkspaceSummary;
  sessionStatus?: SessionStatusInfo | null;
  /** 是否为自动研究模式 */
  /** 研究状态 */
  /** 是否正在加载研究状态 */
  onManageDatabaseConnections?: () => void;
  onCreateDatabaseConnection?: () => void;
  onOpenKnowledgeBaseDialog?: () => void;
  onOpenKnowledgeGraphDialog?: () => void;
  onOpenWorkspaceSettings?: () => void;
  onNewConversation?: () => void;
  defaultActiveTab?: SidebarTab;
}

export function SidebarProvider({
  children,
  isOpen,
  taskList: taskListProp,
  selectedTask,
  selectedTaskId,
  onSelectTask,
  onClose,
  onOpen,
  width = 400,
  onWidthChange,
  sessionId,
  sessionTitle,
  messageCount,
  executionRecordCount,
  lastRuntimeState,
  isSessionRunning = false,
  isCompactingConversation = false,
  isRestartingRuntime = false,
  isLoadingHistory = false,
  workspaceFiles = [],
  pendingUploadedFiles: _pendingUploadedFiles,
  onDeleteFile,
  onDeleteFolder,
  onReadFileContent,
  onRefreshWorkspaceFiles,
  onMoveFile,
  onUploadFiles: _onUploadFiles,
  onViewExecutionRecords,
  onCompactConversation,
  onRestartRuntime,
  activeTabRequest,
  workspaceSummary,
  sessionStatus,
  onManageDatabaseConnections,
  onCreateDatabaseConnection,
  onOpenKnowledgeBaseDialog: _onOpenKnowledgeBaseDialog,
  onOpenKnowledgeGraphDialog: _onOpenKnowledgeGraphDialog,
  onOpenWorkspaceSettings,
  onNewConversation: _onNewConversation,
  defaultActiveTab = "artifacts",
}: SidebarProviderProps) {
  const taskList = useMemo(() => taskListProp ?? [], [taskListProp]);
  void _pendingUploadedFiles;
  void _onUploadFiles;
  void _onOpenKnowledgeBaseDialog;
  void _onOpenKnowledgeGraphDialog;
  void _onNewConversation;

  // 追踪 isSessionRunning 变为 true 的时间戳，跨 tab 切换不丢失
  const runningStartedAtRef = useRef<number>(0);
  const runningStartedAt = isSessionRunning ? runningStartedAtRef.current || undefined : undefined;
  useEffect(() => {
    if (isSessionRunning && runningStartedAtRef.current === 0) {
      runningStartedAtRef.current = Date.now();
    } else if (!isSessionRunning) {
      runningStartedAtRef.current = 0;
    }
  }, [isSessionRunning]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const defaultVisibleTab = activeTabRequest?.tab ?? defaultActiveTab;
  const [activeTab, setActiveTab] = useState<SidebarTab>(defaultVisibleTab);
  const didMountDefaultTabSyncRef = useRef(false);
  const [isExporting, setIsExporting] = useState(false);
  const { toasts, showError, showSuccess } = useFileUploadToast();
  const setSafeTimeout = useSafeTimeout();
  const [selectedTool, setSelectedTool] = useState<{
    toolName: string;
    toolParams?: Record<string, unknown>;
    toolOutput?: string;
    taskId?: string;
  } | null>(null);
  useEffect(() => {
    if (!activeTabRequest) {
      return;
    }
    setActiveTab(activeTabRequest.tab);
  }, [activeTabRequest]);

  useEffect(() => {
    if (!didMountDefaultTabSyncRef.current) {
      didMountDefaultTabSyncRef.current = true;
      return;
    }

    setActiveTab(defaultActiveTab);
  }, [defaultActiveTab]);

  const downloadBlob = useCallback((blob: Blob, filename: string) => {
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    window.URL.revokeObjectURL(url);
    link.remove();
  }, []);

  const getDownloadFilename = useCallback(
    (response: Response, fallbackFilename: string) => {
      const contentDisposition = response.headers.get("content-disposition");
      const match = contentDisposition?.match(/filename="?([^"]+)"?/i);
      return match?.[1] || fallbackFilename;
    },
    [],
  );

  const isExportingRef = useRef(isExporting);
  useEffect(() => {
    isExportingRef.current = isExporting;
  }, [isExporting]);

  const exportWorkspace = useCallback(async () => {
    if (!sessionId || isExportingRef.current) return;
    setIsExporting(true);
    try {
      const userId = getCurrentUserId();
      const exportUrl = API_ENDPOINTS.FILES_EXPORT(userId, sessionId);

      const response = await apiFetch(exportUrl);

      if (!response.ok) {
        throw new Error(`导出失败: ${response.status}`);
      }

      const blob = await response.blob();
      downloadBlob(blob, `workspace_${sessionId}.zip`);
      showSuccess("工作区 ZIP 导出成功");
    } catch (error) {
      console.error("Export failed:", error);
      showError(error instanceof Error ? error.message : "工作区导出失败");
    } finally {
      setSafeTimeout(() => setIsExporting(false), 2000);
    }
  }, [downloadBlob, sessionId, setSafeTimeout, showError, showSuccess]);

  const exportWorkspaceFile = useCallback(
    async (filename: string, format: "md" | "docx" | "pdf") => {
      if (!sessionId) return;

      try {
        const userId = getCurrentUserId();
        const exportUrl = `${API_ENDPOINTS.FILES_EXPORT_DOCUMENT(
          userId,
          sessionId,
          filename,
        )}?format=${format}`;

        const response = await apiFetch(exportUrl);

        if (!response.ok) {
          let detail = `导出失败: ${response.status}`;
          try {
            const payload = (await response.json()) as { detail?: string };
            if (payload.detail) {
              detail = payload.detail;
            }
          } catch {
            // keep fallback
          }
          throw new Error(detail);
        }

        const blob = await response.blob();
        const extension = format === "md" ? "md" : format;
        const fallbackFilename = `${filename.replace(/\.(md|markdown)$/i, "")}.${extension}`;
        downloadBlob(blob, getDownloadFilename(response, fallbackFilename));
        showSuccess(`${filename} 已导出为 ${format.toUpperCase()}`);
      } catch (error) {
        console.error("Document export failed:", error);
        showError(error instanceof Error ? error.message : "文档导出失败");
        throw error;
      }
    },
    [downloadBlob, getDownloadFilename, sessionId, showError, showSuccess],
  );

  const state = useMemo<SidebarState>(
    () => ({
      isOpen,
      width,
      taskList,
      subAgentTasks: [],
      selectedTask,
      selectedTaskId,
      isLoadingHistory,
      activeTab,
      workspaceSummary,
      sessionStatus,
      workspaceFiles,
      sessionId,
      sessionTitle,
      messageCount,
      executionRecordCount,
      lastRuntimeState,
      isSessionRunning,
      runningStartedAt,
      isCompactingConversation,
      isRestartingRuntime,
      isExporting,
      selectedTool,
    }),
    [
      isOpen,
      width,
      taskList,
      selectedTask,
      selectedTaskId,
      isLoadingHistory,
      activeTab,
      workspaceSummary,
      sessionStatus,
      workspaceFiles,
      sessionId,
      sessionTitle,
      messageCount,
      executionRecordCount,
      lastRuntimeState,
      isSessionRunning,
      runningStartedAt,
      isCompactingConversation,
      isRestartingRuntime,
      isExporting,
      selectedTool,
    ],
  );

  const actions = useMemo<SidebarActions>(
    () => ({
      onClose,
      onOpen,
      onSelectTask,
      onWidthChange,
      onDeleteFile,
      onDeleteFolder,
      onReadFileContent,
      onRefreshWorkspaceFiles,
      onMoveFile,
      setActiveTab,
      setIsExporting,
      exportWorkspace,
      exportWorkspaceFile,
      setSelectedTool,
      onViewExecutionRecords,
      onCompactConversation,
      onRestartRuntime,
      onManageDatabaseConnections,
      onCreateDatabaseConnection,
      onOpenWorkspaceSettings,
    }),
    [
      onClose,
      onOpen,
      onSelectTask,
      onWidthChange,
      onDeleteFile,
      onDeleteFolder,
      onReadFileContent,
      onRefreshWorkspaceFiles,
      onMoveFile,
      exportWorkspace,
      exportWorkspaceFile,
      onViewExecutionRecords,
      onCompactConversation,
      onRestartRuntime,
      onManageDatabaseConnections,
      onCreateDatabaseConnection,
      onOpenWorkspaceSettings,
    ],
  );

  const meta = useMemo<SidebarMeta>(
    () => ({ scrollRef }),
    [],
  );

  const contextValue = useMemo(
    () => ({ state, actions, meta }),
    [state, actions, meta],
  );

  return (
    <SidebarContext value={contextValue}>
      {children}
      {toasts.map((toast) => (
        <FileUploadToast
          key={toast.id}
          message={toast.message}
          type={toast.type}
        />
      ))}
    </SidebarContext>
  );
}
