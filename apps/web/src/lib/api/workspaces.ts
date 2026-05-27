import { API_ENDPOINTS } from "@/config/api";
import {
  DEFAULT_CONVERSATION_TITLE,
  getDefaultConversationTitle,
} from "@/lib/conversationTitles";
import { apiRequest } from "@/lib/api/httpClient";
import type {
  TaskWorkspaceSummary,
  WorkspaceRuntimeBindingSummary,
  WorkspaceConversationSummary,
} from "@/pages/DataAnalysisPage/types";
import type {
  GlobalAutoTaskSummaryResponse,
  GlobalAutoTaskListResponse,
  WorkspaceAutoTask,
  WorkspaceAutoTaskRunNowResponse,
  WorkspaceAutoTaskUpsertPayload,
  WorkspaceAutoTaskListResponse,
  WorkspaceTriggerEventListResponse,
} from "@/types/autoTask";
import type {
  WorkspaceConversationRuntimeActionResult,
  WorkspaceConversationRuntimeListSummary,
  WorkspaceDatabaseMountSummary,
  WorkspaceRuntimeEnvActionResponse,
  WorkspaceRuntimeEnvInspection,
  WorkspaceRuntimeEnvironmentRegistry,
  EnsureWorkspaceUvEnvPayload,
  RegisterWorkspacePythonEnvPayload,
  InstallWorkspacePackagesPayload,
  BindWorkspaceRuntimeEnvPayload,
  WorkspaceKnowledgeBaseMountSummary,
  WorkspaceOverviewResponse,
  WorkspaceResourceLayerSummaryResponse,
  WorkspaceResourceVerificationSummary,
  WorkspaceContainerResourceRegistry,
  RegisterWorkspaceContainerResourcePayload,
  ContainerResourceActionResponse,
  ContainerLogsResponse,
} from "@/types/workspace";
import type { TaskExecutionPolicySummary } from "@/types/autoTask";

interface WorkspaceListResponse {
  workspaces: TaskWorkspaceSummary[];
  total: number;
}

interface WorkspaceDetailResponse extends TaskWorkspaceSummary {
  conversations: WorkspaceConversationSummary[];
}

interface DeleteWorkspaceResponse {
  success: boolean;
  workspace_id: string;
}

function appendQuery(
  url: string,
  params: Record<string, string | null | undefined>,
): string {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (!value) {
      return;
    }
    search.set(key, value);
  });
  const query = search.toString();
  return query ? `${url}?${query}` : url;
}

export interface CapabilityDeclaration {
  capability_id: string;
  kind: "skill_pack" | "mcp_server" | "subagent" | "native_tool";
  required: boolean;
  auto_activate: boolean;
  config?: Record<string, unknown>;
}

export interface CreateWorkspacePayload {
  workspaceId?: string;
  title?: string;
  description?: string;
  workspaceKind?: "task" | "claw";
  initialConversationId?: string;
  initialConversationTitle?: string;
  codeTimeout?: number;
  runtimeBinding?: WorkspaceRuntimeBindingSummary | null;
  executionPolicy?: TaskExecutionPolicySummary | null;
  templateId?: string;
  installCapabilities?: string[];
  templateFiles?: string[];
}

export interface CreateConversationPayload {
  conversationId?: string;
  title?: string;
  branchedFromConversationId?: string;
  codeTimeout?: number;
}

export interface UpdateWorkspacePayload {
  title?: string;
  description?: string;
  runtimeBinding?: WorkspaceRuntimeBindingSummary | null;
  executionPolicy?: TaskExecutionPolicySummary | null;
}

function normalizeWorkspaceConversation(
  conversation: WorkspaceConversationSummary,
): WorkspaceConversationSummary {
  return {
    ...conversation,
    title: conversation.title || "",
  };
}

