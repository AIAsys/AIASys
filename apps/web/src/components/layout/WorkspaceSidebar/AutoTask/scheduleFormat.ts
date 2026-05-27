import type {
  TriggerEventDocument,
  WorkspaceAutoTask,
  WorkspaceAutoTaskUpsertPayload,
} from "@/types/autoTask";

import type { AutoTaskDraft } from "./types";

export const STATUS_LABEL: Record<WorkspaceAutoTask["status"], string> = {
  active: "运行中",
  paused: "已暂停",
  disabled: "已禁用",
  completed: "已完成",
};

export const STATUS_BADGE_CLASS: Record<
  WorkspaceAutoTask["status"],
  string
> = {
  active: "border-success/20 bg-success-container text-success",
  paused: "border-warning/20 bg-warning-container text-warning",
  disabled: "border-error/20 bg-error-container text-error",
  completed: "border-foreground bg-foreground text-white",
};

export type IntervalUnit = "second" | "minute" | "hour" | "day";
export type FixedTimeMode = "daily" | "weekday" | "weekly";

const INTERVAL_UNIT_SECONDS: Record<IntervalUnit, number> = {
  second: 1,
  minute: 60,
  hour: 3600,
  day: 86400,
};

export const INTERVAL_UNIT_LABEL: Record<IntervalUnit, string> = {
  second: "秒",
  minute: "分钟",
  hour: "小时",
  day: "天",
};

export const MIN_INTERVAL_SECONDS = 60;

export const WEEKDAY_LABEL: Record<string, string> = {
  "0": "周日",
  "1": "周一",
  "2": "周二",
  "3": "周三",
  "4": "周四",
  "5": "周五",
  "6": "周六",
};

export const OVERLAP_POLICY_LABEL: Record<
  AutoTaskDraft["overlapPolicy"],
  string
> = {
  skip: "跳过本次",
  queue: "排队等候",
  parallel: "仍新建会话",
};

export const TASK_CATEGORY_LABEL: Record<
  AutoTaskDraft["taskCategory"],
  string
> = {
  scheduled: "时间触发",
  continuous: "连续推进",
};

export const FIRST_RUN_POLICY_LABEL: Record<
  AutoTaskDraft["firstRunPolicy"],
  string
> = {
  immediate: "立即执行一轮",
  next_scheduled: "等待计划时间",
};

export function shouldShowFirstRunPolicy(draft: AutoTaskDraft): boolean {
  return (
    draft.taskCategory === "scheduled" &&
    (draft.triggerType === "interval" || draft.triggerType === "cron")
  );
}

export function shouldShowTaskFirstRunPolicy(task: WorkspaceAutoTask): boolean {
  return (
    (task.task_category ?? "scheduled") === "scheduled" &&
    (task.trigger_type === "interval" || task.trigger_type === "cron")
  );
}

function formatClock(hour: string, minute: string): string {
  return `${hour.padStart(2, "0")}:${minute.padStart(2, "0")}`;
}

export function formatTimestamp(value?: string | null): string {
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

export function formatIntervalSeconds(value: string): string {
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

export function parseIntervalScheduleValue(value: string): {
  amount: string;
  unit: IntervalUnit;
} {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return {
      amount: value,
      unit: "second",
    };
  }
  if (seconds % 86400 === 0) {
    return { amount: String(seconds / 86400), unit: "day" };
  }
  if (seconds % 3600 === 0) {
    return { amount: String(seconds / 3600), unit: "hour" };
  }
  if (seconds % 60 === 0) {
    return { amount: String(seconds / 60), unit: "minute" };
  }
  return { amount: String(seconds), unit: "second" };
}

export function buildIntervalScheduleValue(
  amount: string,
  unit: IntervalUnit,
): string {
  const trimmed = amount.trim();
  if (!trimmed) {
    return "";
  }

  const numericAmount = Number(trimmed);
  if (!Number.isFinite(numericAmount) || numericAmount <= 0) {
    return trimmed;
  }

  return String(numericAmount * INTERVAL_UNIT_SECONDS[unit]);
}

export function formatFixedTimeExpression(value: string): string {
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
    return `每${WEEKDAY_LABEL[dayOfWeek]} ${clock}`;
  }

  return `按固定时间 · ${value}`;
}

