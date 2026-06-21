/**
 * SubAgent Task 事件监听 Hook
 *
 * 用于监听和管理 SubAgent Task 的执行事件
 * 支持 per-session 任务状态存储
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { apiRequest } from "@/lib/api/httpClient";
import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import type { ExecutionEvent } from "@/types/api";
import type { TaskEvent } from "@/types/task";
import {
  mapExecutionEventsToTaskEvents,
} from "./useMultiTaskEventStream.events";
import {
  buildTaskList,
  completeAllTasksInState,
  createEmptyMultiTaskState,
  ensurePerSessionData,
  hasAnyRunningTasks,
  replaceTaskEvents,
  upsertTaskWithEvents,
} from "./useMultiTaskEventStream.state";
import type {
  MultiTaskStreamState,
  NotebookHistoryItem,
  PerSessionData,
  UseMultiTaskEventStreamReturn,
  WorkspaceFile,
} from "./useMultiTaskEventStream.types";

export type {
  MultiTaskStreamState,
  TaskState,
  UseMultiTaskEventStreamReturn,
  WorkspaceFile,
} from "./useMultiTaskEventStream.types";

/**
 * SubAgent Task 事件监听 Hook — 支持 per-session 任务状态
 */
export function useMultiTaskEventStream(): UseMultiTaskEventStreamReturn {
  const [state, setState] = useState<MultiTaskStreamState>(createEmptyMultiTaskState());
  const [workspaceFiles, setWorkspaceFiles] = useState<WorkspaceFile[]>([]);

  const abortControllersRef = useRef<Map<string, AbortController>>(new Map());
  const perSessionRef = useRef<Map<string, PerSessionData>>(new Map());
  const activeSessionIdRef = useRef<string>("");

  const setActiveSessionId = useCallback((id: string) => {
    activeSessionIdRef.current = id;
  }, []);

  const getPerSessionData = useCallback(
    (sessionId: string): PerSessionData =>
      ensurePerSessionData(perSessionRef.current, sessionId),
    [],
  );

  const initSession = useCallback((id: string) => {
    ensurePerSessionData(perSessionRef.current, id);
  }, []);

  const removeSession = useCallback((id: string) => {
    perSessionRef.current.delete(id);
  }, []);

  const stateRef = useRef(state);
  const workspaceFilesRef = useRef(workspaceFiles);

  useEffect(() => {
    stateRef.current = state;
    workspaceFilesRef.current = workspaceFiles;
  }, [state, workspaceFiles]);

  const switchSession = useCallback(
    (fromId: string, toId: string) => {
      if (fromId === toId) return;

      if (fromId) {
        const fromData = getPerSessionData(fromId);
        // 深拷贝 tasks Map，避免跨 session 共享 TaskState 引用
        const deepTasks = new Map<string, typeof stateRef.current.tasks extends Map<string, infer V> ? V : never>();
        stateRef.current.tasks.forEach((task, taskId) => {
          deepTasks.set(taskId, {
            ...task,
            events: task.events.map((e) => ({ ...e })),
          });
        });
        fromData.state = {
          ...stateRef.current,
          tasks: deepTasks,
        };
        fromData.files = workspaceFilesRef.current.map((f) => ({ ...f }));
      }

      const toData = getPerSessionData(toId);
      const toDeepTasks = new Map<string, typeof toData.state.tasks extends Map<string, infer V> ? V : never>();
      toData.state.tasks.forEach((task, taskId) => {
        toDeepTasks.set(taskId, {
          ...task,
          events: task.events.map((e) => ({ ...e })),
        });
      });
      setState({
        tasks: toDeepTasks,
        taskOrder: [...toData.state.taskOrder],
        selectedTaskId: toData.state.selectedTaskId,
      });
      setWorkspaceFiles(toData.files.map((f) => ({ ...f })));
      activeSessionIdRef.current = toId;
    },
    [getPerSessionData],
  );

  const syncNotebookHistory = useCallback(
    async (taskId: string, sessionId: string) => {
      try {
        const userId = getCurrentUserId();
        const endpoint = API_ENDPOINTS.EXECUTION_FLOW(userId, sessionId);
        const data = await apiRequest<{ history?: NotebookHistoryItem[] }>(endpoint);
        const history = data.history || [];

        const notebookEvents: TaskEvent[] = history.flatMap((item) => {
          const timestampSeconds = item.timestamp || Date.now() / 1000;
          return [
            {
              event: "tool_start",
              tool_name: "LocalIPythonBox",
              tool_params: item.code || "",
              agent_name: "专家",
              source_agent: "专家",
              timestamp: new Date(timestampSeconds * 1000).toISOString(),
            },
            {
              event: "tool_output",
              tool_name: "LocalIPythonBox",
              content:
                (item.stdout || "") + (item.stderr ? `\n[stderr]\n${item.stderr}` : ""),
              status: item.success ? "success" : "error",
              agent_name: "专家",
              source_agent: "专家",
              timestamp: new Date(timestampSeconds * 1000).toISOString(),
            },
          ];
        });

        const updater = (prev: MultiTaskStreamState): MultiTaskStreamState => {
          const newTasks = new Map(prev.tasks);
          const existing = newTasks.get(taskId);

          newTasks.set(taskId, {
            taskId,
            label: existing?.label || "当前会话代码执行",
            events: notebookEvents,
            isComplete: existing?.isComplete ?? true,
            startedAt: existing?.startedAt || new Date(),
          });

          return {
            ...prev,
            tasks: newTasks,
            taskOrder: prev.taskOrder.includes(taskId)
              ? prev.taskOrder
              : [...prev.taskOrder, taskId],
            selectedTaskId: prev.selectedTaskId || taskId,
          };
        };

        if (sessionId === activeSessionIdRef.current) {
          setState(updater);
        } else {
          const psd = getPerSessionData(sessionId);
          psd.state = updater(psd.state);
        }
      } catch (err) {
        console.error("Failed to sync notebook history:", err);
      }
    },
    [getPerSessionData],
  );

  const stopTask = useCallback((taskId: string) => {
    const controller = abortControllersRef.current.get(taskId);
    if (controller) {
      controller.abort();
      abortControllersRef.current.delete(taskId);
    }
  }, []);

  const stopAll = useCallback(() => {
    abortControllersRef.current.forEach((controller) => controller.abort());
    abortControllersRef.current.clear();
  }, []);

  const reset = useCallback(() => {
    stopAll();
    setState(createEmptyMultiTaskState());
  }, [stopAll]);

  const resetSession = useCallback(
    (sessionId: string) => {
      stopAll();

      if (sessionId === activeSessionIdRef.current) {
        setState(createEmptyMultiTaskState());
        setWorkspaceFiles([]);
      } else {
        perSessionRef.current.set(sessionId, {
          state: createEmptyMultiTaskState(),
          files: [],
        });
      }
    },
    [stopAll],
  );

  /** 仅重置指定 session 的任务状态，不影响工作区文件和监控连接（用于 SSE 重连去重） */
  const resetSessionTaskState = useCallback(
    (sessionId: string) => {
      if (sessionId === activeSessionIdRef.current) {
        setState(createEmptyMultiTaskState());
      } else {
        const psd = getPerSessionData(sessionId);
        psd.state = createEmptyMultiTaskState();
      }
    },
    [getPerSessionData],
  );

  useEffect(() => {
    return () => stopAll();
  }, [stopAll]);

  const selectTask = useCallback((taskId: string) => {
    setState((prev) => ({ ...prev, selectedTaskId: taskId }));
  }, []);

  const addTaskEvents = useCallback((taskId: string, events: TaskEvent[], label?: string) => {
    setState((prev) => upsertTaskWithEvents(prev, taskId, events, label));
  }, []);

  const addStreamEventsForSession = useCallback(
    (sessionId: string, taskId: string, events: TaskEvent[], label?: string) => {
      if (sessionId === activeSessionIdRef.current) {
        setState((prev) => upsertTaskWithEvents(prev, taskId, events, label));
      } else {
        const psd = getPerSessionData(sessionId);
        psd.state = upsertTaskWithEvents(psd.state, taskId, events, label);
      }
    },
    [getPerSessionData],
  );

  const loadHistoricalEvents = useCallback(
    (taskId: string, events: ExecutionEvent[], label?: string) => {
      const taskEvents = mapExecutionEventsToTaskEvents(taskId, events);
      setState((prev) => replaceTaskEvents(prev, taskId, taskEvents, label || "Code Execution"));
    },
    [],
  );

  const selectedTask = state.selectedTaskId
    ? state.tasks.get(state.selectedTaskId)
    : undefined;
  const taskList = buildTaskList(state);
  const hasAnyRunning = hasAnyRunningTasks(state);

  const completeHost = useCallback(() => {
    // Host 完成时的处理逻辑
  }, []);

  const completeAllTasks = useCallback(() => {
    setState((prev) => completeAllTasksInState(prev));
  }, []);

  const updateWorkspaceFiles = useCallback((files: WorkspaceFile[]) => {
    setWorkspaceFiles(files);
  }, []);

  const updateWorkspaceFilesForSession = useCallback(
    (sessionId: string, files: WorkspaceFile[]) => {
      if (sessionId === activeSessionIdRef.current) {
        setWorkspaceFiles(files);
        return;
      }
      const sessionData = getPerSessionData(sessionId);
      sessionData.files = files;
    },
    [getPerSessionData],
  );

  return {
    taskList,
    selectedTask,
    selectedTaskId: state.selectedTaskId,
    hasAnyRunning,
    selectTask,
    addStreamEvents: addTaskEvents,
    addStreamEventsForSession,
    loadHistoricalEvents,
    stopTask,
    stopAll,
    reset,
    resetSession,
    resetSessionTaskState,
    completeHost,
    completeAllTasks,
    workspaceFiles,
    updateWorkspaceFiles,
    updateWorkspaceFilesForSession,
    syncNotebookHistory,
    switchSession,
    initSession,
    removeSession,
    setActiveSessionId,
  };
}
