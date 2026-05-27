import {
  Pencil,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Search,
  Trash2,
} from "lucide-react";
import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

import { Input } from "@/components/ui/input";
import { lazy, Suspense } from "react";

const LazyAutoTaskEditorDialog = lazy(() =>
  import("@/components/layout/WorkspaceSidebar/AutoTask/AutoTaskEditorDialog").then(
    (module) => ({
      default: module.AutoTaskEditorDialog,
    }),
  ),
);
import {
  FIRST_RUN_POLICY_LABEL,
  TASK_CATEGORY_LABEL,
  buildDraftFromTask,
  buildPayloadFromDraft,
  shouldShowTaskFirstRunPolicy,
  validateDraft,
} from "@/components/layout/WorkspaceSidebar/AutoTask/scheduleFormat";
import {
  buildDraftFromTemplate,
  createEmptyAutoTaskDraft,
  getAutoTaskTemplates,
} from "@/components/layout/WorkspaceSidebar/AutoTask/templates";
import type { AutoTaskDraft, AutoTaskTemplate } from "@/components/layout/WorkspaceSidebar/AutoTask/types";
import type { AutoTaskSessionOption } from "@/components/layout/WorkspaceSidebar/AutoTask/types";
import {
  createWorkspaceAutoTask,
  deleteWorkspaceAutoTask,
  getGlobalAutoTasks,
  getGlobalAutoTasksSummary,
  runWorkspaceAutoTaskNow,
  updateWorkspaceAutoTask,
} from "@/lib/api/workspaces";
import { cn } from "@/lib/utils";
import type { LLMModelConfig } from "@/lib/api/llm";
import type {
  GlobalAutoTaskSummaryResponse,
  GlobalAutoTask,
  WorkspaceAutoTask,
} from "@/types/autoTask";
import type { TaskWorkspaceSummary } from "../types";

interface GlobalAutoTaskDialogProps {
  currentWorkspaceId?: string | null;
  currentSessionId?: string | null;
  currentSessionTitle?: string | null;
  workspaces: TaskWorkspaceSummary[];
  availableModels?: LLMModelConfig[];
}

type AutoTaskStatusFilter =
  | "all"
  | WorkspaceAutoTask["status"];

type AutoTaskCategoryFilter = "all" | "scheduled" | "continuous";

const STATUS_LABEL: Record<WorkspaceAutoTask["status"], string> = {
  active: "运行中",
  paused: "已暂停",
  disabled: "已禁用",
  completed: "已完成",
};

const STATUS_BADGE_CLASS: Record<WorkspaceAutoTask["status"], string> = {
  active: "border-success/20 bg-success-container text-success",
  paused: "border-warning/20 bg-warning-container text-warning",
  disabled: "border-error/20 bg-error-container text-error",
  completed: "border-foreground bg-foreground text-white",
};

const FILTER_OPTIONS: Array<{
  value: AutoTaskStatusFilter;
  label: string;
}> = [
  { value: "all", label: "全部" },
  { value: "active", label: "运行中" },
  { value: "paused", label: "已暂停" },
  { value: "disabled", label: "已禁用" },
  { value: "completed", label: "已完成" },
];

const CATEGORY_FILTER_OPTIONS: Array<{
  value: AutoTaskCategoryFilter;
  label: string;
}> = [
  { value: "all", label: "全部类别" },
  { value: "scheduled", label: "时间触发" },
  { value: "continuous", label: "连续推进" },
];

function formatTimestamp(value?: string | null): string {
  if (!value) {
    return "未记录";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString("zh-CN", {
    hour12: false,
  });
}

function formatClock(hour: string, minute: string): string {
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

function formatIntervalSeconds(value: string): string {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return `每 ${value} 秒`;
  }
  if (seconds % 86400 === 0) {
    return `每 ${seconds / 86400} 天`;
  }
  if (seconds % 3600 === 0) {
    return `每 ${seconds / 3600} 小时`;
  }
  if (seconds % 60 === 0) {
    return `每 ${seconds / 60} 分钟`;
  }
  return `每 ${seconds} 秒`;
}

function formatFixedTimeExpression(value: string): string {
  const fields = value.trim().split(/\s+/);
  if (fields.length !== 5) {
    return `按固定时间 · ${value}`;
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = fields;
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) {
    return `按固定时间 · ${value}`;
  }

  const clock = formatClock(hour, minute);

  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return `每天 ${clock}`;
  }
  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "1-5") {
    return `工作日 ${clock}`;
  }
  if (dayOfMonth === "*" && month === "*" && /^\d$/.test(dayOfWeek)) {
    const weekdayMap = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
    return `每${weekdayMap[Number(dayOfWeek)]} ${clock}`;
  }

  return `按固定时间 · ${value}`;
}

