import { useState, useEffect, useCallback } from "react";

/**
 * useState 的 localStorage 持久化版本。
 * 初始化时从 localStorage 读取，变化时写回。
 */
export function useLocalStorageState<T>(
  key: string,
  defaultValue: T,
): [T, (value: T | ((prev: T) => T)) => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const stored = localStorage.getItem(key);
      if (stored !== null) {
        return JSON.parse(stored) as T;
      }
    } catch {
      // localStorage 不可用或数据损坏，fallback 到默认值
    }
    return defaultValue;
  });

  useEffect(() => {
    try {
      localStorage.setItem(key, JSON.stringify(state));
    } catch {
      // 写入失败（quota 满等），静默忽略
    }
  }, [key, state]);

  const setValue = useCallback(
    (value: T | ((prev: T) => T)) => {
      setState(value);
    },
    [],
  );

  return [state, setValue];
}