import { API_ENDPOINTS, getCurrentUserId } from "@/config/api";
import { apiRequest } from "@/lib/api/httpClient";

export type LLMSelectionScope = "global" | "workspace" | "session";
export type LLMInheritedScope = "global" | "workspace";

export interface LLMModelIdentitySummary {
  model_id: string | null;
  display_name: string | null;
  model_name: string | null;
  provider: string | null;
  provider_name: string | null;
}

export interface LLMModelScopeSelectionSummary {
  scope: LLMSelectionScope;
  configured_model_id: string | null;
  configured_missing: boolean;
  configured_display_name: string | null;
  configured_model_name: string | null;
  configured_provider: string | null;
  configured_provider_name: string | null;
  inherited_from: LLMInheritedScope | null;
  effective: LLMModelIdentitySummary;
}

export interface WorkspaceLLMSelectionSummary {
  workspace_id: string;
  global_scope: LLMModelScopeSelectionSummary;
  workspace_scope: LLMModelScopeSelectionSummary;
  effective: LLMModelIdentitySummary;
}

export interface SessionLLMSelectionSummary {
  session_id: string;
  workspace_id: string | null;
  global_scope: LLMModelScopeSelectionSummary;
  workspace_scope: LLMModelScopeSelectionSummary;
  session_scope: LLMModelScopeSelectionSummary;
  effective: LLMModelIdentitySummary;
}

export async function getSessionLLMSelection(
  sessionId: string,
  userId = getCurrentUserId(),
): Promise<SessionLLMSelectionSummary> {
  return apiRequest<SessionLLMSelectionSummary>(
    API_ENDPOINTS.SESSION_LLM_SELECTION(userId, sessionId),
    {
      cache: "no-store",
    },
  );
}

export async function updateSessionLLMSelection(
  sessionId: string,
  modelId: string | null,
  userId = getCurrentUserId(),
): Promise<SessionLLMSelectionSummary> {
  return apiRequest<SessionLLMSelectionSummary>(
    API_ENDPOINTS.SESSION_LLM_SELECTION(userId, sessionId),
    {
      method: "PUT",
      body: {
        model_id: modelId,
      },
    },
  );
}

export async function getWorkspaceLLMSelection(
  workspaceId: string,
): Promise<WorkspaceLLMSelectionSummary> {
  return apiRequest<WorkspaceLLMSelectionSummary>(
    API_ENDPOINTS.WORKSPACE_LLM_SELECTION(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function updateWorkspaceLLMSelection(
  workspaceId: string,
  modelId: string | null,
): Promise<WorkspaceLLMSelectionSummary> {
  return apiRequest<WorkspaceLLMSelectionSummary>(
    API_ENDPOINTS.WORKSPACE_LLM_SELECTION(workspaceId),
    {
      method: "PUT",
      body: {
        model_id: modelId,
      },
    },
  );
}