function normalizeWorkspaceSummary<T extends TaskWorkspaceSummary>(workspace: T): T {
  return {
    ...workspace,
    current_conversation: workspace.current_conversation
      ? normalizeWorkspaceConversation(workspace.current_conversation)
      : workspace.current_conversation,
    conversations: Array.isArray(workspace.conversations)
      ? workspace.conversations.map(normalizeWorkspaceConversation)
      : workspace.conversations,
  };
}

export async function listTaskWorkspaces(): Promise<TaskWorkspaceSummary[]> {
  const data = await apiRequest<WorkspaceListResponse>(API_ENDPOINTS.WORKSPACES_LIST, {
    cache: "no-store",
  });
  return Array.isArray(data.workspaces)
    ? data.workspaces.map((workspace) => normalizeWorkspaceSummary(workspace))
    : [];
}

export interface TemplateFileItem {
  relative_path: string;
  content: string;
  source_path?: string;
}

export interface WorkspaceTemplateItem {
  template_id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  default_title: string;
  default_description: string;
  initial_conversation_title: string;
  env_kind: string;
  is_builtin?: boolean;
  env_vars?: Record<string, string>;
  recommended_skills: string[];
  recommended_mcps: string[];
  recommended_capabilities: CapabilityDeclaration[];
  files: TemplateFileItem[];
}

export interface WorkspaceTemplateListResponse {
  templates: WorkspaceTemplateItem[];
  total: number;
}

export async function listWorkspaceTemplates(
  installedOnly: boolean = false,
): Promise<WorkspaceTemplateItem[]> {
  const url = installedOnly
    ? `${API_ENDPOINTS.WORKSPACE_TEMPLATES_LIST}?installed_only=true`
    : API_ENDPOINTS.WORKSPACE_TEMPLATES_LIST;
  const data = await apiRequest<WorkspaceTemplateListResponse>(
    url,
    { cache: "no-store", timeoutMs: 10000 },
  );
  return Array.isArray(data.templates) ? data.templates : [];
}

export async function getWorkspaceTemplate(templateId: string): Promise<WorkspaceTemplateItem | null> {
  const data = await apiRequest<WorkspaceTemplateItem>(
    API_ENDPOINTS.WORKSPACE_TEMPLATE_DETAIL(templateId),
    { cache: "no-store", timeoutMs: 10000 },
  );
  return data ?? null;
}

export async function deleteWorkspaceTemplate(templateId: string): Promise<{ template_id: string; deleted: boolean }> {
  return apiRequest<{ template_id: string; deleted: boolean }>(
    API_ENDPOINTS.WORKSPACE_TEMPLATE_DELETE(templateId),
    { method: "DELETE", timeoutMs: 15000 },
  );
}

export interface ExportWorkspaceTemplatePayload {
  name: string;
  description?: string;
  icon?: string;
  category?: string;
  templateId?: string;
  files?: string[];
  includeEnvVars?: boolean;
}

export async function exportWorkspaceAsTemplate(
  workspaceId: string,
  payload: ExportWorkspaceTemplatePayload,
): Promise<WorkspaceTemplateItem> {
  const data = await apiRequest<WorkspaceTemplateItem>(
    API_ENDPOINTS.WORKSPACE_TEMPLATE_EXPORT(workspaceId),
    {
      method: "POST",
      timeoutMs: 15000,
      body: {
        name: payload.name,
        description: payload.description,
        icon: payload.icon,
        category: payload.category,
        template_id: payload.templateId,
        files: payload.files,
        include_env_vars: payload.includeEnvVars,
      },
    },
  );
  return data;
}

export async function createTaskWorkspace(
  payload: CreateWorkspacePayload,
): Promise<WorkspaceDetailResponse> {
  const response = await apiRequest<WorkspaceDetailResponse>(
    API_ENDPOINTS.WORKSPACES_CREATE,
    {
      method: "POST",
      body: {
        workspace_id: payload.workspaceId,
        title: payload.title ?? "新任务",
        description: payload.description,
        workspace_kind: payload.workspaceKind,
        initial_conversation_id: payload.initialConversationId,
        initial_conversation_title:
          payload.initialConversationTitle ?? DEFAULT_CONVERSATION_TITLE,
        code_timeout: payload.codeTimeout,
        runtime_binding: payload.runtimeBinding,
        execution_policy: payload.executionPolicy,
        template_id: payload.templateId,
        install_capabilities: payload.installCapabilities,
      },
    },
  );
  return normalizeWorkspaceSummary(response);
}

