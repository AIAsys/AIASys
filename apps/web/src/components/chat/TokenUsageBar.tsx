import { useCallback, useEffect, useRef, useState } from "react";
import { Gauge, Settings } from "lucide-react";
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
import type { TokenStats } from "@/types/sessionBudget";
import {
  getSessionTokenStats,
  setSessionBudget,
  clearSessionBudget,
} from "@/lib/api/sessionBudget";

interface TokenUsageBarProps {
  sessionId?: string | null;
  refreshSignal?: number | string;
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
}: TokenUsageBarProps) {
  const [stats, setStats] = useState<TokenStats | null>(null);
  const [budgetEnabled, setBudgetEnabled] = useState(false);
  const [tokenBudget, setTokenBudget] = useState("50000");
  const [isSaving, setIsSaving] = useState(false);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const requestSeqRef = useRef(0);
  const editingRef = useRef(false);

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
      if (requestSeqRef.current !== requestSeq) return;
      setStats(data);
      setBudgetEnabled(data.token_budget != null);
      // 只在 Popover 关闭时才同步后端值到输入框，避免覆盖用户正在编辑的内容
      if (data.token_budget && !editingRef.current) {
        setTokenBudget(String(data.token_budget));
      }
    } catch {
      // 保持已有 stats，避免预算条突然消失
    }
  }, [userId, sessionId]);

  useEffect(() => {
    void loadStats();
  }, [loadStats, refreshSignal]);

  if (!sessionId || !stats) return null;

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
      pct >= 90 ? "bg-error" : pct >= 70 ? "bg-warning" : "bg-success",
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
              className={barClass(contextPercent)}
              style={{ width: `${contextPercent}%` }}
            />
          </div>
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
        </div>
      </div>

      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            className={cn(
              "flex h-7 shrink-0 items-center gap-1 rounded-md border border-border bg-background px-2.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-tertiary/40 hover:bg-tertiary-container/50 hover:text-tertiary",
              budgetExhausted && "border-error/40 bg-error/10 text-error hover:text-error",
            )}
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
      </Popover>

    </div>
  );
}

export default TokenUsageBar;
