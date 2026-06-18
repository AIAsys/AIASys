import { useEffect, useState } from "react";

import { backendHealth } from "@/lib/backendHealth";

/**
 * 订阅后端健康状态。
 *
 * 返回当前后端是否可达。初次渲染时读取单例的同步状态，避免闪烁。
 */
export function useBackendHealth(): { healthy: boolean } {
  const [healthy, setHealthy] = useState(backendHealth.isHealthy);

  useEffect(() => {
    const unsubscribe = backendHealth.subscribe(setHealthy);
    return unsubscribe;
  }, []);

  return { healthy };
}
