import { useCallback, useEffect, useRef, useState } from "react";

export type TerminalStatus = "idle" | "connecting" | "connected" | "disconnected" | "error" | "attaching";

export interface TerminalState {
  status: TerminalStatus;
  error: string | null;
  terminalId: string | null;
  pid: number | null;
}

export interface UseTerminalOptions {
  userId: string;
  sessionId: string;
  /** 外部指定的 terminalId，用于 attach 已有 PTY（PaneRenderer 传入） */
  terminalId?: string;
  /** 初始连接模式：'attach' 优先尝试 attach 已有 PTY，'spawn' 直接创建新 PTY（默认） */
  initialMode?: "spawn" | "attach";
  onOutput?: (data: string) => void;
  onSpawned?: (terminalId: string, pid: number) => void;
  onExited?: (terminalId: string, exitCode: number) => void;
  onError?: (terminalId: string, message: string) => void;
  onAttached?: (terminalId: string, pid: number) => void;
}

export interface UseTerminalReturn {
  state: TerminalState;
  spawn: (rows: number, cols: number, cwd?: string) => void;
  input: (data: string) => void;
  resize: (rows: number, cols: number) => void;
  kill: () => void;
  reconnect: () => void;
}

function buildWsUrl(userId: string, sessionId: string): string {
  // Desktop 运行时由主进程注入后端地址，避免前端 preview server 无法代理 WebSocket。
  // 参考 VSCode 设计：Electron 前端直接连接已知的后端服务端点，而不是依赖页面同源。
  const desktopBackend =
    (window as unknown as { __AIASYS_DESKTOP__?: { backendBaseUrl?: string } }).__AIASYS_DESKTOP__
      ?.backendBaseUrl;
  if (desktopBackend) {
    const backendUrl = new URL(desktopBackend);
    const protocol = backendUrl.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${backendUrl.host}/ws/terminal/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`;
  }

  // 构建时覆盖（例如 Docker 独立部署）
  const apiBase = (import.meta.env.VITE_API_BASE_URL || "").trim();
  if (apiBase) {
    const base = new URL(apiBase);
    const protocol = base.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${base.host}/ws/terminal/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`;
  }

  // 默认走页面同源（Vite dev proxy / nginx 同域部署）
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${protocol}//${host}/ws/terminal/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`;
}

