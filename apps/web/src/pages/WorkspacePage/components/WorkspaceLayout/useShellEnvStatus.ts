/**
 * useShellEnvStatus — 轻量级 Shell 环境状态 hook
 *
 * 在对话页面侧栏展示当前推荐的 Shell 类型。
 * 如果 Windows 上 fallback 到 PowerShell/CMD，显示警告样式。
 */
import { useCallback, useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/httpClient";
import { API_ENDPOINTS } from "@/config/api";

interface ShellEnvStatus {
  family: string;
  isWindows: boolean;
  needsAttention: boolean;
}

const CACHE_TTL = 60_000; // 60 seconds

let cachedResult: ShellEnvStatus | null = null;
let cacheTimestamp = 0;

export function useShellEnvStatus() {
  const [status, setStatus] = useState<ShellEnvStatus | null>(cachedResult);

  const fetch = useCallback(async (force = false) => {
    if (!force && cachedResult && Date.now() - cacheTimestamp < CACHE_TTL) {
      setStatus(cachedResult);
      return;
    }
    try {
      const res = await apiRequest<{
        recommended_family: string;
        is_windows: boolean;
      }>(API_ENDPOINTS.SHELL_ENVIRONMENT);
      const family = res.recommended_family;
      const result: ShellEnvStatus = {
        family,
        isWindows: res.is_windows,
        needsAttention:
          res.is_windows && (family === "powershell" || family === "cmd"),
      };
      cachedResult = result;
      cacheTimestamp = Date.now();
      setStatus(result);
    } catch {
      // Silently fail — this is a non-critical indicator
    }
  }, []);

  useEffect(() => {
    void fetch();
  }, [fetch]);

  return { status, refresh: () => fetch(true) };
}

const FAMILY_LABELS: Record<string, string> = {
  posix: "Bash",
  wsl: "WSL",
  busybox: "busybox",
  powershell: "PowerShell",
  cmd: "CMD",
};

export function shellFamilyLabel(family: string): string {
  return FAMILY_LABELS[family] ?? family;
}
