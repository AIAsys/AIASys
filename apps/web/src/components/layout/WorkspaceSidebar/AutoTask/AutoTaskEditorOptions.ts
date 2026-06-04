import {
  CalendarClock,
  Clock3,
  Infinity as InfinityIcon,
  GitBranch,
  Layers3,
  Play,
  Repeat2,
  type LucideIcon,
} from "lucide-react";

import type { AutoTaskDraft, AutoTaskSessionOption } from "./types";

export const DEFAULT_AUTO_TASK_MODEL_VALUE = "__auto_task_default_model__";
export const NO_AUTO_TASK_MODEL_VALUE = "__auto_task_no_models__";

export type ScheduledTriggerType = Extract<
  AutoTaskDraft["triggerType"],
  "interval" | "cron" | "once"
>;

export const TRIGGER_TYPE_OPTIONS: Array<{
  value: ScheduledTriggerType;
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    value: "once",
    label: "立即或单次",
    description: "创建后可立即运行，也可指定一次性时间",
    icon: Play,
  },
  {
    value: "interval",
    label: "周期触发",
    description: "按分钟、小时或天重复运行",
    icon: Repeat2,
  },
  {
    value: "cron",
    label: "固定时间",
    description: "每天、工作日或每周在固定时间运行",
    icon: CalendarClock,
  },
];

export function formatSessionOptionLabel(
  option: AutoTaskSessionOption,
): string {
  const title = option.title.trim() || "未命名会话";
  return option.isCurrent ? `${title}（当前会话）` : title;
}

export function getSessionOptionLabel(
  options: AutoTaskSessionOption[],
  sessionId: string,
): string {
  const normalizedId = sessionId.trim();
  if (!normalizedId) {
    return "未选择会话";
  }

  const option = options.find((item) => item.sessionId === normalizedId);
  if (option) {
    return formatSessionOptionLabel(option);
  }

  return `会话 ${normalizedId.slice(0, 8)}`;
}

export const AUTOMATION_MODE_OPTIONS: Array<{
  value: AutoTaskDraft["taskCategory"];
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    value: "scheduled",
    label: "按时间触发",
    description: "立即、单次、周期或固定时间运行",
    icon: Clock3,
  },
  {
    value: "continuous",
    label: "连续推进",
    description: "目标未完成时继续运行，直到停止条件触发",
    icon: InfinityIcon,
  },
];

export const SESSION_STRATEGY_OPTIONS: Array<{
  value: AutoTaskDraft["sessionStrategy"];
  label: string;
  description: string;
  icon: LucideIcon;
}> = [
  {
    value: "new_each_time",
    label: "新建会话",
    description: "每次触发都在工作区中新建普通会话",
    icon: GitBranch,
  },
  {
    value: "bind_session",
    label: "绑定会话",
    description: "回到指定会话继续推进上下文",
    icon: Layers3,
  },
];

export const OVERLAP_POLICY_OPTIONS: Array<{
  value: AutoTaskDraft["overlapPolicy"];
  label: string;
  description: string;
}> = [
  {
    value: "skip",
    label: "跳过",
    description: "上轮未结束时跳过本次",
  },
  {
    value: "queue",
    label: "排队",
    description: "等上轮结束后继续",
  },
  {
    value: "parallel",
    label: "并行",
    description: "仍然新建一条会话",
  },
];