export async function getTaskWorkspace(
  workspaceId: string,
): Promise<WorkspaceDetailResponse> {
  const response = await apiRequest<WorkspaceDetailResponse>(
    API_ENDPOINTS.WORKSPACE_DETAIL(workspaceId),
    {
      cache: "no-store",
    },
  );
  return normalizeWorkspaceSummary(response);
}

export async function getWorkspaceOverview(
  workspaceId: string,
): Promise<WorkspaceOverviewResponse> {
  return apiRequest<WorkspaceOverviewResponse>(
    API_ENDPOINTS.WORKSPACE_OVERVIEW(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function getWorkspaceResourceLayers(
  workspaceId: string,
): Promise<WorkspaceResourceLayerSummaryResponse> {
  return apiRequest<WorkspaceResourceLayerSummaryResponse>(
    API_ENDPOINTS.WORKSPACE_RESOURCE_LAYERS(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function getWorkspaceResourceVerification(
  workspaceId: string,
  options?: { refresh?: boolean },
): Promise<WorkspaceResourceVerificationSummary> {
  return apiRequest<WorkspaceResourceVerificationSummary>(
    appendQuery(API_ENDPOINTS.WORKSPACE_RESOURCE_VERIFICATION(workspaceId), {
      refresh: options?.refresh ? "true" : undefined,
    }),
    {
      cache: "no-store",
    },
  );
}

export async function getWorkspaceRuntimeEnvironments(
  workspaceId: string,
  options?: { inspect?: boolean },
): Promise<WorkspaceRuntimeEnvironmentRegistry> {
  return apiRequest<WorkspaceRuntimeEnvironmentRegistry>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENTS(workspaceId),
    {
      cache: "no-store",
      query: {
        inspect: options?.inspect === false ? "false" : "true",
      },
    },
  );
}

export async function ensureWorkspaceUvEnvironment(
  workspaceId: string,
  payload: EnsureWorkspaceUvEnvPayload,
): Promise<WorkspaceRuntimeEnvActionResponse> {
  return apiRequest<WorkspaceRuntimeEnvActionResponse>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENT_UV(workspaceId),
    {
      method: "POST",
      body: {
        env_id: payload.envId,
        display_name: payload.displayName,
        python_version: payload.pythonVersion,
        packages: payload.packages ?? [],
        create_venv: payload.createVenv ?? false,
        sync: payload.sync ?? false,
      },
      timeoutMs: 120000,
    },
  );
}

export async function registerWorkspacePythonEnvironment(
  workspaceId: string,
  payload: RegisterWorkspacePythonEnvPayload,
): Promise<WorkspaceRuntimeEnvActionResponse> {
  return apiRequest<WorkspaceRuntimeEnvActionResponse>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENT_REGISTERED_PYTHON(workspaceId),
    {
      method: "POST",
      body: {
        env_id: payload.envId,
        display_name: payload.displayName,
        python_executable: payload.pythonExecutable,
        source_kernel_name: payload.sourceKernelName,
        activate: payload.activate ?? false,
      },
      timeoutMs: 120000,
    },
  );
}

export async function installWorkspaceRuntimePackages(
  workspaceId: string,
  envId: string,
  payload: InstallWorkspacePackagesPayload,
): Promise<WorkspaceRuntimeEnvActionResponse> {
  return apiRequest<WorkspaceRuntimeEnvActionResponse>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENT_PACKAGES(workspaceId, envId),
    {
      method: "POST",
      body: {
        env_id: envId,
        packages: payload.packages,
        sync: payload.sync ?? true,
      },
      timeoutMs: 300000,
    },
  );
}

export async function bindWorkspaceRuntimeEnvironment(
  workspaceId: string,
  payload: BindWorkspaceRuntimeEnvPayload,
): Promise<WorkspaceRuntimeEnvActionResponse> {
  return apiRequest<WorkspaceRuntimeEnvActionResponse>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENT_ACTIVE(workspaceId),
    {
      method: "POST",
      body: {
        env_id: payload.envId,
      },
    },
  );
}

export async function unregisterWorkspaceRuntimeEnvironment(
  workspaceId: string,
  envId: string,
): Promise<WorkspaceRuntimeEnvActionResponse> {
  return apiRequest<WorkspaceRuntimeEnvActionResponse>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENT(workspaceId, envId),
    {
      method: "DELETE",
    },
  );
}

