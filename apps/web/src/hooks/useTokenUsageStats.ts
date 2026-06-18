import { useCallback, useEffect, useRef, useState } from "react";
import { getCurrentUserId } from "@/config/api";
import { getSessionTokenStats } from "@/lib/api/sessionBudget";
import type { TokenStats } from "@/types/sessionBudget";

interface UseTokenUsageStatsOptions {
  /** 当前会话 ID，切换会话时重新拉取 */
  sessionId?: string | null;
  /** 外部刷新信号，变化时立即拉取（如 token_usage 事件、运行状态切换） */
  refreshSignal?: number | string;
  /** 会话是否正在运行，运行期间启用定时轮询 */
  isRunning?: boolean;
  /** 运行期轮询间隔，默认 8s */
  pollIntervalMs?: number;
}

interface UseTokenUsageStatsResult {
  stats: TokenStats | null;
  /** 手动触发一次拉取（不依赖信号） */
  loadStats: () => Promise<void>;
}

/**
 * 会话级 token 用量拉取与轮询。
 *
 * - 会话切换 / refreshSignal 变化时立即拉取
 * - 运行期间按 pollIntervalMs 定时轮询，保持用量实时刷新
 * - 通过 requestSeq 丢弃过期响应，避免竞态覆盖
 *
 * 注意：refreshSignal 应只携带语义化触发器（会话 ID、运行状态、token_usage 事件序号），
 * 不要把 chatItems.length 这类高频变化值塞进信号，否则会在流式输出期间产生大量冗余请求。
 */
export function useTokenUsageStats({
  sessionId,
  refreshSignal,
  isRunning = false,
  pollIntervalMs = 8000,
}: UseTokenUsageStatsOptions): UseTokenUsageStatsResult {
  const [stats, setStats] = useState<TokenStats | null>(null);
  const requestSeqRef = useRef(0);
  const userId = getCurrentUserId();

  const loadStats = useCallback(async () => {
    const requestSeq = requestSeqRef.current + 1;
    requestSeqRef.current = requestSeq;
    if (!userId || !sessionId) {
      setStats(null);
      return;
    }
    try {
      const data = await getSessionTokenStats(userId, sessionId);
      // 丢弃过期响应，避免旧请求覆盖新数据
      if (requestSeqRef.current !== requestSeq) return;
      setStats(data);
    } catch {
      // 保持已有 stats，避免用量条突然消失
    }
  }, [userId, sessionId]);

  // 会话切换 / 外部刷新信号变化 → 立即拉取
  useEffect(() => {
    void loadStats();
  }, [loadStats, refreshSignal]);

  // 运行期间定时轮询，停止时由 refreshSignal（含 isRunning）触发最终刷新
  useEffect(() => {
    if (!userId || !sessionId || !isRunning) return;
    const timer = window.setInterval(() => {
      void loadStats();
    }, pollIntervalMs);
    return () => {
      window.clearInterval(timer);
    };
  }, [userId, sessionId, isRunning, pollIntervalMs, loadStats]);

  return { stats, loadStats };
}
