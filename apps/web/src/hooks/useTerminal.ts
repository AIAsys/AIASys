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
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  return `${protocol}//${host}/ws/terminal/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}`;
}

export function useTerminal(options: UseTerminalOptions): UseTerminalReturn {
  const {
    userId,
    sessionId,
    terminalId: externalTerminalId,
    onOutput,
    onSpawned,
    onExited,
    onError,
    onAttached,
  } = options;

  const [state, setState] = useState<TerminalState>({
    status: "idle",
    error: null,
    terminalId: externalTerminalId ?? null,
    pid: null,
  });

  const wsRef = useRef<WebSocket | null>(null);
  const pendingSpawnRef = useRef<{ rows: number; cols: number; cwd?: string }[]>([]);
  const terminalIdRef = useRef<string | null>(externalTerminalId ?? null);
  const reconnectCountRef = useRef(0);
  // 标记已过期的 terminalId，防止 render 阶段重新写入 externalTerminalIdRef
  const expiredTerminalIdRef = useRef<string | null>(null);

  // 稳定引用：userId/sessionId/externalTerminalId 变化时更新 ref
  const userIdRef = useRef(userId);
  const sessionIdRef = useRef(sessionId);
  const externalTerminalIdRef = useRef<string | undefined | null>(externalTerminalId);
  userIdRef.current = userId;
  sessionIdRef.current = sessionId;

  // 只在 prop 实际变化时更新 externalTerminalIdRef，且如果该 terminalId 已过期则忽略
  if (externalTerminalId !== externalTerminalIdRef.current && externalTerminalId !== expiredTerminalIdRef.current) {
    externalTerminalIdRef.current = externalTerminalId;
  }

  // ref 存储回调，避免 StrictMode 下 ws.onmessage 使用旧闭包
  const onOutputRef = useRef(onOutput);
  const onSpawnedRef = useRef(onSpawned);
  const onExitedRef = useRef(onExited);
  const onErrorRef = useRef(onError);
  const onAttachedRef = useRef(onAttached);
  onOutputRef.current = onOutput;
  onSpawnedRef.current = onSpawned;
  onExitedRef.current = onExited;
  onErrorRef.current = onError;
  onAttachedRef.current = onAttached;

  // 同步 terminalIdRef
  useEffect(() => {
    terminalIdRef.current = state.terminalId;
  }, [state.terminalId]);

  // 外部 terminalId 变化时同步
  useEffect(() => {
    if (externalTerminalId && externalTerminalId !== terminalIdRef.current) {
      terminalIdRef.current = externalTerminalId;
      setState((prev) => ({ ...prev, terminalId: externalTerminalId }));
    }
  }, [externalTerminalId]);

  const connect = useCallback(() => {
    const currentUserId = userIdRef.current;
    const currentSessionId = sessionIdRef.current;
    const attachTarget = externalTerminalIdRef.current;

    if (wsRef.current?.readyState === WebSocket.OPEN || wsRef.current?.readyState === WebSocket.CONNECTING) {
      return;
    }

    setState((prev) => ({
      ...prev,
      status: attachTarget ? "attaching" : "connecting",
      error: null,
    }));

    const url = buildWsUrl(currentUserId, currentSessionId);
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
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
        ws.send(
          JSON.stringify({
            type: "spawn",
            terminal_id: terminalIdRef.current || `term-${Date.now()}`,
            rows: pending.rows,
            cols: pending.cols,
            cwd: pending.cwd,
          }),
        );
      }
    };

    ws.onmessage = (event) => {
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
              const ws = wsRef.current;
              if (ws) {
                wsRef.current = null;
                try { ws.close(); } catch { /* ignore */ }
              }
              setTimeout(() => {
                connect();
              }, 100);
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
      wsRef.current = null;
      setState((prev) => {
        const wasActive = prev.status === "connected" || prev.status === "connecting" || prev.status === "attaching";
        return {
          ...prev,
          status: wasActive ? "disconnected" : prev.status,
        };
      });
    };

    ws.onerror = () => {
      wsRef.current = null;
      setState((prev) => ({
        ...prev,
        status: "error",
        error: "WebSocket 连接失败",
      }));
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
      const tid = terminalIdRef.current || `term-${Date.now()}`;
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
    reconnectCountRef.current = 0;
    connect();
  }, [disconnect, connect]);

  useEffect(() => {
    return () => {
      disconnect();
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