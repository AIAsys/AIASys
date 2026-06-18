import { useEffect, useState } from "react";
import { useSafeTimeout } from "@/hooks/useSafeTimeout";

/**
 * 全局网络状态横幅。
 *
 * 离线时在顶部悬浮一条警告横幅，恢复后短暂提示"网络已恢复"。
 * 不影响页面布局（fixed 定位），z-index 低于 ErrorBoundary 全屏遮罩。
 */
export default function NetworkStatusOverlay() {
  const [isOnline, setIsOnline] = useState(
    typeof navigator !== "undefined" ? navigator.onLine : true,
  );
  const [showRestored, setShowRestored] = useState(false);
  const setSafeTimeout = useSafeTimeout();

  useEffect(() => {
    const handleOffline = () => {
      setShowRestored(false);
      setIsOnline(false);
    };
    const handleOnline = () => {
      setIsOnline(true);
      setShowRestored(true);
      setSafeTimeout(() => setShowRestored(false), 2000);
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, [setSafeTimeout]);

  if (isOnline && !showRestored) {
    return null;
  }

  if (!isOnline) {
    return (
      <div role="status" aria-live="polite" className="fixed inset-x-0 top-0 z-[90] bg-warning px-4 py-2 text-center text-sm font-medium text-on-warning-container">
        网络连接已断开，部分功能可能不可用
      </div>
    );
  }

  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 top-0 z-[90] bg-success px-4 py-2 text-center text-sm font-medium text-on-success-container">
      网络已恢复
    </div>
  );
}
