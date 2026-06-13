/**
 * useExecutionTree - Host Agent 执行树 Hook
 *
 * 管理 Host Agent 和 Sub Agents 的执行状态
 * 用于新的执行流展示（Host 双层视图 + Sub Agent 单层视图）
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { apiRequest } from "@/lib/api/httpClient";
import { eventBus, EVENTS } from "@/lib/eventBus";
import { getExecutionRecordSeed } from "@/lib/runtimeToolEvents";
import type { SessionExecutionRecord } from "@/pages/WorkspacePage/types";
import type { ExpertRoleSummary } from "@/types/expertRoles";
const EXECUTION_MATCH_WINDOW_MS = 5 * 60 * 1000;

type ExecutionDisplayStatus =
  | "idle"
  | "running"
  | "completed"
  | "failed"
  | "cancelled"
  | "queued"
  | "closed";

function normalizeExecutionStatus(status: string | null | undefined): ExecutionDisplayStatus {
  const normalized = status?.trim().toLowerCase();

  switch (normalized) {
    case "running":
    case "completed":
    case "failed":
    case "cancelled":
    case "queued":
    case "idle":
    case "closed":
      return normalized;
    case "finished":
      return "completed";
    case "interrupted":
      return "cancelled";
    case "awaiting_user":
    case "blocked":
    case "paused":
      return "running";
    default:
      return "idle";
  }
}

function normalizeExecutionTree(tree: ExecutionTree): ExecutionTree {
  return {
    ...tree,
    host: {
      ...tree.host,
      status: normalizeExecutionStatus(tree.host.status),
    },
    subagent_calls: tree.subagent_calls.map((call) => ({
      ...call,
      subagent: {
        ...call.subagent,
        id: call.subagent.agent_id || call.subagent.id,
        status: normalizeExecutionStatus(call.subagent.status),
      },
    })),
  };
}

function normalizeRecord(record: SessionExecutionRecord): SessionExecutionRecord {
  return {
    ...record,
    status: normalizeExecutionStatus(record.status),
  };
}

function parseTimeMs(value?: string | null): number | null {
  if (!value) return null;
  const ts = new Date(value).getTime();
  return Number.isNaN(ts) ? null : ts;
}

function isSameExecution(
  optimistic: SessionExecutionRecord,
  persisted: SessionExecutionRecord,
): boolean {
  if (!optimistic.code || !persisted.code) return false;
  if (optimistic.code !== persisted.code) return false;

  const optimisticMode = optimistic.runtime?.sandbox_mode || null;
  const persistedMode = persisted.runtime?.sandbox_mode || null;
  if (optimisticMode !== persistedMode) return false;

  const optimisticStart = parseTimeMs(optimistic.started_at);
  const persistedStart = parseTimeMs(persisted.started_at);
  if (optimisticStart === null || persistedStart === null) return false;

  return Math.abs(optimisticStart - persistedStart) <= EXECUTION_MATCH_WINDOW_MS;
}

function mergeExecutionRecords(
  current: SessionExecutionRecord[],
  incoming: SessionExecutionRecord[],
): SessionExecutionRecord[] {
  const normalizedIncoming = incoming.map(normalizeRecord);
  if (normalizedIncoming.length === 0) {
    return current;
  }

  const merged = new Map<string, SessionExecutionRecord>();
  normalizedIncoming.forEach((record) => {
    merged.set(record.record_id, record);
  });

  current.forEach((record) => {
    if (merged.has(record.record_id)) {
      return;
    }

    const matchedPersisted = normalizedIncoming.some((incomingRecord) =>
      isSameExecution(record, incomingRecord),
    );
    if (matchedPersisted) {
      return;
    }

    merged.set(record.record_id, normalizeRecord(record));
  });

  return Array.from(merged.values()).sort((a, b) => {
    const seqA = typeof a.sequence === "number" ? a.sequence : 0;
    const seqB = typeof b.sequence === "number" ? b.sequence : 0;
    if (seqA !== seqB) return seqA - seqB;

    const timeA = parseTimeMs(a.started_at) ?? 0;
    const timeB = parseTimeMs(b.started_at) ?? 0;
    return timeA - timeB;
  });
}

// Host Agent 状态
export interface HostStatus {
  status: ExecutionDisplayStatus;
  current_step: number;
  total_steps: number;
  session_id?: string;
  workspace_id?: string | null;
  bound_host_session_id?: string | null;
}

export interface SubAgentOwnership {
  host_session_id: string;
  parent_tool_call_id?: string | null;
  agent_id: string;
  subagent_type: string;
  bound_host_session_id?: string | null;
}

// Sub Agent 执行摘要（用于概览）
export interface SubAgentSummary {
  id: string;
  agent_id?: string;
  name: string;
  status: ExecutionDisplayStatus;
  description: string;
  subagent_type?: string | null;
  host_session_id?: string | null;
  bound_host_session_id?: string | null;
  parent_tool_call_id?: string | null;
  parent_agent_id?: string | null;
  agent_path?: string | null;
  depth?: number | null;
  nickname?: string | null;
  ownership?: SubAgentOwnership;
  workspace_id?: string | null;
  node_role?: string | null;
  hosting_controller?: boolean;
  role_summary?: ExpertRoleSummary | null;
  progress: {
    current_step: number;
    total_steps: number;
    tool_calls: number;
  };
  duration_ms: number;
  created_at: string;
  updated_at: string;
  triggered_by_step?: number;
}

// Sub Agent 调用（包含触发信息）
export interface SubAgentCall {
  tool_call_id: string;
  parent_tool_call_id?: string | null;
  step_number: number;
  subagent: SubAgentSummary;
}

// 执行树
export interface ExecutionTree {
  host: HostStatus;
  subagent_calls: SubAgentCall[];
}

// 执行事件
export interface ExecutionEvent {
  type: string;
  timestamp?: number;
  [key: string]: unknown;
}

// Sub Agent 完整详情
export interface SubAgentDetail {
  id: string;
  agent_id?: string;
  name: string;
  status: ExecutionDisplayStatus;
  description: string;
  subagent_type?: string | null;
  host_session_id?: string | null;
  bound_host_session_id?: string | null;
  parent_tool_call_id?: string | null;
  parent_agent_id?: string | null;
  agent_path?: string | null;
  depth?: number | null;
  nickname?: string | null;
  ownership?: SubAgentOwnership;
  workspace_id?: string | null;
  node_role?: string | null;
  hosting_controller?: boolean;
  role_summary?: ExpertRoleSummary | null;
  duration_ms?: number;
  created_at?: string | null;
  updated_at?: string | null;
  meta: Record<string, unknown>;
  events: ExecutionEvent[];
  context: unknown[];
  output_files: Array<{
    name: string;
    path: string;
    size: number;
    modified_at: string;
  }>;
}

// Hook 返回类型
export interface UseExecutionTreeReturn {
  // 数据
  executionTree: ExecutionTree | null;
  selectedSubAgent: SubAgentDetail | null;
  codeExecutionRecords: SessionExecutionRecord[];

  // 加载状态
  isLoadingTree: boolean;
  isLoadingSubAgent: boolean;
  isLoadingCodeRecords: boolean;
  error: string | null;

  // 操作
  refreshTree: () => Promise<void>;
  refreshCodeExecutionRecords: () => Promise<void>;
  selectSubAgent: (agentId: string | null) => Promise<void>;
  stopSubAgent: (agentId: string) => Promise<boolean>;
  retrySubAgent: (agentId: string) => Promise<boolean>;

  // 实时更新
  onSubAgentEvent: (event: unknown) => void;
  onAgentSubAgentEvent: (event: unknown) => void;
  onCodeExecutionEvent: (event: unknown) => void;
}

export interface UseExecutionTreeOptions {
  enabled?: boolean;
  loadCodeExecutionRecords?: boolean;
}

export function useExecutionTree(
  userId: string | undefined,
  sessionId: string | undefined,
  options: UseExecutionTreeOptions = {},
): UseExecutionTreeReturn {
  const {
    enabled = true,
    loadCodeExecutionRecords = true,
  } = options;
  // 数据状态
  const [executionTree, setExecutionTree] = useState<ExecutionTree | null>(null);
  const [selectedSubAgent, setSelectedSubAgent] = useState<SubAgentDetail | null>(null);
  const [codeExecutionRecords, setCodeExecutionRecords] = useState<SessionExecutionRecord[]>([]);

  // 加载状态
  const [isLoadingTree, setIsLoadingTree] = useState(false);
  const [isLoadingSubAgent, setIsLoadingSubAgent] = useState(false);
  const [isLoadingCodeRecords, setIsLoadingCodeRecords] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 当前选中的 Sub Agent ID（用于重新加载）
  const selectedAgentIdRef = useRef<string | null>(null);

  // 分离 tree 刷新与全量刷新，避免流式阶段频繁整树抖动
  const pendingTreeRefreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingFullRefreshRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 流活跃标记：防止 API 返回的 idle 覆盖乐观更新的 running
  const streamActiveRef = useRef(false);

  // 数据 ref：用于在 refresh 函数中判断是否为首次加载，避免 setState 嵌套
  const executionTreeRef = useRef<ExecutionTree | null>(null);
  const codeRecordsLoadedRef = useRef(false);

  // 清理函数
  useEffect(() => {
    return () => {
      if (pendingTreeRefreshRef.current) clearTimeout(pendingTreeRefreshRef.current);
      if (pendingFullRefreshRef.current) clearTimeout(pendingFullRefreshRef.current);
    };
  }, []);

  // session 切换时重置所有状态（包括 loading 标志，防止前一个 session 的 loading 残留）
  useEffect(() => {
    executionTreeRef.current = null;
    codeRecordsLoadedRef.current = false;
    streamActiveRef.current = false;
    if (pendingTreeRefreshRef.current) {
      clearTimeout(pendingTreeRefreshRef.current);
      pendingTreeRefreshRef.current = null;
    }
    if (pendingFullRefreshRef.current) {
      clearTimeout(pendingFullRefreshRef.current);
      pendingFullRefreshRef.current = null;
    }
    setExecutionTree(null);
    setCodeExecutionRecords([]);
    setSelectedSubAgent(null);
    setError(null);
    setIsLoadingTree(false);
    setIsLoadingCodeRecords(false);
    setIsLoadingSubAgent(false);
  }, [userId, sessionId]);

  // 加载执行树（已有数据时静默刷新，不触发 loading 状态）
  const isRefreshingTreeRef = useRef(false);
  const refreshTree = useCallback(async () => {
    if (!enabled || !userId || !sessionId) return;
    if (isRefreshingTreeRef.current) return; // 去重：防止定时刷新与手动刷新冲突

    isRefreshingTreeRef.current = true;
    // 只有首次加载时才显示 loading spinner
    if (!executionTreeRef.current) setIsLoadingTree(true);
    setError(null);

    try {
      const data = await apiRequest<ExecutionTree>(
        `/api/sessions/${userId}/${sessionId}/execution-tree`,
      );
      const normalized = normalizeExecutionTree(data);
      // 流活跃期间，API 返回 idle 时保护乐观更新的 running 状态
      const result = streamActiveRef.current && normalized.host.status === "idle"
        ? { ...normalized, host: { ...normalized.host, status: "running" as ExecutionDisplayStatus } }
        : normalized;
      executionTreeRef.current = result;
      setExecutionTree(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
      console.error("加载执行树失败:", err);
    } finally {
      isRefreshingTreeRef.current = false;
      setIsLoadingTree(false);
    }
  }, [enabled, userId, sessionId]);

  // 加载代码执行记录（已有数据时静默刷新）
  const refreshCodeExecutionRecords = useCallback(async () => {
    if (!enabled || !loadCodeExecutionRecords || !userId || !sessionId) {
      return;
    }

    if (!codeRecordsLoadedRef.current) setIsLoadingCodeRecords(true);

    try {
      const data = await apiRequest<{ records?: SessionExecutionRecord[] }>(
        `/api/sessions/${userId}/${sessionId}/execution-records`,
      );
      codeRecordsLoadedRef.current = true;
      setCodeExecutionRecords((prev) => {
        return mergeExecutionRecords(prev, data.records || []);
      });
    } catch (err) {
      console.error("加载代码执行记录失败:", err);
    } finally {
      setIsLoadingCodeRecords(false);
    }
  }, [enabled, loadCodeExecutionRecords, userId, sessionId]);

  // 选择 Sub Agent（加载详情）
  const selectSubAgentAbortRef = useRef<AbortController | null>(null);
  const selectSubAgent = async (agentId: string | null) => {
    if (!enabled || !userId || !sessionId ) return;

    // 取消旧请求
    if (selectSubAgentAbortRef.current) {
      selectSubAgentAbortRef.current.abort();
    }
    const abortController = new AbortController();
    selectSubAgentAbortRef.current = abortController;

    selectedAgentIdRef.current = agentId;

    if (!agentId) {
      setSelectedSubAgent(null);
      return;
    }

    setIsLoadingSubAgent(true);

    try {
      const data = await apiRequest<SubAgentDetail>(
        `/api/sessions/${userId}/${sessionId}/subagents/${agentId}`,
        { signal: abortController.signal },
      );
      // 如果请求过程中切换了选中的节点，丢弃旧响应
      if (selectedAgentIdRef.current !== agentId) return;
      setSelectedSubAgent({
        ...data,
        id: data.agent_id || data.id,
        status: normalizeExecutionStatus(data.status),
      });
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      console.error("加载 Sub Agent 详情失败:", err);
    } finally {
      setIsLoadingSubAgent(false);
    }
  };

  // 停止 Sub Agent
  const stopSubAgent = async (agentId: string): Promise<boolean> => {
    if (!enabled || !userId || !sessionId ) return false;

    try {
      await apiRequest(
        `/api/sessions/${userId}/${sessionId}/subagents/${agentId}/stop`,
        { method: "POST" },
      );
      await Promise.all([
        refreshTree(),
        refreshCodeExecutionRecords(),
      ]);
      if (selectedAgentIdRef.current === agentId) {
        await selectSubAgent(agentId);
      }
      return true;
    } catch (err) {
      console.error("停止 Sub Agent 失败:", err);
      return false;
    }
  };

  // 重试 Sub Agent
  const retrySubAgent = async (agentId: string): Promise<boolean> => {
    if (!enabled || !userId || !sessionId ) return false;

    try {
      await apiRequest(
        `/api/sessions/${userId}/${sessionId}/subagents/${agentId}/retry`,
        { method: "POST" },
      );
      await Promise.all([
        refreshTree(),
        refreshCodeExecutionRecords(),
      ]);
      return true;
    } catch (err) {
      console.error("重试 Sub Agent 失败:", err);
      return false;
    }
  };

  // 处理实时 Sub Agent 事件（来自 SSE）
  const onSubAgentEvent = useCallback((event: unknown) => {
    if (!event || typeof event !== "object" || event === null) return;
    const e = event as Record<string, unknown>;

    const eventType = e.type as string | undefined;
    const agentId = (e.agent_id as string) || (e.subagent_name as string);

    // 更新执行树中的 Sub Agent 状态
    setExecutionTree((prev) => {
      if (!prev) return prev;

      const newTree = { ...prev };
      const callIndex = newTree.subagent_calls.findIndex(
        (call) => call.subagent.id === agentId
      );

      if (callIndex >= 0) {
        const call = { ...newTree.subagent_calls[callIndex] };
        const subagent = { ...call.subagent };

        // 根据事件类型更新状态
        if (eventType === "worker.lifecycle.changed") {
          subagent.status = normalizeExecutionStatus((e.status as string) || subagent.status);
        } else if (eventType === "step_begin") {
          subagent.progress = {
            ...subagent.progress,
            current_step: (e.step_n as number) || subagent.progress.current_step + 1,
          };
        } else if (eventType === "tool_call") {
          subagent.progress = {
            ...subagent.progress,
            tool_calls: subagent.progress.tool_calls + 1,
          };
        }

        call.subagent = subagent;
        newTree.subagent_calls[callIndex] = call;
      }

      return newTree;
    });

    // 如果当前正在查看该 Sub Agent，追加事件
    if (selectedAgentIdRef.current === agentId) {
      setSelectedSubAgent((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          status: eventType === "worker.lifecycle.changed"
            ? normalizeExecutionStatus((e.status as string) || prev.status)
            : prev.status,
          events: [...prev.events, e as ExecutionEvent],
        };
      });
    }
  }, []);

  // SubAgent 生命周期变化只需要刷新 tree，本地代码执行记录已走事件增量更新。
  const triggerTreeRefresh = useCallback((delayMs = 500) => {
    if (pendingTreeRefreshRef.current) {
      clearTimeout(pendingTreeRefreshRef.current);
    }
    pendingTreeRefreshRef.current = setTimeout(() => {
      void refreshTree();
      pendingTreeRefreshRef.current = null;
    }, delayMs);
  }, [refreshTree]);

  // 仅在流开始/结束等关键节点做一次全量对账。
  const triggerFullRefresh = useCallback((delayMs = 500) => {
    if (pendingFullRefreshRef.current) {
      clearTimeout(pendingFullRefreshRef.current);
    }
    pendingFullRefreshRef.current = setTimeout(() => {
      const tasks: Array<Promise<void>> = [refreshTree()];
      if (loadCodeExecutionRecords) {
        tasks.push(refreshCodeExecutionRecords());
      }
      void Promise.all(tasks);
      pendingFullRefreshRef.current = null;
    }, delayMs);
  }, [refreshTree, loadCodeExecutionRecords, refreshCodeExecutionRecords]);

  // 处理代码执行事件（从流中实时提取）
  const onCodeExecutionEvent = useCallback((event: unknown) => {
    if (!loadCodeExecutionRecords || !event || typeof event !== "object" || event === null) return;
    const e = event as Record<string, unknown>;
    
    const eventType = e.type as string | undefined;
    
    // 处理 Host 或 SubAgent 的代码执行事件
    if (eventType === "subagent_event" || eventType === "tool_call" || eventType === "tool_result") {
      const payload = (e.payload as Record<string, unknown>) || e;
      const payloadType = payload.type as string | undefined;
      
      // 工具调用开始 - 创建执行记录
      if (payloadType === "subagent_tool_call" || eventType === "tool_call") {
        const args = (payload.arguments || payload.tool_params || {}) as Record<string, unknown>;
        const seed = getExecutionRecordSeed(payload.tool_name as string, args);
        if (!seed) return;

        setCodeExecutionRecords((prev) => {
          const recordId = (payload.tool_call_id as string) || `exec-${Date.now()}`;
          if (prev.some((record) => record.record_id === recordId)) {
            return prev;
          }

          const newRecord: SessionExecutionRecord = {
            record_id: recordId,
            session_id: sessionId || "",
            sequence: prev.length + 1,
            status: "running",
            language: seed.language,
            code: seed.code,
            started_at: new Date().toISOString(),
            finished_at: "",
            runtime: {
              sandbox_mode: "local",
              env_id: undefined,
            },
          };

          const next = [...prev, newRecord];
          return next;
        });
      }
      
      // 工具调用结果 - 更新执行记录
      if (payloadType === "subagent_tool_result" || eventType === "tool_result") {
        const toolCallId = payload.tool_call_id as string | undefined;
        const content = (payload.content as string) || "";
        const isError = (payload.is_error as boolean) || false;
        
        setCodeExecutionRecords((prev) => {
          if (!toolCallId || !prev.some((record) => record.record_id === toolCallId)) {
            return prev;
          }
          return prev.map((record) => {
            if (record.record_id === toolCallId) {
              return {
                ...record,
                status: isError ? "failed" : "completed",
                finished_at: new Date().toISOString(),
                result_preview: {
                  type: "text",
                  text: content.slice(0, 500), // 限制预览长度
                },
                error: isError ? content : undefined,
              };
            }
            return record;
          });
        });
      }
    }
  }, [loadCodeExecutionRecords, sessionId]);

  // 处理来自 Agent SSE 的 subagent_event（包含新 Sub Agent 创建事件）
  const onAgentSubAgentEvent = useCallback((event: unknown) => {
    if (!event || typeof event !== "object" || event === null) return;
    const e = event as Record<string, unknown>;

    const payload = (e.payload as Record<string, unknown>) || e;
    const eventType = payload.type as string | undefined;

    // 如果收到新 Sub Agent 的 lifecycle 事件，触发刷新
    if (eventType === "worker.lifecycle.changed" ||
        eventType === "worker.registered" ||
        eventType === "started") {
      triggerTreeRefresh();
    }

    // 处理代码执行事件
    onCodeExecutionEvent(event);

    // 转发到子组件的事件处理
    onSubAgentEvent(payload);
  }, [triggerTreeRefresh, onCodeExecutionEvent, onSubAgentEvent]);

  // 初始加载
  useEffect(() => {
    if (enabled && userId && sessionId) {
      void refreshTree();
    }
    if (enabled && loadCodeExecutionRecords && userId && sessionId) {
      void refreshCodeExecutionRecords();
    }
  }, [enabled, loadCodeExecutionRecords, userId, sessionId, refreshTree, refreshCodeExecutionRecords]);

  // 定时刷新（当 Host 正在运行时）
  // 使用 ref 避免 executionTree 变化导致频繁重建定时器
  executionTreeRef.current = executionTree;

  useEffect(() => {
    if (!enabled || !userId || !sessionId ) return;

    const hasActiveWork = Boolean(
      executionTreeRef.current &&
      (
        executionTreeRef.current.host.status === "running" ||
        executionTreeRef.current.subagent_calls.some(
          (call) => call.subagent.status === "running" || call.subagent.status === "queued"
        )
      )
    );
    if (!hasActiveWork) return;

    const interval = setInterval(() => {
      void refreshTree();
    }, 3000); // 每 3 秒刷新一次

    return () => clearInterval(interval);
  }, [enabled, userId, sessionId, refreshTree]);

  // 监听事件总线
  useEffect(() => {
    if (!enabled || !userId || !sessionId) return;

    const unsubscribeSubAgent = eventBus.on(EVENTS.SUBAGENT_EVENT, (event) => {
      if (!event || typeof event !== "object") return;
      const e = event as Record<string, unknown>;
      const eventSessionId = (e.session_id as string) || sessionId;
      if (eventSessionId === sessionId) {
        triggerTreeRefresh();
        onCodeExecutionEvent(e);
      }
    });

    const unsubscribeCodeExec = eventBus.on(EVENTS.CODE_EXECUTION_EVENT, (event) => {
      if (!loadCodeExecutionRecords) return;
      if (!event || typeof event !== "object") return;
      const e = event as Record<string, unknown>;
      const eventSessionId = (e.session_id as string) || sessionId;
      if (eventSessionId === sessionId) {
        onCodeExecutionEvent(e);
      }
    });

    const unsubscribeActivity = eventBus.on(EVENTS.EXECUTION_ACTIVITY, (event) => {
      if (!event || typeof event !== "object") return;
      const e = event as Record<string, unknown>;
      const eventSessionId = (e.session_id as string) || sessionId;
      if (eventSessionId !== sessionId) return;

      const activityType = e.type as string | undefined;

      if (activityType === "stream_start") {
        streamActiveRef.current = true;
        setExecutionTree((prev) => {
          const base = prev || {
            host: { status: "idle" as ExecutionDisplayStatus, current_step: 0, total_steps: 0 },
            subagent_calls: [],
          };
          if (base.host.status === "running") return prev;
          return { ...base, host: { ...base.host, status: "running" as ExecutionDisplayStatus } };
        });
        triggerFullRefresh(1500);
      } else if (activityType === "stream_end") {
        streamActiveRef.current = false;
        triggerFullRefresh(500);
      }
    });

    return () => {
      streamActiveRef.current = false;
      unsubscribeSubAgent();
      unsubscribeCodeExec();
      unsubscribeActivity();
    };
  }, [enabled, loadCodeExecutionRecords, userId, sessionId, onCodeExecutionEvent, triggerFullRefresh, triggerTreeRefresh]);

  return {
    executionTree,
    selectedSubAgent,
    codeExecutionRecords,
    isLoadingTree,
    isLoadingSubAgent,
    isLoadingCodeRecords,
    error,
    refreshTree,
    refreshCodeExecutionRecords,
    selectSubAgent,
    stopSubAgent,
    retrySubAgent,
    onSubAgentEvent,
    onAgentSubAgentEvent,
    onCodeExecutionEvent,
  };
}
