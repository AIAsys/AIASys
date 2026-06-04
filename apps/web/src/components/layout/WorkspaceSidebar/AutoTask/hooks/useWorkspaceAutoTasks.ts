import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";

import {
  createWorkspaceAutoTask,
  deleteWorkspaceAutoTask,
  getWorkspaceResearchTriggerEvents,
  getWorkspaceAutoTasks,
  runWorkspaceAutoTaskNow,
  updateWorkspaceAutoTask,
} from "@/lib/api/workspaces";
import type {
  TriggerEventDocument,
  WorkspaceAutoTask,
} from "@/types/autoTask";

import {
  buildDraftFromTask,
  buildPayloadFromDraft,
  getAutoTaskTitle,
  getTaskEventId,
  validateDraft,
} from "../scheduleFormat";
import {
  buildDraftFromTemplate,
  createEmptyAutoTaskDraft,
} from "../templates";
import type {
  AutoTaskDraft,
  AutoTaskFeedback,
  AutoTaskSummary,
  AutoTaskTemplate,
} from "../types";

interface UseWorkspaceAutoTasksParams {
  workspaceId?: string;
  defaultBindSessionId?: string;
}

export interface UseWorkspaceAutoTasksResult {
  isLoading: boolean;
  loadError: string | null;
  feedback: AutoTaskFeedback | null;
  sortedTasks: WorkspaceAutoTask[];
  latestTaskEvents: ReadonlyMap<string, TriggerEventDocument>;
  taskSummary: AutoTaskSummary;
  isEditorOpen: boolean;
  editingTaskId: string | null;
  selectedTemplateId: string | null;
  draft: AutoTaskDraft;
  isSaving: boolean;
  draftSubmitLabel: string;
  pendingActionTaskId: string | null;
  pendingDeleteTask: WorkspaceAutoTask | null;
  setDraft: Dispatch<SetStateAction<AutoTaskDraft>>;
  setPendingDeleteTask: Dispatch<
    SetStateAction<WorkspaceAutoTask | null>
  >;
  loadAutoTasks: () => Promise<void>;
  applyTemplate: (template: AutoTaskTemplate) => void;
  openCreateDialog: (template?: AutoTaskTemplate, taskCategory?: "scheduled" | "continuous") => void;
  openEditDialog: (task: WorkspaceAutoTask) => void;
  closeEditor: () => void;
  handleSubmit: () => Promise<void>;
  handleToggleTask: (task: WorkspaceAutoTask) => Promise<void>;
  handleRunNow: (task: WorkspaceAutoTask) => Promise<void>;
  confirmDeleteTask: () => Promise<void>;
}

