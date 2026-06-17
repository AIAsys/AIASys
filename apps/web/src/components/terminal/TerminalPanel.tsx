import { useEffect, useRef, useCallback } from "react";
import { Terminal as XTerm } from "@xterm/xterm";
import type { ITheme } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import "@xterm/xterm/css/xterm.css";
import { useTerminal, type UseTerminalOptions } from "@/hooks/useTerminal";
import { useTheme } from "@/contexts/ThemeContext";
import { cn } from "@/lib/utils";
import { Loader2, AlertCircle, WifiOff, RefreshCw, Link2 } from "lucide-react";

const LIGHT_THEME: ITheme = {
  background: "#ffffff",
  foreground: "#101828",
  cursor: "#111827",
  selectionBackground: "#dbeafe",
  black: "#1f2937",
  red: "#b42318",
  green: "#0f766e",
  yellow: "#b54708",
  blue: "#2563eb",
  magenta: "#9333ea",
  cyan: "#0891b2",
  white: "#f3f4f6",
  brightBlack: "#6b7280",
  brightRed: "#ef4444",
  brightGreen: "#22c55e",
  brightYellow: "#eab308",
  brightBlue: "#3b82f6",
  brightMagenta: "#a855f7",
  brightCyan: "#06b6d4",
  brightWhite: "#ffffff",
};

const DARK_THEME: ITheme = {
  background: "#1a1b26",
  foreground: "#c0caf5",
  cursor: "#c0caf5",
  selectionBackground: "#33467c",
  black: "#15161e",
  red: "#f7768e",
  green: "#9ece6a",
  yellow: "#e0af68",
  blue: "#7aa2f7",
  magenta: "#bb9af7",
  cyan: "#7dcfff",
  white: "#a9b1d6",
  brightBlack: "#414868",
  brightRed: "#f7768e",
  brightGreen: "#9ece6a",
  brightYellow: "#e0af68",
  brightBlue: "#7aa2f7",
  brightMagenta: "#bb9af7",
  brightCyan: "#7dcfff",
  brightWhite: "#c0caf5",
};

interface TerminalPanelProps {
  userId: string;
  sessionId: string;
  terminalId?: string;
  className?: string;
  /** 是否可见。false 时隐藏终端但保留 xterm 实例和 WebSocket */
  visible?: boolean;
  /** 初始连接模式：'attach' 优先 attach 已有 PTY（用于恢复场景），'spawn' 创建新 PTY（默认） */
  initialMode?: "spawn" | "attach";
  onSpawned?: (terminalId: string, pid: number) => void;
  onExited?: (terminalId: string, exitCode: number) => void;
}

