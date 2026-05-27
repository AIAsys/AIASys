import { useState, useCallback, useEffect, useRef } from "react";
import {
  Terminal,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Play,
  Square,
  RotateCcw,
  Trash2,
  Bell,
  BellOff,
  Sparkles,
  Plus,
  Copy,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useSessionMonitors } from "@/hooks/useSessionMonitors";
import { parseAnsiToElements } from "@/lib/ansi";
import { cn } from "@/lib/utils";

interface WorkspaceMonitorPanelProps {
  userId?: string;
  sessionId?: string;
}

function formatDuration(createdAt: number, completedAt?: number | null): string {
  const end = completedAt ?? Date.now() / 1000;
  const diff = Math.max(0, end - createdAt);
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  return `${Math.floor(diff / 3600)}h${Math.floor((diff % 3600) / 60)}m`;
}

const STATUS_BADGE_CLASS: Record<string, string> = {
  running: "border-success/20 bg-success-container text-success",
  completed: "border-foreground/10 bg-muted text-muted-foreground",
  error: "border-error/20 bg-error-container text-error",
  killed: "border-warning/20 bg-warning-container text-warning",
};

const STATUS_LABELS: Record<string, string> = {
  running: "运行中",
  completed: "已完成",
  error: "错误",
  killed: "已终止",
};

function useLiveTick(active: boolean) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((t) => t + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  return tick;
}

