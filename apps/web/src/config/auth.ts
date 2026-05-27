/**
 * 认证模式辅助函数
 *
 * 当前产品只保留 `local` 与 `none` 两种模式。
 */
export function getAuthMode(): "local" | "none" {
  const mode = import.meta.env.VITE_AUTH_MODE || "local";
  if (mode === "none") {
    return mode;
  }
  return "local";
}

export function isSingleUserAuthMode(): boolean {
  const authMode = getAuthMode();
  return authMode === "local" || authMode === "none";
}