export function TerminalPanel({
  userId,
  sessionId,
  terminalId,
  className,
  visible = true,
  initialMode,
  onSpawned,
  onExited,
}: TerminalPanelProps) {
  const { resolvedTheme } = useTheme();

  const containerRef = useRef<HTMLDivElement | null>(null);
  const xtermRef = useRef<XTerm | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const hasSpawnedRef = useRef(false);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleOutput = useCallback((data: string) => {
    xtermRef.current?.write(data);
  }, []);

  const handleAttached = useCallback((_terminalId: string, _pid: number) => {
    // attach 成功后，xterm 已存在，输出回调已绑定
  }, []);

  const hookOptions: UseTerminalOptions = {
    userId,
    sessionId,
    terminalId,
    initialMode,
    onOutput: handleOutput,
    onSpawned,
    onExited,
    onAttached: handleAttached,
  };

  const { state, spawn, input, resize, reconnect } = useTerminal(hookOptions);

  // 初始化 xterm.js（仅在首次挂载时执行）
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const term = new XTerm({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace',
      theme: resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME,
      scrollback: 10000,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);

    term.open(container);

    // 尝试加载 WebGL renderer，不可用时 fallback 到默认 Canvas renderer
    try {
      const webglAddon = new WebglAddon();
      term.loadAddon(webglAddon);
    } catch {
      // WebGL 不可用时 fallback 到默认 Canvas renderer
    }

    fitAddon.fit();

    xtermRef.current = term;
    fitAddonRef.current = fitAddon;

    term.onData((data) => {
      input(data);
    });

    // ResizeObserver：容器尺寸变化时重新 fit（防抖 200ms）
    const handleResize = () => {
      if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
      resizeTimerRef.current = setTimeout(() => {
        fitAddon.fit();
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          resize(Math.floor(dims.rows), Math.floor(dims.cols));
        }
      }, 200);
    };

    const resizeObserver = new ResizeObserver(() => {
      handleResize();
    });
    resizeObserver.observe(container);

    // spawn：仅当 visible 时立即 spawn，否则延迟到 visible 时
    if (!hasSpawnedRef.current && !state.terminalId) {
      if (visible && container.offsetWidth > 0) {
        hasSpawnedRef.current = true;
        const dims = fitAddon.proposeDimensions();
        if (dims) {
          spawn(Math.floor(dims.rows), Math.floor(dims.cols));
        } else {
          spawn(24, 80);
        }
      }
    }

    const handleBeforeUnload = () => {
      (window as unknown as Record<string, unknown>)._pageRefreshing = true;
    };
    window.addEventListener("beforeunload", handleBeforeUnload);

    return () => {
      resizeObserver.disconnect();
      if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
      term.dispose();
      xtermRef.current = null;
      fitAddonRef.current = null;
      hasSpawnedRef.current = false;
      window.removeEventListener("beforeunload", handleBeforeUnload);
    };
    // 只在 userId/sessionId 变化时重新初始化（terminalId 变化通过 useTerminal 内部处理 attach）
  }, [userId, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // 主题切换时更新 xterm 主题
  useEffect(() => {
    if (xtermRef.current) {
      xtermRef.current.options.theme =
        resolvedTheme === "dark" ? DARK_THEME : LIGHT_THEME;
    }
  }, [resolvedTheme]);

  // visible 变化时：强制 fit + 如果尚未 spawn 则 spawn
  useEffect(() => {
    if (visible) {
      requestAnimationFrame(() => {
        const fitAddon = fitAddonRef.current;
        if (!fitAddon) return;
        if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
        resizeTimerRef.current = setTimeout(() => {
          fitAddon.fit();
          const dims = fitAddon.proposeDimensions();
          if (dims) {
            resize(Math.floor(dims.rows), Math.floor(dims.cols));
          }
          // 延迟 spawn：如果之前因不可见未 spawn，现在执行
          if (!hasSpawnedRef.current && !state.terminalId) {
            hasSpawnedRef.current = true;
            if (dims) {
              spawn(Math.floor(dims.rows), Math.floor(dims.cols));
            } else {
              spawn(24, 80);
            }
          }
        }, 200);
      });
    }
  }, [visible, resize, spawn, state.terminalId]);

  // Re-spawn when reconnected after disconnect
  useEffect(() => {
    if (state.status === "connected" && !state.terminalId && !hasSpawnedRef.current) {
      hasSpawnedRef.current = true;
      const dims = fitAddonRef.current?.proposeDimensions();
      if (dims) {
        spawn(Math.floor(dims.rows), Math.floor(dims.cols));
      }
    }
  }, [state.status, state.terminalId, spawn]);

  const renderOverlay = () => {
    if (state.status === "attaching") {
      return (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
          <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
            <Link2 className="h-5 w-5 animate-pulse" />
            <span>正在恢复终端会话...</span>
          </div>
        </div>
      );
    }
    if (state.status === "connecting") {
      return (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
          <div className="flex flex-col items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span>正在连接终端...</span>
          </div>
        </div>
      );
    }
    if (state.status === "error") {
      return (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
          <div className="flex max-w-[260px] flex-col items-center gap-3 px-4 text-center text-sm">
            <AlertCircle className="h-5 w-5 text-destructive" />
            <div>
              <div className="font-medium text-foreground">终端连接失败</div>
              <div className="mt-0.5 text-xs text-muted-foreground">
                请检查运行环境是否正常，或稍后重试。
              </div>
            </div>
            {state.error && state.error !== "WebSocket 连接失败" && (
              <div className="w-full rounded-md bg-muted px-2 py-1.5 text-left text-[11px] font-mono text-muted-foreground">
                {state.error}
              </div>
            )}
            <button
              type="button"
              onClick={reconnect}
              className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <RefreshCw className="h-3 w-3" />
              重试
            </button>
          </div>
        </div>
      );
    }
    if (state.status === "disconnected") {
      return (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-background/80">
          <div className="flex flex-col items-center gap-3 text-sm text-muted-foreground">
            <WifiOff className="h-5 w-5" />
            <span>连接已断开</span>
            <button
              type="button"
              onClick={reconnect}
              className="inline-flex items-center gap-1.5 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
            >
              <RefreshCw className="h-3 w-3" />
              重新连接
            </button>
          </div>
        </div>
      );
    }
    return null;
  };

  return (
    <div
      className={cn("relative flex h-full w-full flex-col overflow-hidden", className)}
      style={{ display: visible ? undefined : "none" }}
    >
      {renderOverlay()}
      <div
        ref={containerRef}
        className="h-full w-full"
        style={{ background: resolvedTheme === "dark" ? "#1a1b26" : "#ffffff" }}
      />
    </div>
  );
}