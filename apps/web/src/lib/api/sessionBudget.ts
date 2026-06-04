import type {
  SessionBudgetState,
  SetSessionBudgetPayload,
  TokenStats,
} from "@/types/sessionBudget";
import { apiRequest } from "@/lib/api/httpClient";

export async function setSessionBudget(
  userId: string,
  sessionId: string,
  payload: SetSessionBudgetPayload,
): Promise<void> {
  await apiRequest<{ success: boolean }>(`/api/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/budget`, {
    method: "PUT",
    body: payload,
  });
}

export async function clearSessionBudget(
  userId: string,
  sessionId: string,
): Promise<void> {
  await apiRequest<{ success: boolean }>(`/api/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/budget`, {
    method: "DELETE",
  });
}

export async function getSessionBudget(
  userId: string,
  sessionId: string,
): Promise<SessionBudgetState | null> {
  return apiRequest<SessionBudgetState | null>(
    `/api/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/budget`,
    { cache: "no-store" },
  );
}

export async function getSessionTokenStats(
  userId: string,
  sessionId: string,
): Promise<TokenStats> {
  return apiRequest<TokenStats>(
    `/api/${encodeURIComponent(userId)}/${encodeURIComponent(sessionId)}/tokens`,
    { cache: "no-store" },
  );
}
