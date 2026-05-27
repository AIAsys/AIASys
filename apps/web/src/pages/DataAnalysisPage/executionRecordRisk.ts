import type { SessionExecutionRecord } from "./types";

export type ExecutionRiskLevelValue = "low" | "medium" | "high";

const EXECUTION_RISK_LABELS: Record<ExecutionRiskLevelValue, string> = {
  low: "执行风险低",
  medium: "副作用风险",
  high: "高副作用风险",
};

const EXECUTION_RISK_BADGE_CLASSES: Record<ExecutionRiskLevelValue, string> = {
  low: "border-border/60 bg-background text-muted-foreground",
  medium: "border-border bg-muted/60 text-foreground",
  high: "border-foreground bg-foreground text-background",
};

const EXECUTION_RISK_TAG_LABELS: Record<string, string> = {
  network_write: "外部写请求",
  database_write: "数据库写入",
  subprocess: "外部命令",
  package_install: "依赖变更",
  destructive_fs: "删除/移动文件",
  file_write: "写文件",
  directory_create: "创建目录",
};

export function getExecutionRiskLevel(
  record?: Pick<SessionExecutionRecord, "replay_risk"> | null,
): ExecutionRiskLevelValue {
  return record?.replay_risk?.level || "low";
}

export function getExecutionRiskLabelByLevel(
  level: ExecutionRiskLevelValue,
): string {
  return EXECUTION_RISK_LABELS[level];
}

export function getExecutionRiskLabel(
  record?: Pick<SessionExecutionRecord, "replay_risk"> | null,
): string {
  return getExecutionRiskLabelByLevel(getExecutionRiskLevel(record));
}

export function getExecutionRiskBadgeClassByLevel(
  level: ExecutionRiskLevelValue,
): string {
  return EXECUTION_RISK_BADGE_CLASSES[level];
}

export function getExecutionRiskBadgeClass(
  record?: Pick<SessionExecutionRecord, "replay_risk"> | null,
): string {
  return getExecutionRiskBadgeClassByLevel(getExecutionRiskLevel(record));
}

export function getExecutionRiskTagLabel(tag: string): string {
  return EXECUTION_RISK_TAG_LABELS[tag] || tag;
}