export function parseFixedTimeScheduleValue(value: string): {
  mode: FixedTimeMode;
  time: string;
  weekday: string;
} {
  const fields = value.trim().split(/\s+/);
  if (fields.length !== 5) {
    return {
      mode: "daily",
      time: "08:00",
      weekday: "1",
    };
  }

  const [minute, hour, dayOfMonth, month, dayOfWeek] = fields;
  if (!/^\d+$/.test(minute) || !/^\d+$/.test(hour)) {
    return {
      mode: "daily",
      time: "08:00",
      weekday: "1",
    };
  }

  const time = formatClock(hour, minute);
  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "*") {
    return { mode: "daily", time, weekday: "1" };
  }
  if (dayOfMonth === "*" && month === "*" && dayOfWeek === "1-5") {
    return { mode: "weekday", time, weekday: "1" };
  }
  if (dayOfMonth === "*" && month === "*" && /^\d$/.test(dayOfWeek)) {
    return { mode: "weekly", time, weekday: dayOfWeek };
  }

  return {
    mode: "daily",
    time,
    weekday: "1",
  };
}

export function buildFixedTimeScheduleValue(
  mode: FixedTimeMode,
  time: string,
  weekday: string,
): string {
  const [hour, minute] = time.split(":");
  if (!hour || !minute) {
    return "";
  }

  if (mode === "daily") {
    return `${Number(minute)} ${Number(hour)} * * *`;
  }
  if (mode === "weekday") {
    return `${Number(minute)} ${Number(hour)} * * 1-5`;
  }

  return `${Number(minute)} ${Number(hour)} * * ${weekday}`;
}