function formatScheduleValue(task: WorkspaceAutoTask): string {
  if (task.trigger_type === "continuous") {
    return "连续推进";
  }
  if (task.trigger_type === "interval") {
    return formatIntervalSeconds(task.trigger_value);
  }
  if (task.trigger_type === "cron") {
    return formatFixedTimeExpression(task.trigger_value);
  }
  return formatTimestamp(task.trigger_value);
}

function getTaskTitle(task: WorkspaceAutoTask): string {
  return task.title?.trim() || task.task_id;
}

function summarizeText(value: string, limit = 120): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "未填写说明。";
  }

  if (normalized.length <= limit) {
    return normalized;
  }

  return `${normalized.slice(0, limit).trimEnd()}...`;
}

export function GlobalAutoTaskDialog({
  currentWorkspaceId,
  currentSessionId,
  currentSessionTitle,
  workspaces,
  availableModels = [],
}: GlobalAutoTaskDialogProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);
  const [summary, setSummary] = useState<GlobalAutoTaskSummaryResponse | null>(null);
  const [tasks, setTasks] = useState<GlobalAutoTask[]>([]);
  const [statusFilter, setStatusFilter] = useState<AutoTaskStatusFilter>("all");
  const [categoryFilter, setCategoryFilter] = useState<AutoTaskCategoryFilter>("all");
  const [workspaceFilter, setWorkspaceFilter] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const deferredSearchQuery = useDeferredValue(searchQuery);
  const [pendingTaskId, setPendingTaskId] = useState<string | null>(null);
  const [pendingDeleteTask, setPendingDeleteTask] =
    useState<GlobalAutoTask | null>(null);

  // Editor state
  const templates = useMemo(() => getAutoTaskTemplates(), []);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(null);
  const [draft, setDraft] = useState<AutoTaskDraft>(createEmptyAutoTaskDraft());
  const [isSaving, setIsSaving] = useState(false);
  const [editorTargetWorkspaceId, setEditorTargetWorkspaceId] = useState<string>(
    currentWorkspaceId ?? "",
  );
  const [editorFeedback, setEditorFeedback] = useState<{
    tone: "success" | "error";
    message: string;
  } | null>(null);


  useEffect(() => {
    if (currentWorkspaceId) {
      setEditorTargetWorkspaceId(currentWorkspaceId);
    }
  }, [currentWorkspaceId]);

  const availableWorkspacesForEditor = useMemo(
    () =>
      workspaces.map((w) => ({
        id: w.workspace_id,
        title: w.title || w.workspace_id,
      })),
    [workspaces],
  );

  const editorSessionOptions = useMemo<AutoTaskSessionOption[]>(() => {
    const targetWorkspace = workspaces.find(
      (workspace) => workspace.workspace_id === editorTargetWorkspaceId,
    );
    if (!targetWorkspace) {
      return [];
    }

    const optionMap = new Map<string, AutoTaskSessionOption>();
    const addConversation = (
      conversation: TaskWorkspaceSummary["current_conversation"],
    ) => {
      if (!conversation?.session_id) {
        return;
      }
      const sessionId = conversation.session_id;
      optionMap.set(sessionId, {
        sessionId,
        title: conversation.title || "未命名会话",
        isCurrent:
          targetWorkspace.workspace_id === currentWorkspaceId &&
          sessionId === currentSessionId,
        updatedAt: conversation.updated_at,
        messageCount: conversation.message_count,
      });
    };

    addConversation(targetWorkspace.current_conversation);
    targetWorkspace.conversations?.forEach(addConversation);

    if (
      targetWorkspace.workspace_id === currentWorkspaceId &&
      currentSessionId &&
      !optionMap.has(currentSessionId)
    ) {
      optionMap.set(currentSessionId, {
        sessionId: currentSessionId,
        title:
          currentSessionTitle?.trim() ||
          targetWorkspace.current_conversation?.title ||
          "当前会话",
        isCurrent: true,
        updatedAt: targetWorkspace.current_conversation?.updated_at ?? null,
        messageCount: targetWorkspace.current_conversation?.message_count ?? null,
      });
    }

    return [...optionMap.values()].sort((left, right) => {
      if (left.isCurrent !== right.isCurrent) {
        return left.isCurrent ? -1 : 1;
      }
      return (right.updatedAt || "").localeCompare(left.updatedAt || "");
    });
  }, [
    currentSessionId,
    currentSessionTitle,
    currentWorkspaceId,
    editorTargetWorkspaceId,
    workspaces,
  ]);

  const defaultBindSessionId =
    editorSessionOptions.find((option) => option.isCurrent)?.sessionId ??
    editorSessionOptions[0]?.sessionId ??
    "";

  const draftSubmitLabel = editingTaskId
    ? "保存修改"
    : draft.enabled
      ? "创建并启用"
      : "保存为暂停";

  const openCreateDialog = useCallback((taskCategory?: "scheduled" | "continuous") => {
    setEditingTaskId(null);
    setSelectedTemplateId(null);
    setEditorFeedback(null);
    const baseDraft = createEmptyAutoTaskDraft();
    if (taskCategory) {
      baseDraft.taskCategory = taskCategory;
      if (taskCategory === "continuous") {
        baseDraft.triggerType = "continuous";
        baseDraft.triggerValue = "";
        baseDraft.sessionStrategy = "bind_session";
        baseDraft.bindSessionId = defaultBindSessionId;
        baseDraft.firstRunPolicy = "immediate";
        baseDraft.overlapPolicy =
          baseDraft.overlapPolicy === "parallel" ? "skip" : baseDraft.overlapPolicy;
      }
    }
    setDraft(baseDraft);
    setIsEditorOpen(true);
  }, [defaultBindSessionId]);

  const openEditDialog = useCallback((task: GlobalAutoTask) => {
    setEditingTaskId(task.task_id);
    setSelectedTemplateId(null);
    setEditorFeedback(null);
    setDraft(buildDraftFromTask(task));
    setEditorTargetWorkspaceId(task.workspace_id);
    setIsEditorOpen(true);
  }, []);

  const closeEditor = useCallback(() => {
    if (isSaving) return;
    setIsEditorOpen(false);
    setEditingTaskId(null);
    setSelectedTemplateId(null);
    setDraft(createEmptyAutoTaskDraft());
    setEditorFeedback(null);
  }, [isSaving]);

  const applyTemplate = useCallback((template: AutoTaskTemplate) => {
    setSelectedTemplateId(template.id);
    setDraft(buildDraftFromTemplate(template));
  }, []);

  const loadAutoTasks = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);

    try {
      const [summaryResponse, tasksResponse] = await Promise.all([
        getGlobalAutoTasksSummary(),
        getGlobalAutoTasks(),
      ]);
      setSummary(summaryResponse);
      setTasks(tasksResponse.tasks ?? []);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "读取全局自动化任务状态失败。";
      setLoadError(message);
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleEditorSubmit = useCallback(async () => {
    if (isSaving) return;

    const validationError = validateDraft(draft);
    if (validationError) {
      setEditorFeedback({ tone: "error", message: validationError });
      return;
    }

    const targetWorkspaceId = editingTaskId
      ? editorTargetWorkspaceId
      : editorTargetWorkspaceId || currentWorkspaceId;
    if (!targetWorkspaceId) {
      setEditorFeedback({ tone: "error", message: "请先选择目标工作区。" });
      return;
    }

    setIsSaving(true);
    setEditorFeedback(null);

    try {
      const payload = buildPayloadFromDraft(draft);

      if (editingTaskId) {
        await updateWorkspaceAutoTask(targetWorkspaceId, editingTaskId, payload);
        setEditorFeedback({ tone: "success", message: "自动化任务已更新。" });
      } else {
        await createWorkspaceAutoTask(targetWorkspaceId, payload);
        setEditorFeedback({ tone: "success", message: "自动化任务已创建。" });
      }

      closeEditor();
      await loadAutoTasks();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "保存自动化任务失败。";
      setEditorFeedback({ tone: "error", message });
    } finally {
      setIsSaving(false);
    }
  }, [
    draft,
    editingTaskId,
    editorTargetWorkspaceId,
    currentWorkspaceId,
    isSaving,
    closeEditor,
    loadAutoTasks,
  ]);

  useEffect(() => {
    void loadAutoTasks();
  }, [loadAutoTasks]);

  const filteredTasks = useMemo(() => {
    const normalizedQuery = deferredSearchQuery.trim().toLowerCase();
    return tasks
      .filter((task) => workspaceFilter === "all" || task.workspace_id === workspaceFilter)
      .filter((task) => statusFilter === "all" || task.status === statusFilter)
      .filter((task) => categoryFilter === "all" || task.task_category === categoryFilter)
      .filter((task) => {
        if (!normalizedQuery) {
          return true;
        }
        return [
          getTaskTitle(task),
          task.workspace_title || "",
          task.workspace_id,
          task.prompt,
        ]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);
      })
      .sort((left, right) => {
        const rank: Record<WorkspaceAutoTask["status"], number> = {
          active: 0,
          paused: 1,
          disabled: 2,
          completed: 3,
        };
        const statusDelta = rank[left.status] - rank[right.status];
        if (statusDelta !== 0) {
          return statusDelta;
        }
        return (left.next_run_at || "9999").localeCompare(right.next_run_at || "9999");
      });
  }, [deferredSearchQuery, statusFilter, tasks, workspaceFilter]);

  const workspaceSummaries = useMemo(() => {
    return [...(summary?.workspaces ?? [])].sort((left, right) => {
      const activeDelta = right.counts.active - left.counts.active;
      if (activeDelta !== 0) {
        return activeDelta;
      }
      return right.counts.total - left.counts.total;
    });
  }, [summary?.workspaces]);

  const handleToggleTask = useCallback(
    async (task: GlobalAutoTask) => {
      setPendingTaskId(task.task_id);
      setFeedback(null);
      try {
        const nextStatus = task.status === "active" ? "paused" : "active";
        await updateWorkspaceAutoTask(task.workspace_id, task.task_id, {
          status: nextStatus,
        });
        setFeedback({
          tone: "success",
          message:
            nextStatus === "active"
              ? `已重新启用 ${getTaskTitle(task)}。`
              : `已暂停 ${getTaskTitle(task)}。`,
        });
        await loadAutoTasks();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "切换自动化任务状态失败。";
        setFeedback({ tone: "error", message });
      } finally {
        setPendingTaskId(null);
      }
    },
    [loadAutoTasks],
  );

  const handleRunNow = useCallback(
    async (task: GlobalAutoTask) => {
      setPendingTaskId(task.task_id);
      setFeedback(null);
      try {
        const response = await runWorkspaceAutoTaskNow(
          task.workspace_id,
          task.task_id,
        );
        const fallbackHint =
          response.result.executed === false
            ? " 已记录一次自动触发，但后端这次没有继续生成自动执行会话。"
            : " 已记录这次自动触发。";
        setFeedback({
          tone: "success",
          message: `${getTaskTitle(task)} 已立即运行。${fallbackHint}`,
        });
        await loadAutoTasks();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "立即运行失败。";
        setFeedback({ tone: "error", message });
      } finally {
        setPendingTaskId(null);
      }
    },
    [loadAutoTasks],
  );

  const confirmDeleteTask = useCallback(async () => {
    if (!pendingDeleteTask) {
      return;
    }
    const task = pendingDeleteTask;
    setPendingTaskId(task.task_id);
    setFeedback(null);
    try {
      await deleteWorkspaceAutoTask(task.workspace_id, task.task_id);
      setPendingDeleteTask(null);
      setFeedback({
        tone: "success",
        message: `${getTaskTitle(task)} 已删除。`,
      });
      await loadAutoTasks();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "删除自动化任务失败。";
      setFeedback({ tone: "error", message });
    } finally {
      setPendingTaskId(null);
    }
  }, [loadAutoTasks, pendingDeleteTask]);

  const counts = summary?.counts ?? {
    total: 0,
    active: 0,
    paused: 0,
    disabled: 0,
    completed: 0,
  };

  const content = (
    <div className="min-h-0 flex-1 overflow-hidden px-6 py-5">
            <div className="flex h-full min-h-0 flex-col gap-4">
              {feedback ? (
                <div
                  className={cn(
                    "rounded-2xl border px-4 py-3 text-sm",
                    feedback.tone === "success"
                      ? "border-success/20 bg-success-container text-success"
                      : "border-error/20 bg-error-container text-error",
                  )}
                >
                  {feedback.message}
                </div>
              ) : null}

              {loadError ? (
                <div className="rounded-2xl border border-error/20 bg-error-container px-4 py-3 text-sm text-error">
                  {loadError}
                </div>
              ) : null}

              <div className="grid min-h-0 flex-1 grid-rows-[minmax(0,1fr)] gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                <aside className="flex flex-col min-h-0 overflow-hidden rounded-2xl border border-border bg-background">
                  <div className="border-b border-border px-4 py-3">
                    <div className="text-sm font-semibold text-foreground">工作区</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      先按工作区收窄，再处理具体规则。
                    </div>
                  </div>

                  <div className="min-h-0 overflow-y-auto px-3 py-3">
                    <div className="space-y-3">
                      <div className="rounded-xl border border-border bg-muted/15 p-2">
                        <button
                          type="button"
                          className={cn(
                            "flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left transition",
                            workspaceFilter === "all"
                              ? "bg-muted text-foreground"
                              : "bg-background text-foreground hover:bg-muted/50",
                          )}
                          onClick={() => setWorkspaceFilter("all")}
                        >
                          <div>
                            <div className="text-sm font-medium">全部工作区</div>
                            <div className="mt-1 text-[11px] text-muted-foreground">
                              {counts.total} 条任务 · {counts.active} 运行中
                            </div>
                          </div>
                          <Badge
                            variant="outline"
                            className="border-border bg-background text-muted-foreground"
                          >
                            {counts.total}
                          </Badge>
                        </button>
                      </div>

                      <div>
                        <div className="px-1 pb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                          工作区列表
                        </div>
                        {workspaceSummaries.length > 0 ? (
                          <div className="space-y-2">
                            {workspaceSummaries.map((workspace) => {
                              const isSelected = workspaceFilter === workspace.workspace_id;
                              return (
                                <button
                                  key={workspace.workspace_id}
                                  type="button"
                                  className={cn(
                                    "flex w-full items-start justify-between gap-3 rounded-xl border px-3 py-3 text-left transition",
                                    isSelected
                                      ? "border-border bg-muted/50 text-foreground"
                                      : "border-transparent bg-muted/20 text-foreground hover:border-border hover:bg-muted/35",
                                  )}
                                  onClick={() => setWorkspaceFilter(workspace.workspace_id)}
                                >
                                  <div className="min-w-0">
                                    <div className="flex flex-wrap items-center gap-2">
                                      <div className="truncate text-sm font-medium">
                                        {workspace.workspace_title}
                                      </div>
                                      {workspace.workspace_id === currentWorkspaceId ? (
                                        <Badge
                                          variant="outline"
                                          className="border-info/20 bg-info-container text-info"
                                        >
                                          当前
                                        </Badge>
                                      ) : null}
                                    </div>
                                    <div className="mt-1 text-[11px] text-muted-foreground">
                                      {workspace.counts.total} 条任务 · {workspace.counts.active} 运行中
                                    </div>
                                  </div>
                                  <Badge
                                    variant="outline"
                                    className="border-border bg-background text-muted-foreground"
                                  >
                                    {workspace.counts.total}
                                  </Badge>
                                </button>
                              );
                            })}
                          </div>
                        ) : (
                          <div className="rounded-xl border border-dashed border-border bg-muted/20 px-3 py-6 text-center text-[11px] leading-5 text-muted-foreground">
                            还没有任何工作区挂上自动化任务。
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                </aside>

                <section className="flex flex-col min-h-0 overflow-hidden rounded-2xl border border-border bg-background">
                  <div className="border-b border-border px-4 py-3">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <div className="text-sm font-semibold text-foreground">
                        任务列表
                      </div>
                      <Badge
                        variant="outline"
                        className="border-border bg-background text-muted-foreground"
                      >
                        {counts.total} 条
                      </Badge>
                      {counts.active > 0 ? (
                        <Badge
                          variant="outline"
                          className="border-success/20 bg-success-container text-success"
                        >
                          {counts.active} 运行中
                        </Badge>
                      ) : null}
                      {counts.paused + counts.disabled > 0 ? (
                        <Badge
                          variant="outline"
                          className="border-warning/20 bg-warning-container text-warning"
                        >
                          {counts.paused + counts.disabled} 已停用
                        </Badge>
                      ) : null}
                      {workspaceFilter !== "all" ? (
                        <Badge
                          variant="outline"
                          className="border-info/20 bg-info-container text-info"
                        >
                          {
                            workspaceSummaries.find(
                              (workspace) => workspace.workspace_id === workspaceFilter,
                            )?.workspace_title
                          }
                        </Badge>
                      ) : null}
                    </div>
                    <div className="flex items-center gap-2">
                      {summary?.latest_run ? (
                        <div className="text-xs text-muted-foreground">
                          最近执行 {formatTimestamp(summary.latest_run.last_run_at)}
                        </div>
                      ) : null}
                      <Button
                        type="button"
                        size="sm"
                        className="h-8 gap-1.5 text-[11px]"
                        onClick={() => openCreateDialog()}
                      >
                        <Plus className="h-3.5 w-3.5" />
                        新建
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-8 gap-1.5 text-[11px]"
                        onClick={() => void loadAutoTasks()}
                        disabled={isLoading}
                      >
                        <RefreshCw
                          className={cn("h-3.5 w-3.5", isLoading && "animate-spin")}
                        />
                        刷新
                      </Button>
                    </div>
                  </div>
                </div>

                <div className="border-b border-border px-4 py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="relative min-w-[240px] flex-1">
                      <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                      <Input
                        id="global-auto-task-search"
                        aria-label="搜索全局自动化任务"
                        value={searchQuery}
                        onChange={(event) => setSearchQuery(event.target.value)}
                        placeholder="搜索任务名、工作区或提示词"
                        className="pl-8"
                      />
                    </div>
                    {FILTER_OPTIONS.map((option) => (
                      <Button
                        key={option.value}
                        type="button"
                        size="sm"
                        variant={statusFilter === option.value ? "default" : "outline"}
                        className="h-8 text-[11px]"
                        onClick={() => setStatusFilter(option.value)}
                      >
                        {option.label}
                      </Button>
                    ))}
                    <div className="mx-1 h-4 w-px bg-border" />
                    {CATEGORY_FILTER_OPTIONS.map((option) => (
                      <Button
                        key={option.value}
                        type="button"
                        size="sm"
                        variant={categoryFilter === option.value ? "default" : "outline"}
                        className="h-8 text-[11px]"
                        onClick={() => setCategoryFilter(option.value)}
                      >
                        {option.label}
                      </Button>
                    ))}
                  </div>
                </div>

                <div className="min-h-0 overflow-y-auto">
                  {filteredTasks.length > 0 ? (
                    <div className="divide-y divide-border/70">
                      {filteredTasks.map((task) => {
                        const isMutating = pendingTaskId === task.task_id;

                        return (
                          <div
                            key={task.task_id}
                            className="px-4 py-3 transition-colors hover:bg-muted/20"
                          >
                            <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center gap-2">
                                  <div className="truncate text-sm font-semibold text-foreground">
                                    {getTaskTitle(task)}
                                  </div>
                                  <Badge
                                    variant="outline"
                                    className={STATUS_BADGE_CLASS[task.status]}
                                  >
                                    {STATUS_LABEL[task.status]}
                                  </Badge>
                                  <Badge
                                    variant="outline"
                                    className="border-border bg-background text-muted-foreground"
                                  >
                                    {formatScheduleValue(task)}
                                  </Badge>
                                  {shouldShowTaskFirstRunPolicy(task) ? (
                                    <Badge
                                      variant="outline"
                                      className="border-border bg-background text-muted-foreground"
                                    >
                                      {
                                        FIRST_RUN_POLICY_LABEL[
                                          task.first_run_policy ?? "next_scheduled"
                                        ]
                                      }
                                    </Badge>
                                  ) : null}
                                  <Badge
                                    variant="outline"
                                    className="border-border bg-background text-muted-foreground"
                                  >
                                    {task.workspace_title || task.workspace_id}
                                  </Badge>
                                  <Badge
                                    variant="outline"
                                    className="border-border bg-muted/15 text-muted-foreground"
                                  >
                                    {TASK_CATEGORY_LABEL[task.task_category ?? "scheduled"]}
                                  </Badge>
                                  {task.workspace_id === currentWorkspaceId ? (
                                    <Badge
                                      variant="outline"
                                      className="border-info/20 bg-info-container text-info"
                                    >
                                      当前工作区
                                    </Badge>
                                  ) : null}
                                </div>

                                <div className="mt-1 truncate text-[12px] leading-5 text-muted-foreground">
                                  {summarizeText(task.prompt, 118)}
                                </div>

                                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
                                  <span>下次 {formatTimestamp(task.next_run_at)}</span>
                                  <span>上次 {formatTimestamp(task.last_run_at)}</span>
                                  <span>已触发 {task.fired_count} 次</span>
                                  <span>{task.workspace_title || task.workspace_id}</span>
                                </div>
                              </div>

                              <div className="flex flex-wrap items-center gap-2 xl:ml-4 xl:justify-end">
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="h-8 gap-1.5 text-[11px]"
                                  onClick={() => void handleRunNow(task)}
                                  disabled={isMutating}
                                >
                                  <Play className="h-3.5 w-3.5" />
                                  立即运行
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="h-8 gap-1.5 text-[11px]"
                                  onClick={() => openEditDialog(task)}
                                  disabled={isMutating}
                                >
                                  <Pencil className="h-3.5 w-3.5" />
                                  编辑
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="h-8 gap-1.5 text-[11px]"
                                  onClick={() => void handleToggleTask(task)}
                                  disabled={isMutating || task.status === "completed"}
                                >
                                  {task.status === "active" ? (
                                    <Pause className="h-3.5 w-3.5" />
                                  ) : (
                                    <Play className="h-3.5 w-3.5" />
                                  )}
                                  {task.status === "active" ? "暂停" : "启用"}
                                </Button>
                                <Button
                                  type="button"
                                  size="sm"
                                  variant="outline"
                                  className="h-8 gap-1.5 border-error/20 text-[11px] text-error hover:bg-error-container hover:text-error"
                                  onClick={() => setPendingDeleteTask(task)}
                                  disabled={isMutating}
                                >
                                  <Trash2 className="h-3.5 w-3.5" />
                                  删除
                                </Button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="px-4 py-10 text-center">
                      <div className="text-sm font-medium text-foreground">
                        当前筛选下没有自动化任务
                      </div>
                      <div className="mt-2 text-xs leading-6 text-muted-foreground">
                        可以切换工作区或状态筛选后再看。
                      </div>
                    </div>
                  )}
                </div>
                </section>
              </div>
            </div>
    </div>
  );

  return (
    <>
      <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-border bg-background">
        {content}
      </div>

      <Suspense fallback={null}>
        <LazyAutoTaskEditorDialog
          open={isEditorOpen}
          editingTaskId={editingTaskId}
          selectedTemplateId={selectedTemplateId}
          draft={draft}
          setDraft={setDraft}
          isSaving={isSaving}
          submitLabel={draftSubmitLabel}
          templates={templates}
          availableModels={availableModels}
          sessionOptions={editorSessionOptions}
          feedback={editorFeedback}
          targetWorkspaceId={editorTargetWorkspaceId}
          availableWorkspaces={availableWorkspacesForEditor}
          onTargetWorkspaceChange={(value) => setEditorTargetWorkspaceId(value)}
          onOpenChange={(nextOpen) => {
            if (!nextOpen) {
              closeEditor();
            }
          }}
          onApplyTemplate={applyTemplate}
          onSubmit={() => void handleEditorSubmit()}
        />
      </Suspense>

      <AlertDialog
        open={Boolean(pendingDeleteTask)}
        onOpenChange={(nextOpen) => {
          if (!nextOpen) {
            setPendingDeleteTask(null);
          }
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除自动化任务</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 “{pendingDeleteTask ? getTaskTitle(pendingDeleteTask) : ""}” 吗？
              这会移除后续自动执行计划，但不会回滚已经写入的触发历史。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pendingTaskId === pendingDeleteTask?.task_id}>
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(event) => {
                event.preventDefault();
                void confirmDeleteTask();
              }}
              disabled={pendingTaskId === pendingDeleteTask?.task_id}
            >
              {pendingTaskId === pendingDeleteTask?.task_id ? "删除中..." : "确认删除"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export default GlobalAutoTaskDialog;
