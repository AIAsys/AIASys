/** Capability Confirmation API
 *
 * 对应后端 /api/{user_id}/{session_id}/approvals/* 接口
 */

import { apiRequest } from "./httpClient";

export interface ResolveCapabilityRequest {
  approved: boolean;
  feedback?: string;
  scope?: "once" | "session";
}

export interface ResolveCapabilityResponse {
  success: boolean;
  message: string;
}

export interface PendingCapabilityRecord {
  tool_call_id: string;
  tool_name: string;
  arguments: Record<string, unknown>;
  prompt: string;
  status: string;
  created_at: string;
  subagent_name?: string;
  agent_id?: string;
}

export interface PendingCapabilitiesResponse {
  pending: PendingCapabilityRecord[];
}

export async function resolveCapabilityConfirmation(
  userId: string,
  sessionId: string,
  toolCallId: string,
  payload: ResolveCapabilityRequest,
  agentId?: string,
): Promise<ResolveCapabilityResponse> {
  const query = agentId ? `?agent_id=${encodeURIComponent(agentId)}` : "";
  return apiRequest(
    `/api/${userId}/${sessionId}/approvals/${toolCallId}${query}`,
    {
      method: "POST",
      body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
    },
  );
}

export async function listPendingCapabilityConfirmations(
  userId: string,
  sessionId: string,
): Promise<PendingCapabilitiesResponse> {
  return apiRequest(
    `/api/${userId}/${sessionId}/approvals/pending`,
    { method: "GET" },
  );
}
