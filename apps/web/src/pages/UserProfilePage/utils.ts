import type { AuthUser } from "./types";

const AVATAR_COLORS = [
  "bg-error",
  "bg-warning",
  "bg-warning",
  "bg-success",
  "bg-success",
  "bg-success",
  "bg-info",
  "bg-info",
  "bg-tertiary",
  "bg-tertiary",
  "bg-info",
  "bg-info",
  "bg-info",
  "bg-info",
  "bg-error",
];

export function getDisplayChar(user: AuthUser | null): string {
  if (!user) return "?";
  const name = user.nickname || user.username;
  return name.charAt(0).toUpperCase();
}

export function getAvatarColor(user: AuthUser | null): string {
  if (!user) return "bg-primary";
  const index = user.id.charCodeAt(0) % AVATAR_COLORS.length;
  return AVATAR_COLORS[index];
}

export function formatCreatedAt(value?: string): string {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN");
}
