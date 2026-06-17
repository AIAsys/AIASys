import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

/**
 * 后端服务崩溃重启时的全屏遮罩。
 *
 * 监听桌面版 IPC 事件：
 * - `backend:crashed` → 显示遮罩
 * - `backend:ready` → 隐藏遮罩
 *
 * 仅在 Electron 桌面环境下生效，Web 版无此事件源，组件始终不显示。
 */
export function BackendCrashOverlay() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const desktop = window.__AIASYS_DESKTOP__;
    if (!desktop) return;

    desktop.onBackendCrashed?.(() => setVisible(true));
    desktop.onBackendReady?.(() => setVisible(false));
  }, []);

  if (!visible) return null;

  return (
    <div role="alert" aria-live="assertive" className="fixed inset-0 z-[100] flex items-center justify-center bg-background/80 backdrop-blur-sm">
      <div className="flex flex-col items-center gap-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <p className="text-base font-medium text-foreground">
          后端服务正在重启...
        </p>
      </div>
    </div>
  );
}
