export type BudgetStatus = "active" | "budget_limited";

export interface SessionBudgetState {
  token_budget: number | null;
  tokens_used: number;
  time_budget_seconds: number | null;
  time_used_seconds: number;
  status: BudgetStatus;
}

export interface SetSessionBudgetPayload {
  token_budget: number | null;
  time_budget_seconds?: number | null;
}

// Session Token 监控（聊天区指示器用）
export interface TokenStats {
  tokens_used: number;
  token_budget: number | null;
  context_tokens: number;
  context_window: number | null;
  context_usage_pct: number;
  budget_status: string;
}
