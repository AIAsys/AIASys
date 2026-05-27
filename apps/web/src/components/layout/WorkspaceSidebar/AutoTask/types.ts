import type { Dispatch, SetStateAction } from "react";

export type AutoTaskDraft = {
  title: string;
  prompt: string;
  triggerType: "interval" | "cron" | "once" | "continuous";
  triggerValue: string;
  enabled: boolean;
  modelId: string;
  overlapPolicy: "skip" | "queue" | "parallel";
  bindSessionId: string;
  sessionStrategy: "bind_session" | "new_each_time";
  continuationPrompt: string;
  maxContinuations: number;
  // v0.4.0 新增
  taskCategory: "scheduled" | "continuous";
  firstRunPolicy: "immediate" | "next_scheduled";
  stopOnConsecutiveErrors: number;
  stopOnSignal: boolean;
};

export type AutoTaskSessionOption = {
  sessionId: string;
  title: string;
  isCurrent?: boolean;
  updatedAt?: string | null;
  messageCount?: number | null;
};

export type AutoTaskTemplate = {
  id: string;
  name: string;
  summary: string;
  title: string;
  prompt: string;
  triggerType: AutoTaskDraft["triggerType"];
  triggerValue: string;
};

export interface AutoTaskFeedback {
  tone: "success" | "error";
  message: string;
}

export interface AutoTaskSummary {
  total: number;
  active: number;
  idle: number;
  error: number;
}

export type SetAutoTaskDraft = Dispatch<SetStateAction<AutoTaskDraft>>;
