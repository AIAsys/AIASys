import type { TaskEvent } from "@/types/task";
import type {
  MultiTaskStreamState,
  PerSessionData,
  TaskState,
} from "./useMultiTaskEventStream.types";

export function createEmptyMultiTaskState(): MultiTaskStreamState {
  return {
    tasks: new Map(),
    taskOrder: [],
  };
}

export function ensurePerSessionData(
  store: Map<string, PerSessionData>,
  sessionId: string,
): PerSessionData {
  let data = store.get(sessionId);
  if (!data) {
    data = {
      state: createEmptyMultiTaskState(),
      files: [],
    };
    store.set(sessionId, data);
  }
  return data;
}

export function upsertTaskWithEvents(
  prev: MultiTaskStreamState,
  taskId: string,
  events: TaskEvent[],
  label?: string,
): MultiTaskStreamState {
  const newTasks = new Map(prev.tasks);
  const existing = newTasks.get(taskId);

  newTasks.set(taskId, {
    taskId,
    label: label || existing?.label || `Task ${taskId.slice(0, 8)}`,
    events: [...(existing?.events || []), ...events],
    isComplete: existing?.isComplete || false,
    startedAt: existing?.startedAt || new Date(),
  });

  const taskOrder = prev.taskOrder.includes(taskId)
    ? prev.taskOrder
    : [...prev.taskOrder, taskId];

  return {
    ...prev,
    tasks: newTasks,
    taskOrder,
    selectedTaskId: prev.selectedTaskId || taskId,
  };
}

export function replaceTaskEvents(
  prev: MultiTaskStreamState,
  taskId: string,
  events: TaskEvent[],
  label = "Code Execution",
): MultiTaskStreamState {
  const newTasks = new Map(prev.tasks);
  newTasks.set(taskId, {
    taskId,
    label,
    events,
    isComplete: true,
    startedAt: new Date(),
  });

  const taskOrder = prev.taskOrder.includes(taskId)
    ? prev.taskOrder
    : [...prev.taskOrder, taskId];

  return {
    ...prev,
    tasks: newTasks,
    taskOrder,
    selectedTaskId: taskId,
  };
}

export function initializeListeningTask(
  prev: MultiTaskStreamState,
  taskId: string,
  label?: string,
): MultiTaskStreamState {
  const taskLabel = label || "Code Execution";
  const newTasks = new Map(prev.tasks);
  newTasks.set(taskId, {
    taskId,
    label: taskLabel,
    events: [],
    isComplete: false,
    startedAt: new Date(),
  });

  const taskOrder = prev.taskOrder.includes(taskId)
    ? prev.taskOrder
    : [...prev.taskOrder, taskId];

  return {
    ...prev,
    tasks: newTasks,
    taskOrder,
    selectedTaskId: taskId,
  };
}

export function appendTaskEventIfExists(
  prev: MultiTaskStreamState,
  taskId: string,
  taskEvent: TaskEvent,
): MultiTaskStreamState {
  const newTasks = new Map(prev.tasks);
  const task = newTasks.get(taskId);
  if (!task) return prev;

  newTasks.set(taskId, {
    ...task,
    events: [...task.events, taskEvent],
  });
  return { ...prev, tasks: newTasks };
}

export function markTaskCompleteIfExists(
  prev: MultiTaskStreamState,
  taskId: string,
): MultiTaskStreamState {
  const newTasks = new Map(prev.tasks);
  const task = newTasks.get(taskId);
  if (!task) return prev;
  newTasks.set(taskId, { ...task, isComplete: true });
  return { ...prev, tasks: newTasks };
}

export function markTaskErrorIfExists(
  prev: MultiTaskStreamState,
  taskId: string,
  errorMessage: string,
): MultiTaskStreamState {
  const newTasks = new Map(prev.tasks);
  const task = newTasks.get(taskId);
  if (!task) return prev;
  newTasks.set(taskId, {
    ...task,
    error: errorMessage,
    isComplete: true,
  });
  return { ...prev, tasks: newTasks };
}

export function completeAllTasksInState(
  prev: MultiTaskStreamState,
): MultiTaskStreamState {
  const newTasks = new Map(prev.tasks);
  newTasks.forEach((task, key) => {
    newTasks.set(key, { ...task, isComplete: true });
  });
  return { ...prev, tasks: newTasks };
}

export function buildTaskList(state: MultiTaskStreamState): TaskState[] {
  return state.taskOrder.map((id) => state.tasks.get(id)!).filter(Boolean);
}

export function hasAnyRunningTasks(state: MultiTaskStreamState): boolean {
  return Array.from(state.tasks.values()).some((t) => !t.isComplete);
}