export function formatScheduleValue(task: WorkspaceAutoTask): string {
  if (task.task_category === "continuous") {
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

export function summarizeText(value: string, limit = 180): string {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (!normalized) {
    return "未填写说明。";
  }

  if (normalized.length <= limit) {
    return normalized;
  }

  return `${normalized.slice(0, limit).trimEnd()}...`;
}

export function formatDraftSchedule(draft: AutoTaskDraft): string {
  if (!draft.triggerValue.trim() && draft.triggerType !== "continuous") {
    return "未设置";
  }

  if (draft.triggerType === "continuous") {
    return "连续推进";
  }

  if (draft.triggerType === "interval") {
    if (
      !Number.isFinite(Number(draft.triggerValue)) ||
      Number(draft.triggerValue) <= 0
    ) {
      return "间隔规则待完善";
    }
    return formatIntervalSeconds(draft.triggerValue);
  }

  if (draft.triggerType === "cron") {
    return formatFixedTimeExpression(draft.triggerValue.trim());
  }

  const normalized = normalizeOnceScheduleValue(draft.triggerValue);
  return normalized ? formatTimestamp(normalized) : "单次时间待完善";
}

export function toDatetimeLocalValue(value?: string | null): string {
  if (!value) {
    return "";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }

  const offset = date.getTimezoneOffset();
  const localDate = new Date(date.getTime() - offset * 60_000);
  return localDate.toISOString().slice(0, 16);
}

export function normalizeOnceScheduleValue(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }

  const date = new Date(trimmed);
  if (Number.isNaN(date.getTime())) {
    return trimmed;
  }

  return date.toISOString();
}

export function getTaskEventId(event: TriggerEventDocument): string | null {
  const taskId = event.payload.task_id;
  return typeof taskId === "string" && taskId ? taskId : null;
}

export function getAutoTaskTitle(task: WorkspaceAutoTask): string {
  return task.title?.trim() || task.task_id;
}

export function buildDraftFromTask(task: WorkspaceAutoTask): AutoTaskDraft {
  return {
    title: task.title || "",
    prompt: task.prompt || "",
    triggerType: task.trigger_type,
    triggerValue:
      task.trigger_type === "once"
        ? toDatetimeLocalValue(task.trigger_value)
        : task.trigger_value,
    enabled: task.status === "active",
    modelId: task.model_id || task.model || "",
    overlapPolicy: task.overlap_policy || "skip",
    bindSessionId: task.bind_session_id || "",
    sessionStrategy:
      task.session_strategy ??
      (task.bind_session_id ? "bind_session" : "new_each_time"),
    continuationPrompt: task.continuation_prompt || "",
    maxContinuations: task.max_continuations ?? -1,
    taskCategory: task.task_category ?? "scheduled",
    firstRunPolicy: task.first_run_policy ?? "next_scheduled",
    stopOnConsecutiveErrors: task.stop_on_consecutive_errors ?? 10,
    stopOnSignal: task.stop_on_signal ?? true,
  };
}

export function buildPayloadFromDraft(
  draft: AutoTaskDraft,
): WorkspaceAutoTaskUpsertPayload {
  return {
    title: draft.title.trim(),
    prompt: draft.prompt.trim(),
    trigger_type: draft.triggerType,
    trigger_value:
      draft.triggerType === "once"
        ? normalizeOnceScheduleValue(draft.triggerValue)
        : draft.triggerType === "continuous"
          ? ""
          : draft.triggerValue.trim(),
    status: draft.enabled ? "active" : "paused",
    model_id: draft.modelId.trim() || null,
    sandbox_mode: "local",
    auto_enable_hosting: false,
    hosting_bootstrap_mode: "resume_only",
    overlap_policy: draft.overlapPolicy,
    session_strategy: draft.sessionStrategy,
    bind_session_id:
      draft.sessionStrategy === "bind_session"
        ? draft.bindSessionId.trim() || null
        : null,
    continuation_prompt: draft.continuationPrompt.trim() || null,
    max_continuations: draft.maxContinuations,
    task_category: draft.taskCategory,
    first_run_policy:
      draft.taskCategory === "continuous"
        ? "immediate"
        : draft.firstRunPolicy,
    stop_on_consecutive_errors: draft.stopOnConsecutiveErrors,
    stop_on_signal: draft.stopOnSignal,
  };
}

export function validateDraft(draft: AutoTaskDraft): string | null {
  if (!draft.title.trim()) {
    return "任务名称不能为空。";
  }
  if (!draft.prompt.trim()) {
    return "提示词不能为空。";
  }
  if (
    draft.sessionStrategy === "bind_session" &&
    !draft.bindSessionId.trim()
  ) {
    return "绑定会话模式需要选择会话。";
  }
  // 时间触发任务校验触发规则
  if (draft.taskCategory === "scheduled") {
    if (!draft.triggerValue.trim()) {
      return "请先填写触发规则。";
    }
    if (draft.triggerType === "interval") {
      const seconds = Number(draft.triggerValue);
      if (!Number.isFinite(seconds) || seconds < MIN_INTERVAL_SECONDS) {
        return `按间隔执行最短支持 ${MIN_INTERVAL_SECONDS} 秒。`;
      }
    }
    if (draft.triggerType === "cron") {
      const fields = draft.triggerValue.trim().split(/\s+/);
      if (fields.length !== 5) {
        return "按固定时间需要填写 5 段时间规则，例如 0 8 * * *（表示每天 08:00）。";
      }
    }
    if (draft.triggerType === "once") {
      if (!normalizeOnceScheduleValue(draft.triggerValue)) {
        return "单次执行需要填写有效时间。";
      }
    }
  }
  // 连续推进任务校验停止条件
  if (draft.taskCategory === "continuous") {
    if (
      !Number.isFinite(draft.stopOnConsecutiveErrors) ||
      draft.stopOnConsecutiveErrors < 1
    ) {
      return "连续错误阈值必须是正整数。";
    }
  }
  return null;
}


export function formatStopConditionsSummary(
  task: WorkspaceAutoTask,
): string {
  if (task.task_category !== "continuous") {
    return "";
  }
  const parts: string[] = [];
  if (task.stop_on_signal) {
    parts.push("AI 可自主结束");
  }
  if (task.max_continuations > 0) {
    parts.push(`最多 ${task.max_continuations} 轮`);
  }
  const errorThreshold = task.stop_on_consecutive_errors ?? 10;
  if (errorThreshold > 0) {
    parts.push(`${errorThreshold} 次错误禁用`);
  }
  return parts.join(" · ");
}