export function WorkspaceMonitorPanel({ userId, sessionId }: WorkspaceMonitorPanelProps) {
  const { monitors, loading, error, refresh, toggleExpand, doKill, doSpawn, doRestart, doDelete, doUpdateMode } =
    useSessionMonitors(userId, sessionId);
  const [killingId, setKillingId] = useState<string | null>(null);
  const [restartingId, setRestartingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [updatingModeId, setUpdatingModeId] = useState<string | null>(null);
  const [commandInput, setCommandInput] = useState("");
  const [spawning, setSpawning] = useState(false);
  const [spawnMode, setSpawnMode] = useState<"notify" | "silent">("notify");
  const [spawnTimeout, setSpawnTimeout] = useState("");
  const [spawnOpen, setSpawnOpen] = useState(false);

  const hasRunning = monitors.some((m) => m.info.status === "running");
  const tick = useLiveTick(hasRunning);
  void tick;

  const commandInputRef = useRef(commandInput);
  commandInputRef.current = commandInput;
  const spawnTimeoutRef = useRef(spawnTimeout);
  spawnTimeoutRef.current = spawnTimeout;
  const monitorsRef = useRef(monitors);
  monitorsRef.current = monitors;

  const hasAutoExpanded = useRef(false);
  useEffect(() => {
    if (monitors.length === 0) {
      hasAutoExpanded.current = false;
      return;
    }
    if (hasAutoExpanded.current || loading) return;
    const running = monitors.filter((m) => m.info.status === "running");
    if (running.length === 1 && running[0].segments.length > 0 && !running[0].isExpanded) {
      toggleExpand(running[0].info.id);
      hasAutoExpanded.current = true;
    }
  }, [monitors, loading, toggleExpand]);

  const handleKill = useCallback(
    async (monitorId: string) => {
      setKillingId(monitorId);
      try {
        await doKill(monitorId);
      } finally {
        setKillingId(null);
      }
    },
    [doKill],
  );

  const handleRestart = useCallback(
    async (monitorId: string, command: string) => {
      setRestartingId(monitorId);
      try {
        await doRestart(command);
      } finally {
        setRestartingId(null);
      }
    },
    [doRestart],
  );

  const handleDelete = useCallback(
    async (monitorId: string) => {
      setDeletingId(monitorId);
      try {
        await doDelete(monitorId);
      } finally {
        setDeletingId(null);
      }
    },
    [doDelete],
  );

  const handleClearAll = useCallback(async () => {
    const toDelete = monitorsRef.current.filter((m) => m.info.status !== "running");
    for (const m of toDelete) {
      await doDelete(m.info.id);
    }
  }, [doDelete]);

  const handleSpawn = useCallback(async () => {
    const cmd = commandInputRef.current.trim();
    if (!cmd) return;
    setSpawning(true);
    const req: { command: string; mode?: "notify" | "silent"; timeout_seconds?: number } = {
      command: cmd,
      mode: spawnMode,
    };
    const timeout = parseInt(spawnTimeoutRef.current, 10);
    if (!isNaN(timeout) && timeout > 0) {
      req.timeout_seconds = timeout;
    }
    try {
      await doSpawn(req);
      setCommandInput("");
    } finally {
      setSpawning(false);
    }
  }, [doSpawn, spawnMode]);

  const hasStopped = monitors.some((m) => m.info.status !== "running");

  return (
    <div
      className="flex h-full min-h-0 flex-col bg-background"
      data-testid="workspace-monitor-panel"
    >
      {/* Header */}
      <div className="border-b border-border/70 px-5 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Terminal className="h-4 w-4 text-foreground" />
            <span className="text-sm font-semibold text-foreground">监控任务</span>
            {monitors.length > 0 && (
              <Badge variant="outline" className="border-border bg-background text-muted-foreground text-[10px]">
                {monitors.length}
              </Badge>
            )}
            {hasRunning && (
              <span
                className="h-1.5 w-1.5 rounded-full bg-info animate-pulse"
                title="正在轮询更新"
              />
            )}
          </div>
          <div className="flex items-center gap-1">
            {hasStopped && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    className="h-8 w-8 p-0 text-muted-foreground hover:text-error"
                    onClick={handleClearAll}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>清除所有已完成/终止任务</TooltipContent>
              </Tooltip>
            )}
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  className="h-8 w-8 p-0"
                  onClick={() => refresh()}
                  disabled={loading}
                >
                  <RefreshCw className={cn("h-3.5 w-3.5", loading && "animate-spin")} />
                </Button>
              </TooltipTrigger>
              <TooltipContent>刷新</TooltipContent>
            </Tooltip>
          </div>
        </div>
      </div>

      {/* Spawn area */}
      <Collapsible open={spawnOpen} onOpenChange={setSpawnOpen}>
        <div className="border-b border-border/70">
          <CollapsibleTrigger asChild>
            <Button
              variant="ghost"
              size="sm"
              className="w-full h-8 gap-1.5 text-[11px] text-muted-foreground rounded-none"
            >
              <Plus className="h-3.5 w-3.5" />
              {spawnOpen ? "收起命令面板" : "新建监控任务"}
            </Button>
          </CollapsibleTrigger>
        </div>
        <CollapsibleContent>
          <div className="border-b border-border/70 px-5 py-3">
            <div className="flex items-center gap-2">
              <Input
                type="text"
                value={commandInput}
                onChange={(e) => setCommandInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void handleSpawn();
                }}
                placeholder="输入 shell 命令并启动..."
                disabled={spawning}
                className="min-w-0 flex-1 rounded-lg text-sm"
              />
              <Button
                type="button"
                size="sm"
                className="h-9 shrink-0 gap-1 rounded-xl px-3 text-[12px]"
                onClick={() => void handleSpawn()}
                disabled={spawning || !commandInput.trim()}
              >
                <Play className="h-3.5 w-3.5" />
                {spawning ? "启动中" : "启动"}
              </Button>
            </div>
            <div className="mt-2.5 flex items-center gap-4">
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-muted-foreground">模式</span>
                <div className="flex rounded-lg border border-border/60 bg-background p-0.5">
                  <button
                    type="button"
                    className={cn(
                      "rounded-md px-2.5 py-1 text-[11px] transition-colors",
                      spawnMode === "notify"
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    onClick={() => setSpawnMode("notify")}
                  >
                    通知
                  </button>
                  <button
                    type="button"
                    className={cn(
                      "rounded-md px-2.5 py-1 text-[11px] transition-colors",
                      spawnMode === "silent"
                        ? "bg-primary text-primary-foreground"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                    onClick={() => setSpawnMode("silent")}
                  >
                    静默
                  </button>
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-[11px] text-muted-foreground">限时</span>
                <Input
                  type="number"
                  min={1}
                  value={spawnTimeout}
                  onChange={(e) => setSpawnTimeout(e.target.value)}
                  placeholder="秒"
                  className="h-7 w-20 rounded-md text-[11px]"
                />
                <span className="text-[11px] text-muted-foreground">秒</span>
              </div>
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      {/* Monitor list */}
      <ScrollArea className="min-h-0 flex-1">
        <div className="px-5 py-4">
          {error && (
            <div className="mb-3 rounded-lg border border-error/20 bg-error-container px-3 py-2 text-[11px] text-on-error-container">
              {error}
            </div>
          )}

          {loading && monitors.length === 0 ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <div key={i} className="rounded-xl border border-border/60 bg-card p-3">
                  <Skeleton className="h-4 w-3/4 mb-2" />
                  <Skeleton className="h-3 w-1/2" />
                </div>
              ))}
            </div>
          ) : monitors.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center py-10 text-center">
              <Terminal className="h-8 w-8 text-muted-foreground/30" />
              <div className="mt-3 text-sm font-medium text-foreground">暂无监控任务</div>
              <div className="mt-1 text-xs leading-5 text-muted-foreground">
                Agent 调用 Monitor 工具启动的命令会在这里显示实时输出
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              {monitors.map((m) => (
                <div
                  key={m.info.id}
                  className="group relative rounded-xl border border-border/60 bg-card p-3 transition-colors hover:border-border"
                >
                  {/* Top row: status dot + command + badge + expand */}
                  <div className="flex items-center gap-2">
                    {m.info.status === "running" ? (
                      <span className="relative flex h-2 w-2 shrink-0">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-info opacity-75" />
                        <span className="relative inline-flex h-2 w-2 rounded-full bg-info" />
                      </span>
                    ) : (
                      <span
                        className={cn(
                          "h-2 w-2 shrink-0 rounded-full",
                          m.info.status === "completed" && "bg-success",
                          m.info.status === "error" && "bg-error",
                          m.info.status === "killed" && "bg-warning",
                        )}
                      />
                    )}
                    <span className="min-w-0 flex-1 truncate font-mono text-[12px] font-medium text-foreground">
                      {m.info.command}
                    </span>
                    <Badge
                      variant="outline"
                      className={cn("shrink-0 text-[10px]", STATUS_BADGE_CLASS[m.info.status])}
                    >
                      {STATUS_LABELS[m.info.status] || m.info.status}
                    </Badge>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 shrink-0 p-0 text-muted-foreground"
                      onClick={() => toggleExpand(m.info.id)}
                    >
                      {m.isExpanded ? (
                        <ChevronDown className="h-3.5 w-3.5" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5" />
                      )}
                    </Button>
                  </div>

                  {/* Actions row - hover reveal */}
                  <div className="mt-2 flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                    {m.info.status === "running" ? (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0 text-error hover:bg-error/10 hover:text-error"
                        onClick={() => handleKill(m.info.id)}
                        disabled={killingId === m.info.id}
                        title="终止"
                      >
                        {killingId === m.info.id ? (
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        ) : (
                          <Square className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    ) : (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                          onClick={() => handleRestart(m.info.id, m.info.command)}
                          disabled={restartingId === m.info.id}
                          title="重启"
                        >
                          {restartingId === m.info.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <RotateCcw className="h-3.5 w-3.5" />
                          )}
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="ghost"
                          className="h-7 w-7 p-0 text-muted-foreground hover:bg-error/10 hover:text-error"
                          onClick={() => handleDelete(m.info.id)}
                          disabled={deletingId === m.info.id}
                          title="删除"
                        >
                          {deletingId === m.info.id ? (
                            <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          ) : (
                            <Trash2 className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </>
                    )}
                    {m.segments.length > 0 && (
                      <Button
                        type="button"
                        size="sm"
                        variant="ghost"
                        className="h-7 w-7 p-0 text-muted-foreground hover:text-foreground"
                        onClick={() => {
                          const text = m.segments.map((s) => s.content).join("\n");
                          void navigator.clipboard.writeText(text);
                        }}
                        title="复制输出"
                      >
                        <Copy className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </div>

                  {/* Metadata row */}
                  <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                    <span className="font-mono text-[10px]">{m.info.id.slice(0, 8)}</span>
                    <span>
                      时长: {formatDuration(m.info.created_at, m.info.completed_at)}
                    </span>
                    {m.info.exit_code !== null && (
                      <span>退出码: {m.info.exit_code}</span>
                    )}
                    <button
                      type="button"
                      disabled={updatingModeId === m.info.id}
                      onClick={async () => {
                        const newMode = m.info.mode === "notify" ? "silent" : "notify";
                        setUpdatingModeId(m.info.id);
                        try {
                          await doUpdateMode(m.info.id, newMode);
                        } finally {
                          setUpdatingModeId(null);
                        }
                      }}
                      className={cn(
                        "inline-flex items-center gap-0.5 rounded px-1.5 py-0.5 text-[10px] transition-colors disabled:opacity-50",
                        m.info.mode === "silent"
                          ? "bg-muted text-muted-foreground hover:text-foreground"
                          : "bg-info/10 text-info hover:bg-info/20",
                      )}
                      title={`点击切换为 ${m.info.mode === "notify" ? "静默" : "通知"} 模式`}
                    >
                      {m.info.mode === "silent" ? (
                        <>
                          <BellOff className="h-2.5 w-2.5" />
                          静默
                        </>
                      ) : (
                        <>
                          <Bell className="h-2.5 w-2.5" />
                          通知
                        </>
                      )}
                    </button>
                  </div>

                  {/* Notify completed hint */}
                  {m.info.mode === "notify" && m.info.status !== "running" && (
                    <div className="mt-2 flex items-center gap-1.5 rounded-lg border border-info/20 bg-info/5 px-2.5 py-1.5">
                      <Sparkles className="h-3 w-3 text-info" />
                      <span className="text-[11px] text-info">
                        任务已完成，Agent 会在下一轮主动关注结果
                      </span>
                    </div>
                  )}

                  {/* Collapsed output preview */}
                  {!m.isExpanded && m.segments.length > 0 && (
                    <button
                      type="button"
                      className="mt-2 w-full rounded-lg bg-muted/50 px-3 py-2 text-left transition-colors hover:bg-muted"
                      onClick={() => toggleExpand(m.info.id)}
                    >
                      <div className="font-mono text-[11px] leading-4 text-muted-foreground">
                        {m.segments.slice(-5).map((s, i) => (
                          <div key={i} className="truncate">
                            {s.is_stderr ? (
                              <span className="text-error/70">{s.content || " "}</span>
                            ) : (
                              <span>{s.content || " "}</span>
                            )}
                          </div>
                        ))}
                        {m.segments.length > 5 && (
                          <div className="mt-1 text-[10px] text-muted-foreground/60">
                            ... 共 {m.segments.length} 行，点击展开查看全部
                          </div>
                        )}
                      </div>
                    </button>
                  )}

                  {/* Expanded output */}
                  {m.isExpanded && (
                    <div className="mt-2 overflow-hidden rounded-lg border border-border/40 bg-[#0d1117]">
                      <div className="flex items-center justify-between border-b border-border/20 px-3 py-1.5">
                        <span className="text-[10px] text-muted-foreground">
                          输出 ({m.segments.length} 行)
                        </span>
                        <div className="flex items-center gap-1">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
                            onClick={() => {
                              const text = m.segments.map((s) => s.content).join("\n");
                              void navigator.clipboard.writeText(text);
                            }}
                            title="复制全部输出"
                          >
                            <Copy className="h-3 w-3" />
                          </Button>
                        </div>
                      </div>
                      <ScrollArea className="max-h-[320px]">
                        <div className="px-3 py-2 font-mono text-[11px] leading-5">
                          {m.segments.length === 0 ? (
                            <span className="text-muted-foreground/40">（暂无输出）</span>
                          ) : (
                            m.segments.map((s) => {
                              const parts = parseAnsiToElements(s.content || " ");
                              return (
                                <div key={s.index} className="whitespace-pre-wrap">
                                  {parts.map((part, i) => (
                                    <span
                                      key={i}
                                      className={cn(part.className, s.is_stderr && "bg-red-950/30")}
                                      style={part.color ? { color: part.color } : undefined}
                                    >
                                      {part.text}
                                    </span>
                                  ))}
                                </div>
                              );
                            })
                          )}
                          {m.info.status === "running" && (
                            <div className="mt-1 animate-pulse text-muted-foreground/40">_</div>
                          )}
                        </div>
                      </ScrollArea>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}

export default WorkspaceMonitorPanel;
