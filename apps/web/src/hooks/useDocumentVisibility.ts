/**
 * 页面可见性 Hook
 *
 * 跟踪 document.visibilityState，当标签页切到后台时返回 false。
 * 用于让轮询/定时器在页面不可见时暂停，避免：
 * 1. 后台标签页持续发起不必要的网络请求
 * 2. 浏览器对后台定时器的节流导致心跳检测等时间敏感逻辑误判
 */
import { useEffect, useState } from "react";

export function useDocumentVisibility(): boolean {
  const [isVisible, setIsVisible] = useState(
    typeof document !== "undefined"
      ? document.visibilityState === "visible"
      : true,
  );

  useEffect(() => {
    const handleChange = () => {
      setIsVisible(document.visibilityState === "visible");
    };
    document.addEventListener("visibilitychange", handleChange);
    return () => {
      document.removeEventListener("visibilitychange", handleChange);
    };
  }, []);

  return isVisible;
}
