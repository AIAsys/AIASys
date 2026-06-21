import { useCallback, useEffect, useRef } from "react";

/**
 * 可见性感知的轮询 Hook。
 *
 * 核心能力：
 * - 文档隐藏时自动暂停轮询，避免后台标签页白白消耗后端资源
 * - 文档重新可见时立即触发一次刷新，保证用户回来时看到最新数据
 * - 请求重叠保护：上一次回调还没结束就跳过本轮，避免并发堆积
 * - 卸载时清理定时器，拒绝已卸载组件的过期状态更新
 *
 * @param callback 每次轮询执行的异步回调。应该是稳定引用（useCallback）
 * @param intervalMs 轮询间隔，毫秒
 * @param enabled 是否启用轮询，默认 true。设为 false 时完全停止
 */
export function usePolling(
  callback: () => Promise<void> | void,
  intervalMs: number,
  enabled = true,
): void {
  // 用 ref 持有最新 callback，避免 interval 因 callback 变化而重建
  const callbackRef = useRef(callback);
  useEffect(() => {
    callbackRef.current = callback;
  }, [callback]);

  // 标记是否有请求正在进行，防止重叠
  const inFlightRef = useRef(false);

  // 标记组件是否已卸载，拒绝过期更新
  const mountedRef = useRef(true);

  const tick = useCallback(async () => {
    if (inFlightRef.current) {
      return;
    }
    inFlightRef.current = true;
    try {
      await callbackRef.current();
    } catch {
      // 轮询回调应自行处理错误，这里兜底防止 inFlight 卡住
    } finally {
      inFlightRef.current = false;
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    // 首次挂载立即执行一次
    void tick();

    const timer = window.setInterval(() => {
      // 文档不可见时跳过轮询，节省资源
      if (document.visibilityState === "hidden") {
        return;
      }
      void tick();
    }, intervalMs);

    // 标签页重新可见时立即刷新一次
    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible" && mountedRef.current) {
        void tick();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, [enabled, intervalMs, tick]);
}
