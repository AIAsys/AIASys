import { useCallback, useEffect, useRef } from "react";

/**
 * 安全定时器 Hook。
 *
 * 在事件处理器、useCallback 等非 useEffect 场景中使用 setTimeout 时，
 * 如果组件在定时器触发前卸载，回调仍会执行并尝试更新已卸载组件的状态，
 * 导致 "setState on unmounted component" 警告和潜在的内存泄漏。
 *
 * 本 Hook 将所有通过 setSafeTimeout 创建的定时器 ID 收集到 ref 中，
 * 在组件卸载时统一清除，杜绝过期回调执行。
 *
 * @returns setSafeTimeout — 稳定引用的函数，签名与 window.setTimeout 一致，
 *                           但返回 void（不需要手动 clear）
 */
export function useSafeTimeout(): (
  callback: () => void,
  delay: number,
) => void {
  const timersRef = useRef<Set<ReturnType<typeof setTimeout>>>(
    new Set(),
  );

  const setSafeTimeout = useCallback(
    (callback: () => void, delay: number) => {
      const id = setTimeout(() => {
        timersRef.current.delete(id);
        callback();
      }, delay);
      timersRef.current.add(id);
    },
    [],
  );

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      timers.forEach((id) => clearTimeout(id));
      timers.clear();
    };
  }, []);

  return setSafeTimeout;
}
