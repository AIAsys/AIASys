/**
 * Session Monitor Hook
 *
 * 加载当前会话的 monitor 列表，轮询增量 segments，支持 kill。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import type { MonitorSessionInfo, MonitorSegment, MonitorSpawnRequest } from "@/types/monitors";
import {
  listSessionMonitors,
  getMonitorSegments,
  killMonitor,
  spawnMonitor,
  deleteMonitor,
  updateMonitorMode,
} from "@/lib/api/monitors";

const POLL_INTERVAL_MS = 1500;

interface MonitorWithSegments {
  info: MonitorSessionInfo;
  segments: MonitorSegment[];
  isExpanded: boolean;
}

interface UseSessionMonitorsResult {
  monitors: MonitorWithSegments[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  toggleExpand: (monitorId: string) => void;
  doKill: (monitorId: string) => Promise<void>;
  doSpawn: (req: MonitorSpawnRequest) => Promise<void>;
  doRestart: (command: string) => Promise<void>;
  doDelete: (monitorId: string) => Promise<void>;
  doUpdateMode: (monitorId: string, mode: "notify" | "silent") => Promise<void>;
}

export function useSessionMonitors(
  userId: string | undefined,
  sessionId: string | undefined,
): UseSessionMonitorsResult {
  const [monitors, setMonitors] = useState<MonitorWithSegments[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const segmentIndexesRef = useRef<Map<string, number>>(new Map());
  const loadingSegmentsRef = useRef<Set<string>>(new Set());
  const monitorsRef = useRef(monitors);
  monitorsRef.current = monitors;

  const loadList = useCallback(async (silent = false) => {
    if (!userId || !sessionId) return;
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await listSessionMonitors(userId, sessionId);
      setMonitors((prev) => {
        const prevMap = new Map(prev.map((p) => [p.info.id, p]));
        const next: MonitorWithSegments[] = data.monitors.map((info) => {
          const existing = prevMap.get(info.id);
          return existing
            ? { ...existing, info }
            : { info, segments: [], isExpanded: false };
        });
        return next;
      });
      // 初始化 segment index 追踪
      data.monitors.forEach((m) => {
        if (!segmentIndexesRef.current.has(m.id)) {
          segmentIndexesRef.current.set(m.id, 0);
        }
      });
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      if (!silent) setLoading(false);
    }
  }, [userId, sessionId]);

  const pollSegments = useCallback(async () => {
    if (!userId || !sessionId) return;
    const currentMonitors = monitorsRef.current;
    for (const monitor of currentMonitors) {
      if (monitor.info.status !== "running") continue;
      const mid = monitor.info.id;
      if (loadingSegmentsRef.current.has(mid)) continue;
      loadingSegmentsRef.current.add(mid);
      const sinceIndex = segmentIndexesRef.current.get(mid) ?? 0;
      try {
        const data = await getMonitorSegments(
          userId,
          sessionId,
          mid,
          sinceIndex,
        );
        if (data.segments.length > 0) {
          setMonitors((prev) =>
            prev.map((m) =>
              m.info.id === mid
                ? { ...m, segments: [...m.segments, ...data.segments] }
                : m,
            ),
          );
          const maxIndex = Math.max(
            ...data.segments.map((s) => s.index),
            sinceIndex,
          );
          segmentIndexesRef.current.set(mid, maxIndex + 1);
        }
      } catch (e) {
        console.warn("轮询 monitor segments 失败", e);
      } finally {
        loadingSegmentsRef.current.delete(mid);
      }
    }
  }, [userId, sessionId]);

  useEffect(() => {
    loadList();
  }, [loadList]);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
    }
    intervalRef.current = setInterval(() => {
      // 静默刷新列表（捕获 LLM 通过 tool 调用启动的新 monitor）
      void loadList(true);
      // 轮询 running monitor 的增量 segments
      void pollSegments();
    }, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [pollSegments, loadList]);

  const loadSegmentsFor = useCallback(
    async (monitorId: string) => {
      if (!userId || !sessionId) return;
      if (loadingSegmentsRef.current.has(monitorId)) return;
      loadingSegmentsRef.current.add(monitorId);
      const sinceIndex = segmentIndexesRef.current.get(monitorId) ?? 0;
      try {
        const data = await getMonitorSegments(
          userId,
          sessionId,
          monitorId,
          sinceIndex,
        );
        if (data.segments.length > 0) {
          setMonitors((prev) =>
            prev.map((m) =>
              m.info.id === monitorId
                ? { ...m, segments: [...m.segments, ...data.segments] }
                : m,
            ),
          );
          const maxIndex = Math.max(
            ...data.segments.map((s) => s.index),
            sinceIndex,
          );
          segmentIndexesRef.current.set(monitorId, maxIndex + 1);
        }
      } catch (e) {
        console.warn("加载 monitor segments 失败", e);
      } finally {
        loadingSegmentsRef.current.delete(monitorId);
      }
    },
    [userId, sessionId],
  );

  const toggleExpand = useCallback(
    (monitorId: string) => {
      let shouldLoad = false;
      setMonitors((prev) => {
        const target = prev.find((m) => m.info.id === monitorId);
        if (target && !target.isExpanded && target.segments.length === 0) {
          shouldLoad = true;
        }
        return prev.map((m) =>
          m.info.id === monitorId ? { ...m, isExpanded: !m.isExpanded } : m,
        );
      });
      if (shouldLoad) {
        void loadSegmentsFor(monitorId);
      }
    },
    [loadSegmentsFor],
  );

  const doKill = useCallback(
    async (monitorId: string) => {
      if (!userId || !sessionId) return;
      try {
        await killMonitor(userId, sessionId, monitorId);
        await loadList(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : "终止失败");
      }
    },
    [userId, sessionId, loadList],
  );

  const doSpawn = useCallback(
    async (req: MonitorSpawnRequest) => {
      if (!userId || !sessionId) return;
      try {
        await spawnMonitor(userId, sessionId, req);
        await loadList(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : "启动失败");
      }
    },
    [userId, sessionId, loadList],
  );

  const doRestart = useCallback(
    async (command: string) => {
      if (!userId || !sessionId) return;
      try {
        await spawnMonitor(userId, sessionId, { command });
        await loadList(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : "重启失败");
      }
    },
    [userId, sessionId, loadList],
  );

  const doDelete = useCallback(
    async (monitorId: string) => {
      if (!userId || !sessionId) return;
      try {
        await deleteMonitor(userId, sessionId, monitorId);
        // 从本地状态中移除
        setMonitors((prev) => prev.filter((m) => m.info.id !== monitorId));
        segmentIndexesRef.current.delete(monitorId);
      } catch (e) {
        setError(e instanceof Error ? e.message : "删除失败");
      }
    },
    [userId, sessionId],
  );

  const doUpdateMode = useCallback(
    async (monitorId: string, mode: "notify" | "silent") => {
      if (!userId || !sessionId) return;
      try {
        await updateMonitorMode(userId, sessionId, monitorId, mode);
        setMonitors((prev) =>
          prev.map((m) =>
            m.info.id === monitorId ? { ...m, info: { ...m.info, mode } } : m,
          ),
        );
      } catch (e) {
        setError(e instanceof Error ? e.message : "修改模式失败");
      }
    },
    [userId, sessionId],
  );

  return {
    monitors,
    loading,
    error,
    refresh: loadList,
    toggleExpand,
    doKill,
    doSpawn,
    doRestart,
    doDelete,
    doUpdateMode,
  };
}
