import type { SessionExecutionRecord, SessionHistoryMessage } from "../../types";

export function parseIsoTimestamp(value?: string | null): number {
  if (!value) return Number.NEGATIVE_INFINITY;
  const parsed = new Date(value).getTime();
  return Number.isFinite(parsed) ? parsed : Number.NEGATIVE_INFINITY;
}

export function getExecutionRecordTime(record: SessionExecutionRecord): number {
  return parseIsoTimestamp(record.finished_at || record.started_at);
}

export function formatExecutionShortTime(value?: string | null): string {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";

  const now = new Date();
  const isSameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  return isSameDay
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : date.toLocaleString([], {
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export function formatExecutionFullTime(value?: string | null): string {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";

  return date.toLocaleString([], {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatExecutionDuration(
  startedAt?: string | null,
  finishedAt?: string | null,
): string | null {
  const durationMs = parseIsoTimestamp(finishedAt) - parseIsoTimestamp(startedAt);
  if (!Number.isFinite(durationMs) || durationMs < 0) return null;
  if (durationMs < 1000) return "<1s";

  const totalSeconds = Math.round(durationMs / 1000);
  if (totalSeconds < 60) return `${totalSeconds}s`;

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes < 60) return seconds > 0 ? `${minutes}m ${seconds}s` : `${minutes}m`;

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes > 0 ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

export function formatExecutionStatusLabel(status?: string | null): string {
  switch (status) {
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "running":
      return "进行中";
    case "cancelled":
      return "已取消";
    case "blocked":
      return "已阻断";
    default:
      return status || "未知状态";
  }
}

export function formatExecutionSandboxLabel(value?: string | null): string {
  if (!value || value === "unknown") return "未知";
  if (value === "local") return "本地执行";
  return value;
}

export function formatExecutionEnvLabel(value?: string | null): string {
  if (!value || value === "no-env") return "未设置";
  return value;
}

export function getConversationTextContent(
  content?: SessionHistoryMessage["display_content"] | SessionHistoryMessage["content"],
): string {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content.map((item) => item.text || item.think || "").join("").trim();
  }
  return "";
}

export function formatConversationRoleLabel(role: SessionHistoryMessage["role"]): string {
  switch (role) {
    case "user":
      return "用户";
    case "assistant":
      return "AI";
    case "tool":
      return "工具";
    case "system":
      return "维护";
    default:
      return role;
  }
}

export function getConversationRoleBadgeClass(role: SessionHistoryMessage["role"]): string {
  switch (role) {
    case "user":
      return "border-border bg-muted text-foreground";
    case "assistant":
      return "border-border bg-muted text-foreground";
    case "tool":
      return "border-border bg-muted text-foreground";
    case "system":
      return "border-border bg-muted text-foreground";
    default:
      return "border-border/60 bg-muted/40 text-muted-foreground";
  }
}