export function useWorkspaceAutoTasks({
  workspaceId,
  defaultBindSessionId = "",
}: UseWorkspaceAutoTasksParams): UseWorkspaceAutoTasksResult {
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<AutoTaskFeedback | null>(null);
  const [autoTasks, setAutoTasks] = useState<WorkspaceAutoTask[]>(
    [],
  );
  const [autoTaskEvents, setScheduleEvents] = useState<TriggerEventDocument[]>(
    [],
  );
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  const [selectedTemplateId, setSelectedTemplateId] = useState<string | null>(
    null,
  );
  const [draft, setDraft] = useState<AutoTaskDraft>(
    createEmptyAutoTaskDraft(),
  );
  const [isSaving, setIsSaving] = useState(false);
  const [pendingActionTaskId, setPendingActionTaskId] = useState<string | null>(
    null,
  );
  const [pendingDeleteTask, setPendingDeleteTask] =
    useState<WorkspaceAutoTask | null>(null);

  const draftRef = useRef(draft);
  draftRef.current = draft;
  const isSavingRef = useRef(isSaving);
  isSavingRef.current = isSaving;

  const loadAutoTasks = useCallback(async () => {
    if (!workspaceId) {
      setAutoTasks([]);
      setScheduleEvents([]);
      setIsLoading(false);
      setLoadError(null);
      return;
    }

    async function loadOptional<T>(
      loader: () => Promise<T>,
      label: string,
    ): Promise<T | null> {
      try {
        return await loader();
      } catch (error) {
        console.warn(`Failed to load ${label}:`, error);
        return null;
      }
    }

    setIsLoading(true);
    setLoadError(null);

    const [tasksResponse, triggerResponse] = await Promise.all([
      loadOptional(() => getWorkspaceAutoTasks(workspaceId), "auto tasks"),
      loadOptional(
        () => getWorkspaceResearchTriggerEvents(workspaceId),
        "research trigger events",
      ),
    ]);

    setAutoTasks(tasksResponse?.tasks ?? []);
    setScheduleEvents(
      (triggerResponse?.trigger_events ?? []).filter(
        (item) => item.source_type === "schedule",
      ),
    );

    if (!tasksResponse && !triggerResponse) {
      setLoadError("当前还没有可读取的自动化任务或触发记录。");
    } else {
      setLoadError(null);
    }

    setIsLoading(false);
  }, [workspaceId]);

  useEffect(() => {
    void loadAutoTasks();
  }, [loadAutoTasks]);

  useEffect(() => {
    setFeedback(null);
  }, [workspaceId]);

  const taskSummary = useMemo(
    () =>
      autoTasks.reduce<AutoTaskSummary>(
        (summary, task) => {
          summary.total += 1;
          if (task.status === "active") {
            summary.active += 1;
          }
          if (task.status === "paused" || task.status === "disabled") {
            summary.idle += 1;
          }
          if (task.consecutive_errors > 0 || Boolean(task.last_error)) {
            summary.error += 1;
          }
          return summary;
        },
        { total: 0, active: 0, idle: 0, error: 0 },
      ),
    [autoTasks],
  );

  const sortedTasks = useMemo(() => {
    const statusRank: Record<WorkspaceAutoTask["status"], number> = {
      active: 0,
      paused: 1,
      disabled: 2,
      completed: 3,
    };

    return [...autoTasks].sort((left, right) => {
      const statusDelta = statusRank[left.status] - statusRank[right.status];
      if (statusDelta !== 0) {
        return statusDelta;
      }

      const leftNext = left.next_run_at || "9999";
      const rightNext = right.next_run_at || "9999";
      const nextDelta = leftNext.localeCompare(rightNext);
      if (nextDelta !== 0) {
        return nextDelta;
      }

      return right.updated_at.localeCompare(left.updated_at);
    });
  }, [autoTasks]);

  const latestTaskEvents = useMemo(() => {
    const taskEventMap = new Map<string, TriggerEventDocument>();
    const sortedScheduleEvents = [...autoTaskEvents].sort((left, right) =>
      right.created_at.localeCompare(left.created_at),
    );

    for (const event of sortedScheduleEvents) {
      const taskId = getTaskEventId(event);
      if (!taskId || taskEventMap.has(taskId)) {
        continue;
      }
      taskEventMap.set(taskId, event);
    }

    return taskEventMap;
  }, [autoTaskEvents]);

  const draftSubmitLabel = editingTaskId
    ? "保存修改"
    : draft.enabled
      ? "创建并启用"
      : "保存为暂停";

  const withDefaultBindSession = useCallback(
    (baseDraft: AutoTaskDraft): AutoTaskDraft => {
      if (baseDraft.sessionStrategy !== "bind_session") {
        return baseDraft;
      }
      return {
        ...baseDraft,
        bindSessionId: baseDraft.bindSessionId.trim() || defaultBindSessionId,
      };
    },
    [defaultBindSessionId],
  );

  const applyTemplate = useCallback((template: AutoTaskTemplate) => {
    setSelectedTemplateId(template.id);
    setDraft(withDefaultBindSession(buildDraftFromTemplate(template)));
  }, [withDefaultBindSession]);

  const openCreateDialog = useCallback((template?: AutoTaskTemplate, taskCategory?: "scheduled" | "continuous") => {
    setEditingTaskId(null);
    setFeedback(null);
    setSelectedTemplateId(template?.id ?? null);
    const baseDraft = template
      ? buildDraftFromTemplate(template)
      : createEmptyAutoTaskDraft();
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
    setDraft(withDefaultBindSession(baseDraft));
    setIsEditorOpen(true);
  }, [defaultBindSessionId, withDefaultBindSession]);

  const openEditDialog = useCallback((task: WorkspaceAutoTask) => {
    setEditingTaskId(task.task_id);
    setSelectedTemplateId(null);
    setFeedback(null);
    setDraft(buildDraftFromTask(task));
    setIsEditorOpen(true);
  }, []);

  const resetEditorState = useCallback(() => {
    setIsEditorOpen(false);
    setEditingTaskId(null);
    setSelectedTemplateId(null);
    setDraft(createEmptyAutoTaskDraft());
  }, []);

  const closeEditor = useCallback(() => {
    if (isSavingRef.current) {
      return;
    }
    resetEditorState();
  }, [resetEditorState]);

  const handleSubmit = useCallback(async () => {
    if (!workspaceId || isSavingRef.current) {
      return;
    }

    const validationError = validateDraft(draftRef.current);
    if (validationError) {
      setFeedback({ tone: "error", message: validationError });
      return;
    }

    setIsSaving(true);
    setFeedback(null);

    try {
      const payload = buildPayloadFromDraft(draftRef.current);

      if (editingTaskId) {
        await updateWorkspaceAutoTask(workspaceId, editingTaskId, payload);
        setFeedback({ tone: "success", message: "自动化任务已更新。" });
      } else {
        await createWorkspaceAutoTask(workspaceId, payload);
        setFeedback({ tone: "success", message: "自动化任务已创建。" });
      }

      resetEditorState();
      await loadAutoTasks();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "保存自动化任务失败。";
      setFeedback({ tone: "error", message });
    } finally {
      setIsSaving(false);
    }
  }, [
    editingTaskId,
    loadAutoTasks,
    resetEditorState,
    workspaceId,
  ]);

  const handleToggleTask = useCallback(
    async (task: WorkspaceAutoTask) => {
      if (!workspaceId) {
        return;
      }

      setPendingActionTaskId(task.task_id);
      setFeedback(null);

      try {
        const nextStatus = task.status === "active" ? "paused" : "active";
        await updateWorkspaceAutoTask(workspaceId, task.task_id, {
          status: nextStatus,
        });
        setFeedback({
          tone: "success",
          message:
            nextStatus === "active"
              ? `已重新启用 ${getAutoTaskTitle(task)}。`
              : `已暂停 ${getAutoTaskTitle(task)}。`,
        });
        await loadAutoTasks();
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "切换自动化任务状态失败。";
        setFeedback({ tone: "error", message });
      } finally {
        setPendingActionTaskId(null);
      }
    },
    [loadAutoTasks, workspaceId],
  );

  const handleRunNow = useCallback(
    async (task: WorkspaceAutoTask) => {
      if (!workspaceId) {
        return;
      }

      setPendingActionTaskId(task.task_id);
      setFeedback(null);

      try {
        const response = await runWorkspaceAutoTaskNow(
          workspaceId,
          task.task_id,
        );
        const overlapHint =
          response.result.execution_reason ===
          "overlap_skipped_active_auto_task_branch"
            ? " 上一次自动化任务会话还没结束，本轮按 skip 策略跳过。"
            : response.result.execution_reason ===
                "overlap_queued_until_previous_auto_task_branch_finishes"
              ? ` 上一次自动化任务会话还没结束，本轮已排队，待运行会话结束后再自动新建。当前排队 ${task.pending_run_count ?? 0} 次。`
              : "";
        const fallbackHint =
          response.result.executed === false
            ? overlapHint || " 已记录一次自动触发，但这次没有继续生成新的自动化任务会话。"
            : " 已记录这次自动触发。";

        setFeedback({
          tone: "success",
          message: `${getAutoTaskTitle(task)} 已立即运行。${fallbackHint}`,
        });
        await loadAutoTasks();
      } catch (error) {
        const message = error instanceof Error ? error.message : "立即运行失败。";
        setFeedback({ tone: "error", message });
      } finally {
        setPendingActionTaskId(null);
      }
    },
    [loadAutoTasks, workspaceId],
  );

  const confirmDeleteTask = useCallback(async () => {
    if (!workspaceId || !pendingDeleteTask) {
      return;
    }

    const task = pendingDeleteTask;
    setPendingActionTaskId(task.task_id);
    setFeedback(null);

    try {
      await deleteWorkspaceAutoTask(workspaceId, task.task_id);
      setPendingDeleteTask(null);
      setFeedback({
        tone: "success",
        message: `${getAutoTaskTitle(task)} 已删除。`,
      });
      await loadAutoTasks();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "删除自动化任务失败。";
      setFeedback({ tone: "error", message });
    } finally {
      setPendingActionTaskId(null);
    }
  }, [loadAutoTasks, pendingDeleteTask, workspaceId]);

  return {
    isLoading,
    loadError,
    feedback,
    sortedTasks,
    latestTaskEvents,
    taskSummary,
    isEditorOpen,
    editingTaskId,
    selectedTemplateId,
    draft,
    isSaving,
    draftSubmitLabel,
    pendingActionTaskId,
    pendingDeleteTask,
    setDraft,
    setPendingDeleteTask,
    loadAutoTasks,
    applyTemplate,
    openCreateDialog,
    openEditDialog,
    closeEditor,
    handleSubmit,
    handleToggleTask,
    handleRunNow,
    confirmDeleteTask,
  };
}