export function useTerminal(options: UseTerminalOptions): UseTerminalReturn {
  const {
    userId,
    sessionId,
    terminalId: externalTerminalId,
    initialMode = "spawn",
    onOutput,
    onSpawned,
    onExited,
    onError,
    onAttached,
  } = options;

  const isAttachMode = initialMode === "attach";

  const [state, setState] = useState<TerminalState>({
    status: "idle",
    error: null,
    terminalId: isAttachMode ? (externalTerminalId ?? null) : null,
    pid: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const pendingSpawnRef = useRef<{ rows: number; cols: number; cwd?: string }[]>([]);
  const terminalIdRef = useRef<string | null>(isAttachMode ? (externalTerminalId ?? null) : null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 标记主动关闭（unmount / 手动 reconnect / kill），用于阻止 onclose 自动重连
  const manualCloseRef = useRef(false);
  // 标记已过期的 terminalId，防止 render 阶段重新写入 externalTerminalIdRef
  const expiredTerminalIdRef = useRef<string | null>(null);
  // 记录初始连接模式，用于 connect 时决定是否尝试 attach
  const initialModeRef = useRef(initialMode);

  // 稳定引用：userId/sessionId/externalTerminalId 变化时更新 ref
  const userIdRef = useRef(userId);
  const sessionIdRef = useRef(sessionId);
  const externalTerminalIdRef = useRef<string | undefined | null>(externalTerminalId);

  // ref 存储回调，避免 StrictMode 下 ws.onmessage 使用旧闭包
  const onOutputRef = useRef(onOutput);
  const onSpawnedRef = useRef(onSpawned);
  const onExitedRef = useRef(onExited);
  const onErrorRef = useRef(onError);
  const onAttachedRef = useRef(onAttached);

  useEffect(() => {
    initialModeRef.current = initialMode;
    userIdRef.current = userId;
    sessionIdRef.current = sessionId;

    // 只在 prop 实际变化时更新 externalTerminalIdRef，且如果该 terminalId 已过期则忽略
    if (
      externalTerminalId !== externalTerminalIdRef.current &&
      externalTerminalId !== expiredTerminalIdRef.current
    ) {
      externalTerminalIdRef.current = externalTerminalId;
    }

    onOutputRef.current = onOutput;
    onSpawnedRef.current = onSpawned;
    onExitedRef.current = onExited;
    onErrorRef.current = onError;
    onAttachedRef.current = onAttached;
  }, [
    initialMode,
    userId,
    sessionId,
    externalTerminalId,
    onOutput,
    onSpawned,
    onExited,
    onError,
    onAttached,
  ]);

  // 同步 terminalIdRef
  useEffect(() => {
    terminalIdRef.current = state.terminalId;
  }, [state.terminalId]);

  // 外部 terminalId 变化时同步（仅 attach 模式需要预设 terminalId 到 state，
  // spawn 模式保持 state.terminalId = null 以触发 TerminalPanel 调用 spawn）
  useEffect(() => {
    if (initialModeRef.current === "attach" && externalTerminalId && externalTerminalId !== terminalIdRef.current) {
      terminalIdRef.current = externalTerminalId;
      setState((prev) => ({ ...prev, terminalId: externalTerminalId }));
    }
  }, [externalTerminalId]);

  // externalTerminalId 变化时清除过期标记
  useEffect(() => {
    expiredTerminalIdRef.current = null;
  }, [externalTerminalId]);

  const connect = useCallback(() => {
    const currentUserId = userIdRef.current;
    const currentSessionId = sessionIdRef.current;
    // 仅 attach 模式尝试 attach 已有 PTY；spawn 模式直接走 spawn 路径
    const attachTarget = initialModeRef.current === "attach" ? externalTerminalIdRef.current : null;

    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    // 重置主动关闭标记：新一轮连接不再视为主动关闭
    manualCloseRef.current = false;

    setState((prev) => ({
      ...prev,
      status: attachTarget ? "attaching" : "connecting",
      error: null,
    }));

    const url = buildWsUrl(currentUserId, currentSessionId);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    // 指数退避重连：200ms → 400ms → 800ms → 1600ms → 5000ms，最多 5 次。
    // 设置前先清理已有定时器，避免多个重连定时器叠加。
    const scheduleReconnect = () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
      const MAX_RECONNECT_ATTEMPTS = 5;
      if (reconnectCountRef.current >= MAX_RECONNECT_ATTEMPTS) {
        setState((prev) => ({
          ...prev,
          status: "error",
          error: "Terminal 重连次数过多，已停止重连",
        }));
        return;
      }
      const delay = Math.min(200 * Math.pow(2, reconnectCountRef.current), 5000);
      reconnectCountRef.current += 1;
      reconnectTimerRef.current = setTimeout(() => {
        reconnectTimerRef.current = null;
        connect();
      }, delay);
    };

    ws.onopen = () => {
      // 忽略来自旧 socket 的回调（手动 reconnect / cleanup 后旧 socket 仍可能触发）
      if (ws !== wsRef.current) return;
      reconnectCountRef.current = 0;

      if (attachTarget) {
        pendingSpawnRef.current = [];
        ws.send(JSON.stringify({
          type: "attach",
          terminal_id: attachTarget,
        }));
        return;
      }

      setState((prev) => ({ ...prev, status: "connected" }));

      const pendingQueue = pendingSpawnRef.current;
      if (pendingQueue.length > 0) {
        pendingSpawnRef.current = [];
        const pending = pendingQueue[pendingQueue.length - 1];
        const spawnTid = terminalIdRef.current || externalTerminalIdRef.current || expiredTerminalIdRef.current || `term-${Date.now()}`;
        ws.send(
          JSON.stringify({
            type: "spawn",
            terminal_id: spawnTid,
            rows: pending.rows,
            cols: pending.cols,
            cwd: pending.cwd,
          }),
        );
      }
    };

    ws.onmessage = (event) => {
      // 忽略来自旧 socket 的回调
      if (ws !== wsRef.current) return;
      try {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case "spawned": {
            const tid = msg.terminal_id;
            setState((prev) => ({
              ...prev,
              status: "connected",
              terminalId: tid,
              pid: msg.pid ?? null,
            }));
            onSpawnedRef.current?.(tid, msg.pid);
            break;
          }
          case "attached": {
            const tid = msg.terminal_id;
            setState((prev) => ({
              ...prev,
              status: "connected",
              terminalId: tid,
              pid: msg.pid ?? null,
            }));
            onAttachedRef.current?.(tid, msg.pid);
            break;
          }
          case "output": {
            onOutputRef.current?.(msg.data);
            break;
          }
          case "exited": {
            onExitedRef.current?.(msg.terminal_id, msg.exit_code);
            break;
          }
          case "error": {
            const isExpired = msg.message?.includes("过期");
            setState((prev) => ({
              ...prev,
              error: msg.message,
              terminalId: isExpired ? null : prev.terminalId,
              pid: isExpired ? null : prev.pid,
            }));
            if (isExpired) {
              terminalIdRef.current = null;
              // 标记过期，防止 render 阶段重新写入
              expiredTerminalIdRef.current = attachTarget ?? null;
              // 清除过期 terminalId，下次 connect 走 spawn 而非 attach
              externalTerminalIdRef.current = null;
              // 关闭当前 WebSocket，触发 reconnect
              const wsToClose = wsRef.current;
              if (wsToClose) {
                wsRef.current = null;
                try { wsToClose.close(); } catch { /* ignore */ }
              }
              // 标记非主动关闭，交由 scheduleReconnect 重连
              manualCloseRef.current = false;
              scheduleReconnect();
            }
            onErrorRef.current?.(msg.terminal_id, msg.message);
            break;
          }
          case "killed": {
            setState((prev) => ({ ...prev, terminalId: null, pid: null }));
            break;
          }
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      // 忽略来自旧 socket 的回调
      if (ws !== wsRef.current) return;
      wsRef.current = null;

      // 主动关闭（unmount / 手动 reconnect / kill）：仅更新状态，不自动重连
      if (manualCloseRef.current) {
        setState((prev) => {
          const wasActive = prev.status === "connected" || prev.status === "connecting" || prev.status === "attaching";
          return {
            ...prev,
            status: wasActive ? "disconnected" : prev.status,
          };
        });
        return;
      }

      // 意外断开（后端重启 / 网络抖动）：标记 disconnected 并自动重连
      setState((prev) => ({ ...prev, status: "disconnected" }));
      scheduleReconnect();
    };

    ws.onerror = () => {
      // 忽略来自旧 socket 的回调
      if (ws !== wsRef.current) return;

      // 主动关闭时不自动重连
      if (manualCloseRef.current) {
        setState((prev) => ({
          ...prev,
          status: "error",
          error: "WebSocket 连接失败",
        }));
        return;
      }

      // 意外错误：标记 disconnected 并交由指数退避重连
      setState((prev) => ({ ...prev, status: "disconnected" }));
      scheduleReconnect();
    };
  }, []);

  // 首次挂载时自动连接
  useEffect(() => {
    if (state.status === "idle") {
      connect();
    }
  }, []); // eslint-disable-line

  const disconnect = useCallback(() => {
    const ws = wsRef.current;
    if (ws) {
      // 标记主动关闭，阻止 onclose 自动重连
      manualCloseRef.current = true;
      wsRef.current = null;
      try {
        ws.close();
      } catch {
        // ignore
      }
    }
  }, []);

  const spawn = useCallback(
    (rows: number, cols: number, cwd?: string) => {
      const ws = wsRef.current;
      const tid = terminalIdRef.current || externalTerminalIdRef.current || expiredTerminalIdRef.current || `term-${Date.now()}`;
      if (ws?.readyState === WebSocket.OPEN) {
        ws.send(
          JSON.stringify({
            type: "spawn",
            terminal_id: tid,
            rows,
            cols,
            cwd,
          }),
        );
      } else {
        pendingSpawnRef.current.push({ rows, cols, cwd });
        terminalIdRef.current = null;
        connect();
      }
    },
    [connect],
  );

  const input = useCallback(
    (data: string) => {
      const ws = wsRef.current;
      const tid = terminalIdRef.current;
      if (ws?.readyState === WebSocket.OPEN && tid) {
        ws.send(
          JSON.stringify({
            type: "input",
            terminal_id: tid,
            data,
          }),
        );
      }
    },
    [],
  );

  const resize = useCallback(
    (rows: number, cols: number) => {
      const ws = wsRef.current;
      const tid = terminalIdRef.current;
      if (ws?.readyState === WebSocket.OPEN && tid) {
        ws.send(
          JSON.stringify({
            type: "resize",
            terminal_id: tid,
            rows,
            cols,
          }),
        );
      }
    },
    [],
  );

  const kill = useCallback(() => {
    const ws = wsRef.current;
    const tid = terminalIdRef.current;
    if (ws?.readyState === WebSocket.OPEN && tid) {
      // kill 是主动操作：标记主动关闭，防止服务端关闭连接后触发自动重连 + re-spawn
      manualCloseRef.current = true;
      ws.send(
        JSON.stringify({
          type: "kill",
          terminal_id: tid,
        }),
      );
    }
    setState((prev) => ({ ...prev, terminalId: null, pid: null }));
  }, []);

  const reconnect = useCallback(() => {
    disconnect();
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    reconnectCountRef.current = 0;
    connect();
  }, [disconnect, connect]);

  useEffect(() => {
    return () => {
      disconnect();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };
  }, [disconnect]);

  return {
    state,
    spawn,
    input,
    resize,
    kill,
    reconnect,
  };
}