export async function inspectWorkspaceRuntimeEnvironment(
  workspaceId: string,
  envId: string,
): Promise<WorkspaceRuntimeEnvInspection> {
  return apiRequest<WorkspaceRuntimeEnvInspection>(
    API_ENDPOINTS.WORKSPACE_RUNTIME_ENVIRONMENT(workspaceId, envId),
    {
      cache: "no-store",
    },
  );
}

// --- Docker 沙盒 API ---

export async function getWorkspaceContainerResources(
  workspaceId: string,
): Promise<WorkspaceContainerResourceRegistry> {
  return apiRequest<WorkspaceContainerResourceRegistry>(
    API_ENDPOINTS.WORKSPACE_CONTAINER_RESOURCES(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function registerWorkspaceContainerResource(
  workspaceId: string,
  payload: RegisterWorkspaceContainerResourcePayload,
): Promise<ContainerResourceActionResponse> {
  return apiRequest<ContainerResourceActionResponse>(
    API_ENDPOINTS.WORKSPACE_CONTAINER_RESOURCES(workspaceId),
    {
      method: "POST",
      body: {
        container_id: payload.containerId,
        name: payload.name,
        image: payload.image,
        container_id_or_name: payload.containerIdOrName,
        workspace_mount_path: payload.workspaceMountPath ?? "/workspace",
        create_container: payload.createContainer ?? false,
        auto_start: payload.autoStart ?? false,
        command: payload.command,
        env: payload.env ?? {},
        labels: payload.labels ?? {},
        ports: payload.ports ?? {},
      },
      timeoutMs: 120000,
    },
  );
}

export async function deleteWorkspaceContainerResource(
  workspaceId: string,
  containerId: string,
): Promise<ContainerResourceActionResponse> {
  return apiRequest<ContainerResourceActionResponse>(
    API_ENDPOINTS.WORKSPACE_CONTAINER_RESOURCE(workspaceId, containerId),
    {
      method: "DELETE",
    },
  );
}

export async function startWorkspaceContainerResource(
  workspaceId: string,
  containerId: string,
): Promise<ContainerResourceActionResponse> {
  return apiRequest<ContainerResourceActionResponse>(
    API_ENDPOINTS.WORKSPACE_CONTAINER_RESOURCE_START(workspaceId, containerId),
    {
      method: "POST",
    },
  );
}

export async function stopWorkspaceContainerResource(
  workspaceId: string,
  containerId: string,
): Promise<ContainerResourceActionResponse> {
  return apiRequest<ContainerResourceActionResponse>(
    API_ENDPOINTS.WORKSPACE_CONTAINER_RESOURCE_STOP(workspaceId, containerId),
    {
      method: "POST",
    },
  );
}

export async function getWorkspaceContainerResourceLogs(
  workspaceId: string,
  containerId: string,
): Promise<ContainerLogsResponse> {
  return apiRequest<ContainerLogsResponse>(
    API_ENDPOINTS.WORKSPACE_CONTAINER_RESOURCE_LOGS(workspaceId, containerId),
    {
      cache: "no-store",
    },
  );
}

export async function getWorkspaceDatabaseMounts(
  workspaceId: string,
): Promise<WorkspaceDatabaseMountSummary> {
  return apiRequest<WorkspaceDatabaseMountSummary>(
    API_ENDPOINTS.WORKSPACE_DATABASE_CONNECTORS(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function updateWorkspaceDatabaseMounts(
  workspaceId: string,
  connectorIds: string[],
): Promise<WorkspaceDatabaseMountSummary> {
  return apiRequest<WorkspaceDatabaseMountSummary>(
    API_ENDPOINTS.WORKSPACE_DATABASE_CONNECTORS(workspaceId),
    {
      method: "PUT",
      body: {
        connector_ids: connectorIds,
      },
    },
  );
}

export async function getWorkspaceKnowledgeBaseMounts(
  workspaceId: string,
): Promise<WorkspaceKnowledgeBaseMountSummary> {
  return apiRequest<WorkspaceKnowledgeBaseMountSummary>(
    API_ENDPOINTS.WORKSPACE_KNOWLEDGE_BASES(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function updateWorkspaceKnowledgeBaseMounts(
  workspaceId: string,
  knowledgeBaseIds: string[],
): Promise<WorkspaceKnowledgeBaseMountSummary> {
  return apiRequest<WorkspaceKnowledgeBaseMountSummary>(
    API_ENDPOINTS.WORKSPACE_KNOWLEDGE_BASES(workspaceId),
    {
      method: "PUT",
      body: {
        knowledge_base_ids: knowledgeBaseIds,
      },
    },
  );
}

export async function updateTaskWorkspace(
  workspaceId: string,
  payload: UpdateWorkspacePayload,
): Promise<WorkspaceDetailResponse> {
  const body: Record<string, unknown> = {};
  if (payload.title !== undefined) {
    body.title = payload.title;
  }
  if (payload.description !== undefined) {
    body.description = payload.description;
  }
  if (payload.runtimeBinding !== undefined) {
    body.runtime_binding = payload.runtimeBinding;
  }
  if (payload.executionPolicy !== undefined) {
    body.execution_policy = payload.executionPolicy;
  }
  const response = await apiRequest<WorkspaceDetailResponse>(
    API_ENDPOINTS.WORKSPACE_DETAIL(workspaceId),
    {
      method: "PATCH",
      body,
    },
  );
  return normalizeWorkspaceSummary(response);
}

export async function deleteWorkspace(
  apiBaseUrl: string,
  workspaceId: string,
): Promise<DeleteWorkspaceResponse> {
  return apiRequest<DeleteWorkspaceResponse>(
    `${apiBaseUrl}${API_ENDPOINTS.WORKSPACE_DETAIL(workspaceId)}`,
    {
      method: "DELETE",
    },
  );
}

export async function deleteAllWorkspaces(
  apiBaseUrl: string,
  workspaceIds: string[],
): Promise<{ deleted: number; failed: number; errors: string[] }> {
  let deleted = 0;
  let failed = 0;
  const errors: string[] = [];

  await Promise.all(
    workspaceIds.map(async (workspaceId) => {
      try {
        await deleteWorkspace(apiBaseUrl, workspaceId);
        deleted += 1;
      } catch (error) {
        failed += 1;
        const message = error instanceof Error ? error.message : String(error);
        errors.push(message);
      }
    }),
  );

  return { deleted, failed, errors };
}

export async function createWorkspaceConversation(
  workspaceId: string,
  payload: CreateConversationPayload,
): Promise<WorkspaceConversationSummary> {
  const response = await apiRequest<WorkspaceConversationSummary>(
    API_ENDPOINTS.WORKSPACE_CONVERSATIONS(workspaceId),
    {
      method: "POST",
      body: {
        conversation_id: payload.conversationId,
        title:
          payload.title ??
          getDefaultConversationTitle(payload.branchedFromConversationId),
        branched_from_conversation_id: payload.branchedFromConversationId,
        code_timeout: payload.codeTimeout,
      },
    },
  );
  return normalizeWorkspaceConversation(response);
}

export async function getWorkspaceConversationRuntimes(
  workspaceId: string,
): Promise<WorkspaceConversationRuntimeListSummary> {
  return apiRequest<WorkspaceConversationRuntimeListSummary>(
    API_ENDPOINTS.WORKSPACE_CONVERSATION_RUNTIMES(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function startWorkspaceConversationRuntime(
  workspaceId: string,
  conversationId: string,
): Promise<WorkspaceConversationRuntimeActionResult> {
  return apiRequest<WorkspaceConversationRuntimeActionResult>(
    API_ENDPOINTS.WORKSPACE_CONVERSATION_RUNTIME_START(workspaceId, conversationId),
    {
      method: "POST",
    },
  );
}

export async function stopWorkspaceConversationRuntime(
  workspaceId: string,
  conversationId: string,
): Promise<WorkspaceConversationRuntimeActionResult> {
  return apiRequest<WorkspaceConversationRuntimeActionResult>(
    API_ENDPOINTS.WORKSPACE_CONVERSATION_RUNTIME_STOP(workspaceId, conversationId),
    {
      method: "POST",
    },
  );
}

export async function getWorkspaceResearchTriggerEvents(
  workspaceId: string,
  _options?: { sessionId?: string | null },
): Promise<WorkspaceTriggerEventListResponse> {
  return {
    workspace_id: workspaceId,
    trigger_events_path: "",
    trigger_events: [],
  };
}

export async function getWorkspaceAutoTasks(
  workspaceId: string,
): Promise<WorkspaceAutoTaskListResponse> {
  return apiRequest<WorkspaceAutoTaskListResponse>(
    API_ENDPOINTS.WORKSPACE_AUTO_TASKS(workspaceId),
    {
      cache: "no-store",
    },
  );
}

export async function createWorkspaceAutoTask(
  workspaceId: string,
  payload: WorkspaceAutoTaskUpsertPayload,
): Promise<WorkspaceAutoTask> {
  return apiRequest<WorkspaceAutoTask>(
    API_ENDPOINTS.WORKSPACE_AUTO_TASKS(workspaceId),
    {
      method: "POST",
      body: payload,
    },
  );
}

export async function updateWorkspaceAutoTask(
  workspaceId: string,
  taskId: string,
  payload: Partial<WorkspaceAutoTaskUpsertPayload>,
): Promise<WorkspaceAutoTask> {
  return apiRequest<WorkspaceAutoTask>(
    API_ENDPOINTS.WORKSPACE_AUTO_TASK(workspaceId, taskId),
    {
      method: "PUT",
      body: payload,
    },
  );
}

export async function deleteWorkspaceAutoTask(
  workspaceId: string,
  taskId: string,
): Promise<{ task_id: string; deleted: boolean }> {
  return apiRequest<{ task_id: string; deleted: boolean }>(
    API_ENDPOINTS.WORKSPACE_AUTO_TASK(workspaceId, taskId),
    {
      method: "DELETE",
    },
  );
}

export async function runWorkspaceAutoTaskNow(
  workspaceId: string,
  taskId: string,
): Promise<WorkspaceAutoTaskRunNowResponse> {
  return apiRequest<WorkspaceAutoTaskRunNowResponse>(
    API_ENDPOINTS.WORKSPACE_AUTO_TASK_RUN(workspaceId, taskId),
    {
      method: "POST",
    },
  );
}

export async function getGlobalAutoTasks(): Promise<GlobalAutoTaskListResponse> {
  return apiRequest<GlobalAutoTaskListResponse>(
    API_ENDPOINTS.AUTO_TASKS_ALL,
    {
      cache: "no-store",
    },
  );
}

export async function getGlobalAutoTasksSummary(): Promise<GlobalAutoTaskSummaryResponse> {
  return apiRequest<GlobalAutoTaskSummaryResponse>(
    API_ENDPOINTS.AUTO_TASKS_SUMMARY,
    {
      cache: "no-store",
    },
  );
}
