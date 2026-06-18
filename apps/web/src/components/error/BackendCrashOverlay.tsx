import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { useBackendHealth } from "@/hooks/useBackendHealth";
import { backendHealth } from "@/lib/backendHealth";

/**
 * 后端不可达时的全屏遮罩。
 *
 * 两种触发来源：
 * - 桌面版 IPC（`backend:crashed` / `backend:ready`）：后端崩溃自动重启场景
 * - Web 版被动健康检测（useBackendHealth）：API 连续网络级失败时触发
 *
 * 桌面版 IPC 优先级更高（信息更明确："正在重启"）。
 */
export function BackendCrashOverlay() {
  const [desktopCrashed, setDesktopCrashed] = useState(false);
  const { healthy } = useBackendHealth();

  useEffect(() => {
    const desktop = window.__AIASYS_DESKTOP__;
    if (!desktop) return;

    desktop.onBackendCrashed?.(() => setDesktopCrashed(true));
    desktop.onBackendReady?.(() => {
      setDesktopCrashed(false);
      // 桌面版报告后端就绪，同步健康状态避免闪烁
      backendHealth.recordSuccess();
    });
  }, []);

  if (desktopCrashed) {
    return (
      <div
        role="alert"
        aria-live="assertive"
        className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm"
      >
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-base font-medium text-foreground">
            后端服务正在重启...
          </p>
        </div>
      </div>
    );
  }

  if (!healthy) {
    return (
      <div
        role="alert"
        aria-live="assertive"
        className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm"
      >
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          <p className="text-base font-medium text-foreground">
            无法连接到后端服务
          </p>
          <p className="text-sm text-muted-foreground">
            正在尝试重新连接...
          </p>
        </div>
      </div>
    );
  }

  return null;
}
