import { useEffect, useRef, useState } from "react";
import { BarChart3, Gauge, Loader2, Minimize2, Settings, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { getCurrentUserId } from "@/config/api";
import {
  setSessionBudget,
  clearSessionBudget,
} from "@/lib/api/sessionBudget";
import { useTokenUsageStats } from "@/hooks/useTokenUsageStats";

interface TokenUsageBarProps {
  sessionId?: string | null;
  refreshSignal?: number | string;
  onCompactConversation?: () => Promise<void> | void;
  hasMessages?: boolean;
  isCompactingConversation?: boolean;
  isRunning?: boolean;
  compactionState?: {
    phase: "begin" | "done";
    tokens_before?: number;
    tokens_after?: number;
    saved_tokens?: number;
    summary_tokens?: number;
  } | null;
  variant?: "bar" | "dropdown";
}

function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "0";
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`;
  return String(n);
}

function formatContextWindow(n: number | null): string {
  if (!n) return "未配置";
  return formatTokens(n);
}

function normalizeBudgetInput(value: string): number | null {
  const normalized = value.trim();
  if (!/^\d+$/.test(normalized)) return null;
  const parsed = Number(normalized);
  if (!Number.isSafeInteger(parsed) || parsed < 1) return null;
  return parsed;
}

export function TokenUsageBar({
  sessionId,
  refreshSignal,
  onCompactConversation,
  hasMessages = true,
  isCompactingConversation = false,
  isRunning = false,
  compactionState,
  variant = "bar",
}: TokenUsageBarProps) {
  const [budgetEnabled, setBudgetEnabled] = useState(false);
  const [tokenBudget, setTokenBudget] = useState("50000");
  const [isSaving, setIsSaving] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const editingRef = useRef(false);

  const userId = getCurrentUserId();

  const { stats, loadStats } = useTokenUsageStats({
    sessionId,
    refreshSignal,
    isRunning,
  });

  // stats 更新后同步预算开关与输入框；输入框只在非编辑态同步，避免覆盖用户输入
  useEffect(() => {
    if (!stats) return;
    setBudgetEnabled(stats.token_budget != null);
    if (stats.token_budget && !editingRef.current) {
      setTokenBudget(String(stats.token_budget));
    }
  }, [stats]);

  if (!sessionId || !stats) return null;

  const isCompacting =
    isCompactingConversation || compactionState?.phase === "begin";
  const compactionJustFinished = compactionState?.phase === "done";

  const budgetPercent = stats.token_budget
    ? Math.min(100, (stats.tokens_used / stats.token_budget) * 100)
    : 0;
  const contextPercent = Math.min(100, Math.max(0, stats.context_usage_pct));
  const contextValueLabel = `${formatTokens(stats.context_tokens)}/${formatContextWindow(
    stats.context_window,
  )}`;
  const contextPercentLabel = stats.context_window
    ? `${stats.context_usage_pct.toFixed(stats.context_usage_pct > 0 && stats.context_usage_pct < 1 ? 1 : 0)}%`
    : "未配置";
  const budgetValueLabel = stats.token_budget
    ? `${formatTokens(stats.tokens_used)}/${formatTokens(stats.token_budget)}`
    : `已用 ${formatTokens(stats.tokens_used)}`;

  const budgetExhausted = stats.budget_status === "budget_limited";

  const barClass = (pct: number) =>
    cn(
      "h-full rounded-full transition-all",
      pct >= 90 ? "bg-error" : pct >= 85 ? "bg-orange-500" : pct >= 70 ? "bg-warning" : "bg-success",
    );

  const handleToggleBudget = async (checked: boolean) => {
    if (!userId || !sessionId) return;
    const nextBudget = normalizeBudgetInput(tokenBudget);
    if (checked) {
      if (nextBudget == null) {
        setBudgetError("预算上限必须是大于 0 的整数。");
        return;
      }
    } else {
      setBudgetError(null);
    }
    setBudgetEnabled(checked);
    setIsSaving(true);
    try {
      if (checked) {
        await setSessionBudget(userId, sessionId, {
          token_budget: nextBudget,
        });
      } else {
        await clearSessionBudget(userId, sessionId);
      }
      await loadStats();
    } catch {
      setBudgetEnabled(!checked);
    } finally {
      setIsSaving(false);
    }
  };

  const handleSaveBudget = async () => {
    if (!userId || !sessionId || !budgetEnabled) return;
    const nextBudget = normalizeBudgetInput(tokenBudget);
    if (nextBudget == null) {
      setBudgetError("预算上限必须是大于 0 的整数。");
      return;
    }
    setBudgetError(null);
    setIsSaving(true);
    try {
      await setSessionBudget(userId, sessionId, {
        token_budget: nextBudget,
      });
      setTokenBudget(String(nextBudget));
      await loadStats();
    } catch {
      /* ignore */
    } finally {
      setIsSaving(false);
    }
  };

  const compactButtonClass = cn(
    "flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-tertiary/40 hover:bg-tertiary-container/50 hover:text-tertiary",
    contextPercent >= 85 && !isCompacting && !isRunning && "border-warning/40 bg-warning/10 text-warning hover:text-warning hover:bg-warning/15",
    (isCompacting || isRunning) && "cursor-not-allowed opacity-70",
  );

  const triggerButtonClass = cn(
    "flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-tertiary/40 hover:bg-tertiary-container/50 hover:text-tertiary",
    budgetExhausted && "border-error/40 bg-error/10 text-error hover:text-error hover:bg-error/15",
  );

  const popoverContent = (
    <PopoverContent className="w-80 space-y-4 p-4" align="end">
      <div className="space-y-1">
        <div className="text-sm font-semibold text-foreground">当前会话预算</div>
        <div className="text-xs leading-5 text-muted-foreground">
          预算限制当前会话的累计 token 消耗，普通对话和自动化任务都会受这个上限约束。预算可以高于模型上下文总量，压缩不会重置用量。
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="rounded-lg border border-border bg-muted/20 px-3 py-2">
          <div className="text-muted-foreground">上下文占用</div>
          <div className="mt-1 font-medium tabular-nums text-foreground">
            {contextValueLabel}
          </div>
        </div>
        <div className="rounded-lg border border-border bg-muted/20 px-3 py-2">
          <div className="text-muted-foreground">预算用量</div>
          <div className="mt-1 font-medium tabular-nums text-foreground">
            {budgetValueLabel}
          </div>
        </div>
      </div>

      {variant === "dropdown" && onCompactConversation && hasMessages && (
        <button
          type="button"
          onClick={() => {
            if (isCompacting || isRunning) return;
            setPopoverOpen(false);
            void onCompactConversation();
          }}
          disabled={isCompacting || isRunning}
          className={cn(
            "flex w-full items-center justify-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition-colors",
            contextPercent >= 85 && !isCompacting && !isRunning
              ? "border-warning/40 bg-warning/10 text-warning hover:bg-warning/15"
              : "border-border bg-background text-muted-foreground hover:bg-tertiary-container/50 hover:text-tertiary",
            (isCompacting || isRunning) && "cursor-not-allowed opacity-70",
          )}
        >
          {isCompacting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Minimize2 className="h-3.5 w-3.5" />
          )}
          {isCompacting ? "压缩中" : isRunning ? "运行中" : "压缩上下文"}
        </button>
      )}

      <div className="flex items-center justify-between">
        <Label htmlFor="budget-switch" className="text-sm cursor-pointer">
          开启预算控制
        </Label>
        <Switch
          id="budget-switch"
          checked={budgetEnabled}
          onCheckedChange={(c) => void handleToggleBudget(c)}
          disabled={isSaving}
        />
      </div>
      {budgetEnabled && (
        <div className="space-y-2">
          <Label htmlFor="budget-tokens" className="text-xs">
            Token 预算上限
          </Label>
          <div className="flex gap-2">
            <Input
              id="budget-tokens"
              type="text"
              inputMode="numeric"
              min={1}
              step={1}
              value={tokenBudget}
              onChange={(e) => {
                // 只允许数字字符
                const digits = e.target.value.replace(/\D/g, "");
                setTokenBudget(digits);
                if (budgetError) setBudgetError(null);
              }}
              onFocus={() => {
                editingRef.current = true;
              }}
              onBlur={() => {
                editingRef.current = false;
                void handleSaveBudget();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") void handleSaveBudget();
              }}
              disabled={isSaving}
              className="h-8 text-sm"
            />
            <Button
              type="button"
              variant="default"
              size="sm"
              className="h-8 shrink-0"
              onClick={() => void handleSaveBudget()}
              disabled={isSaving}
            >
              设置
            </Button>
          </div>
          {budgetError && (
            <div className="text-[11px] leading-5 text-error">
              {budgetError}
            </div>
          )}
        </div>
      )}
      {contextPercent >= 85 && onCompactConversation && hasMessages && !isCompacting && !isRunning && (
        <div className="rounded-lg bg-warning/10 px-3 py-2 text-[11px] text-warning">
          上下文接近上限（{contextPercentLabel}），建议压缩以释放空间。
          <button
            type="button"
            onClick={() => {
              setPopoverOpen(false);
              void onCompactConversation();
            }}
            className="ml-1 underline font-medium"
          >
            立即压缩
          </button>
        </div>
      )}
      {budgetExhausted && (
        <div className="rounded-lg bg-error/10 px-3 py-2 text-[11px] text-error">
          当前会话预算已耗尽，普通对话和自动化任务都会停止继续消耗。
        </div>
      )}
      <div className="flex items-center gap-2 rounded-lg bg-muted/30 px-3 py-2 text-[11px] text-muted-foreground">
        <Settings className="h-3 w-3 shrink-0" />
        {budgetEnabled
          ? "token 用量达到预算后，这条会话会停止继续执行。"
          : "开启后可限制当前会话的 token 消耗上限。"}
      </div>
    </PopoverContent>
  );

  if (variant === "dropdown") {
    return (
      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={triggerButtonClass}
            aria-label="上下文与预算"
            title="上下文与预算"
          >
            <Gauge className="h-3.5 w-3.5" />
            <span className="tabular-nums">{contextPercentLabel}</span>
            {compactionJustFinished && (
              <span className="inline-flex items-center gap-0.5 rounded-full bg-success/10 px-1.5 py-0.5 text-[10px] font-medium text-success">
                <Sparkles className="h-3 w-3" />
                已压缩
              </span>
            )}
          </button>
        </PopoverTrigger>
        {popoverContent}
      </Popover>
    );
  }

  return (
    <div
      className="flex items-center gap-2 border-b border-border/50 bg-background px-3 py-2 text-[11px] text-muted-foreground"
      data-testid="token-usage-bar"
    >
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <span className="shrink-0 font-medium text-foreground">上下文</span>
        <div className="flex min-w-0 flex-1 items-center gap-1.5">
          <div className="h-1.5 min-w-10 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                barClass(contextPercent),
                isCompacting && "animate-pulse",
              )}
              style={{ width: `${contextPercent}%` }}
            />
          </div>
          {isCompacting ? (
            <span className="shrink-0 tabular-nums text-tertiary animate-pulse">
              正在压缩…
            </span>
          ) : compactionJustFinished ? (
            <span className="shrink-0 tabular-nums text-success">
              {formatTokens(compactionState?.tokens_before ?? stats.context_tokens)}
              {" → "}
              {formatTokens(compactionState?.tokens_after ?? stats.context_tokens)}
            </span>
          ) : (
            <>
              <span
                className="shrink-0 tabular-nums text-foreground"
                data-testid="context-usage-value"
                title={
                  stats.context_window
                    ? `${stats.context_tokens.toLocaleString()} / ${stats.context_window.toLocaleString()} tokens`
                    : `${stats.context_tokens.toLocaleString()} tokens`
                }
              >
                {contextValueLabel}
              </span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {contextPercentLabel}
              </span>
            </>
          )}
          {compactionJustFinished && (
            <span className="shrink-0 inline-flex items-center gap-0.5 rounded-full bg-success/10 px-1.5 py-0.5 text-[10px] font-medium text-success">
              <Sparkles className="h-3 w-3" />
              已压缩
            </span>
          )}
        </div>
      </div>

      {onCompactConversation && hasMessages && (
        <button
          type="button"
          onClick={() => {
            if (isCompacting || isRunning) return;
            void onCompactConversation();
          }}
          disabled={isCompacting || isRunning}
          className={compactButtonClass}
          title={
            isRunning
              ? "对话进行中，请等待完成后再压缩"
              : isCompacting
                ? "正在压缩上下文"
                : "压缩上下文"
          }
          aria-label={
            isRunning
              ? "对话进行中，请等待完成后再压缩"
              : isCompacting
                ? "正在压缩上下文"
                : "压缩上下文"
          }
          data-testid="token-bar-compact-conversation"
        >
          {isCompacting ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Minimize2 className="h-3.5 w-3.5" />
          )}
          <span className="hidden sm:inline">
            {isCompacting ? "压缩中" : isRunning ? "运行中" : "压缩"}
          </span>
        </button>
      )}
      <button
        type="button"
        onClick={() => {
          const appNavigate = (globalThis as typeof globalThis & {
            appNavigate?: (path: string) => void;
          }).appNavigate;
          if (appNavigate) {
            appNavigate("/dashboard");
          } else {
            globalThis.location.href = "/dashboard";
          }
        }}
        className="flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-tertiary/40 hover:bg-tertiary-container/50 hover:text-tertiary"
        title="Token 消耗面板"
      >
        <BarChart3 className="h-3.5 w-3.5" />
        <span className="hidden sm:inline">用量</span>
      </button>

      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={triggerButtonClass}
            aria-label="设置当前会话预算"
          >
            <Gauge className="h-3.5 w-3.5" />
            <span className="shrink-0">预算</span>
            {stats.token_budget ? (
              <>
                <div className="hidden h-1.5 w-10 overflow-hidden rounded-full bg-muted xl:block">
                  <div
                    className={barClass(budgetPercent)}
                    style={{ width: `${budgetPercent}%` }}
                  />
                </div>
                <span
                  className={cn(
                    "tabular-nums",
                    budgetExhausted && "text-error font-medium",
                  )}
                >
                  {budgetValueLabel}
                </span>
              </>
            ) : (
              <span className="tabular-nums text-muted-foreground/60">
                点击设置
              </span>
            )}
          </button>
        </PopoverTrigger>
        {popoverContent}
      </Popover>

    </div>
  );
}

export default TokenUsageBar;
