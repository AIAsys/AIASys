import type { DatabaseType } from "@/types/databaseConnectors";
import type { TaskExecutionPolicySummary } from "@/types/autoTask";

export type SessionRuntimeStatus =
  | "ready"
  | "busy"
  | "not_started"
  | "released"
  | "refresh_required"
  | "failed"
  | "unknown"
  | string;

export interface SessionRuntimeSummary {
  runtime_kind?: string | null;
  display_name?: string | null;
  scope?: string | null;
  start_policy?: string | null;
  reuse_policy?: string | null;
  control_mode?: string | null;
  kernel_active?: boolean;
  status?: SessionRuntimeStatus | null;
  status_label?: string | null;
  runtime_busy?: boolean;
  env_id?: string | null;
  sandbox_mode?: string | null;
}

export type NewTaskStage =
  | "idle"
  | "selecting_environment"
  | "preparing_session"
  | "scanning_folder"
  | "copying_files"
  | "import_creating_workspace"
  | "creating_workspace"
  | "binding_environment"
  | "attaching_databases"
  | "waiting_runtime"
  | "activating_session"
  | "error";

export const NEW_TASK_STAGE_LABELS: Record<NewTaskStage, string> = {
  idle: "",
  selecting_environment: "",
  preparing_session: "正在准备初始对话",
  scanning_folder: "正在扫描文件夹",
  copying_files: "正在复制文件",
  import_creating_workspace: "正在初始化导入工作区",
  creating_workspace: "正在创建工作区",
  binding_environment: "正在绑定运行环境",
  attaching_databases: "正在挂载数据库连接",
  waiting_runtime: "正在等待运行时就绪",
  activating_session: "正在切换到新对话",
  error: "创建任务失败",
};

export interface NewTaskLifecycleState {
  stage: NewTaskStage;
  stageLabel: string;
  showProgress: boolean;
  isBusy: boolean;
  isError: boolean;
  errorMessage: string | null;
  progress?: number;
}

export interface WorkspaceRuntimeSummary {
  env_id?: string | null;
  sandbox_mode?: "local" | string | null;
  last_runtime_state?: string | null;
  runtime_summary?: SessionRuntimeSummary | null;
}

export interface ExecutionResourceGroup {
  python_env_id?: string | null;
  node_env_id?: string | null;
  docker_resource_id?: string | null;
}

export type WorkspaceRuntimeEnvironmentKind = "uv" | "registered_python" | "fnm";

export type WorkspaceRuntimeEnvironmentStatus =
  | "registered"
  | "ready"
  | "running"
  | "stopped"
  | "missing"
  | "unavailable"
  | "error"
  | string;

export interface WorkspaceRuntimeEnvCommandResult {
  ok: boolean;
  command: string[];
  cwd?: string | null;
  returncode?: number | null;
  stdout?: string;
  stderr?: string;
  error?: string | null;
}

export interface WorkspaceRuntimeEnvPackage {
  name: string;
  version: string;
}

export interface WorkspaceRuntimeEnvironment {
  env_id: string;
  kind: WorkspaceRuntimeEnvironmentKind;
  display_name: string;
  status: WorkspaceRuntimeEnvironmentStatus;
  active: boolean;
  material_path?: string | null;
  python_version?: string | null;
  python_executable?: string | null;
  node_version?: string | null;
  npm_version?: string | null;
  package_count: number;
  packages: WorkspaceRuntimeEnvPackage[];
  created_at?: string | null;
  updated_at?: string | null;
  last_error?: string | null;
  metadata?: Record<string, unknown>;
}

export interface WorkspaceContainerResource {
  container_id: string;
  name: string;
  image: string;
  docker_container_id?: string | null;
  container_name?: string | null;
  status: "running" | "stopped" | "created" | "missing" | "error";
  workspace_mount_path: string;
  command?: string | null;
  ports: Record<string, string>;
  env: Record<string, string>;
  labels: Record<string, string>;
  managed: boolean;
  auto_start: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  last_error?: string | null;
}

export interface WorkspaceContainerResourceRegistry {
  workspace_id: string;
  containers: WorkspaceContainerResource[];
  docker_available: boolean;
  total: number;
}

export interface RegisterWorkspaceContainerResourcePayload {
  containerId?: string;
  name?: string;
  image?: string;
  containerIdOrName?: string;
  workspaceMountPath?: string;
  createContainer?: boolean;
  autoStart?: boolean;
  command?: string;
  env?: Record<string, string>;
  labels?: Record<string, string>;
  ports?: Record<string, string>;
}

export interface ContainerResourceActionResponse {
  workspace_id: string;
  container: WorkspaceContainerResource;
  refresh_required?: boolean;
}

export interface ContainerLogsResponse {
  container_id: string;
  logs: string;
}

export interface WorkspaceRuntimeEnvironmentRegistry {
  workspace_id: string;
  default_env_id?: string | null;
  active_env_id?: string | null;
  registry_path: string;
  uv_available: boolean;
  envs: WorkspaceRuntimeEnvironment[];
  total: number;
}

export interface EnsureWorkspaceUvEnvPayload {
  envId?: string;
  displayName?: string;
  pythonVersion?: string | null;
  packages?: string[];
  createVenv?: boolean;
  sync?: boolean;
}

export interface RegisterWorkspacePythonEnvPayload {
  envId?: string | null;
  displayName?: string | null;
  pythonExecutable: string;
  sourceKernelName?: string | null;
  activate?: boolean;
}

export interface InstallWorkspacePackagesPayload {
  packages: string[];
  sync?: boolean;
}

export interface BindWorkspaceRuntimeEnvPayload {
  envId: string;
}

export interface WorkspaceRuntimeEnvActionResponse {
  workspace_id: string;
  env: WorkspaceRuntimeEnvironment;
  refresh_required: boolean;
  command_result?: WorkspaceRuntimeEnvCommandResult | null;
}

export interface WorkspaceRuntimeEnvInspection {
  workspace_id: string;
  env: WorkspaceRuntimeEnvironment;
  registry_path: string;
  material_files: Record<string, boolean>;
}

// ── Node.js / fnm 类型 ──

export type NodeRuntimeEnvStatus =
  | "registered"
  | "ready"
  | "running"
  | "stopped"
  | "missing"
  | "unavailable"
  | "error"
  | string;

export interface NodeRuntimeEnv {
  env_id: string;
  kind: "fnm" | "registered_node";
  display_name: string;
  status: NodeRuntimeEnvStatus;
  active: boolean;
  node_version: string | null;
  npm_version: string | null;
  package_count: number;
  packages: WorkspaceRuntimeEnvPackage[];
  created_at: string | null;
  updated_at: string | null;
  last_error: string | null;
  metadata: Record<string, unknown>;
}

export interface NodeRuntimeEnvRegistry {
  workspace_id: string;
  default_env_id?: string | null;
  active_env_id?: string | null;
  registry_path: string;
  fnm_available: boolean;
  envs: NodeRuntimeEnv[];
  total: number;
}

export interface NodeRuntimeEnvActionResponse {
  workspace_id: string;
  env?: NodeRuntimeEnv;
  refresh_required?: boolean;
  command_result?: WorkspaceRuntimeEnvCommandResult | null;
}

export interface NodeRuntimeActionResult {
  workspace_id: string;
  result: Record<string, unknown>;
}

export interface WorkspaceOverviewWorkspace {
  workspace_id: string;
  title: string;
  description?: string | null;
  created_at: string;
  updated_at: string;
  status: string;
  workspace_kind: "task" | "claw";
  execution_policy: TaskExecutionPolicySummary;
  runtime_binding?: {
    env_vars?: Record<string, string> | null;
    resources?: ExecutionResourceGroup | null;
  } | null;
  current_conversation_id?: string | null;
  conversation_count: number;
}

export interface WorkspaceOverviewSession {
  workspace_id: string;
  conversation_id: string;
  session_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  status: string;
  execution_policy: TaskExecutionPolicySummary;
  message_count: number;
  execution_record_count: number;
  last_execution_status?: string | null;
  last_execution_record_id?: string | null;
  source?: string | null;
  conversation_type?: string | null;
  bound_host_session_id?: string | null;
  is_current: boolean;
}

export interface WorkspaceOverviewRuntime {
  session_id?: string | null;
  env_id?: string | null;
  sandbox_mode?: string | null;
  last_runtime_state?: string | null;
  runtime_busy: boolean;
  can_start_runtime: boolean;
  can_stop_runtime: boolean;
  runtime_control_reason?: string | null;
  runtime_summary?: SessionRuntimeSummary | null;
}

export interface WorkspaceOverviewConfig {
  config_sync_state: "aligned" | "pending" | "unknown" | string;
  agent_config_effect: "next_run_only" | string;
  task_profile_effect: "next_run_only" | string;
  memory_effect: "next_run_only" | string;
  can_edit_agent_config_now: boolean;
  can_edit_task_profile_now: boolean;
  rebuild_required: boolean;
  rebuild_required_reasons: string[];
  current_agent_config_version?: string | null;
  applied_agent_config_version?: string | null;
  pending_agent_config_version?: string | null;
  current_capability_snapshot_version?: string | null;
  applied_capability_snapshot_version?: string | null;
  pending_capability_snapshot_version?: string | null;
  config_state_updated_at?: string | null;
  projection?: Record<string, unknown>;
}

export type WorkspaceOverviewResourceStatus =
  | "ready"
  | "empty"
  | "not_verified"
  | "degraded"
  | "unavailable";

export interface WorkspaceOverviewResourceBucket {
  resource_key: "mcp" | "knowledge_base" | "knowledge_graph" | "database" | "file";
  display_name: string;
  status: WorkspaceOverviewResourceStatus;
  user_asset_count: number;
  workspace_default_count: number;
  session_attached_count: number;
  runtime_available_count: number;
  configured: boolean;
  mounted: boolean;
  verified: boolean;
  available: boolean;
  stale: boolean;
  primary_action?: string | null;
  disabled_reason?: string | null;
  next_check_hint?: string | null;
  ids: string[];
  detail?: string | null;
  metadata?: Record<string, unknown>;
}

export interface WorkspaceOverviewVerificationSummary {
  status: "not_verified" | "passed" | "warning" | "failed" | "unknown" | string;
  checked_at?: string | null;
  resource_count: number;
  failed_count: number;
  warning_count: number;
}

export interface WorkspaceOverviewResources {
  mcp: WorkspaceOverviewResourceBucket;
  knowledge_base: WorkspaceOverviewResourceBucket;
  knowledge_graph: WorkspaceOverviewResourceBucket;
  database: WorkspaceOverviewResourceBucket;
  file: WorkspaceOverviewResourceBucket;
  verification: WorkspaceOverviewVerificationSummary;
}

export interface WorkspaceOverviewExperts {
  profile_name?: string | null;
  available_role_count: number;
  enabled_role_count: number;
  enabled_role_ids: string[];
  policy_effect: "next_run_only" | string;
  status: "ready" | "empty" | "unavailable" | string;
  detail?: string | null;
}

export interface WorkspaceOverviewArtifacts {
  workspace_file_count: number;
  artifact_file_count: number;
  execution_record_count: number;
  last_execution_status?: string | null;
  last_execution_record_id?: string | null;
}

export interface WorkspaceOverviewMemory {
  effect: "next_run_only" | string;
  has_memory?: boolean;
  document_count?: number;
  version?: string | null;
  snapshot_hash?: string | null;
  pending_snapshot_version?: string | null;
  preview?: Record<string, unknown>;
}

export interface WorkspaceOverviewResponse {
  generated_at: string;
  workspace: WorkspaceOverviewWorkspace;
  current_session?: WorkspaceOverviewSession | null;
  sessions: WorkspaceOverviewSession[];
  runtime: WorkspaceOverviewRuntime;
  config: WorkspaceOverviewConfig;
  resources: WorkspaceOverviewResources;
  experts: WorkspaceOverviewExperts;
  artifacts: WorkspaceOverviewArtifacts;
  memory: WorkspaceOverviewMemory;
}

export interface WorkspaceResourceLayerSummaryResponse {
  workspace_id: string;
  session_id?: string | null;
  generated_at: string;
  resources: WorkspaceOverviewResources;
}

export interface WorkspaceConversationRuntimeSummary {
  workspace_id: string;
  conversation_id: string;
  session_id: string;
  title: string;
  updated_at: string;
  source?: "auto_task" | "manual" | "automation" | "hosting" | string | null;
  conversation_type?: string | null;
  bound_host_session_id?: string | null;
  status: string;
  message_count: number;
  execution_record_count: number;
  last_runtime_state?: string | null;
  runtime_summary?: SessionRuntimeSummary | null;
  can_start_runtime: boolean;
  can_stop_runtime: boolean;
  runtime_control_reason?: string | null;
  is_current: boolean;
}

export interface WorkspaceConversationRuntimeListSummary {
  workspace_id: string;
  current_conversation_id?: string | null;
  conversation_runtimes: WorkspaceConversationRuntimeSummary[];
  total: number;
}

export interface WorkspaceConversationRuntimeActionResult {
  success: boolean;
  action: "start" | "stop";
  message?: string | null;
  workspace_id: string;
  conversation_id: string;
  session_id: string;
  runtime: WorkspaceConversationRuntimeSummary;
}

export interface SessionWorkspaceSummary {
  workspace_id: string;
  session_id: string;
  title: string;
  status: string;
  created_at: string;
  updated_at?: string | null;
  is_empty: boolean;
  message_count: number;
  workspace_file_count: number;
  has_execution_journal: boolean;
  execution_record_count: number;
  last_execution_status?: string | null;
  last_execution_record_id?: string | null;
  runtime: WorkspaceRuntimeSummary;
  recovery_policy?: string | null;
  code_timeout?: number | null;
  can_edit_agent_config_now: boolean;
  agent_config_effect: "next_run_only" | string;
  config_sync_state?: "aligned" | "pending" | string | null;
  rebuild_required?: boolean;
  rebuild_required_reasons?: string[];
  config_state_updated_at?: string | null;
  current_agent_config_version?: string | null;
  applied_agent_config_version?: string | null;
  pending_agent_config_version?: string | null;
  current_capability_snapshot_version?: string | null;
  applied_capability_snapshot_version?: string | null;
  pending_capability_snapshot_version?: string | null;
  workspace_capability_summary?: {
    skill_count?: number;
    skill_names?: string[];
    mcp_server_count?: number;
    enabled_mcp_server_count?: number;
    enabled_mcp_server_names?: string[];
    mcp_config_version?: number;
    mounted_knowledge_base_count?: number;
    mounted_knowledge_base_ids?: string[];
    mounted_knowledge_graph_count?: number;
    mounted_knowledge_graph_ids?: string[];
  } | null;
}

export type ResourceVerificationStatus =
  | "passed"
  | "failed"
  | "warning"
  | "skipped"
  | "unknown";

export interface ResourceVerificationCheck {
  status: ResourceVerificationStatus;
  summary: string;
  detail?: string | null;
  duration_ms?: number | null;
  error_code?: string | null;
}

export interface ResourceVerificationItem {
  resource_key: "mcp" | "knowledge_base" | "knowledge_graph" | "database" | "file";
  display_name: string;
  scope: "task" | "catalog" | "workspace" | "system";
  session_id?: string | null;
  mounted: boolean;
  mounted_summary: string;
  health: ResourceVerificationCheck;
  smoke: ResourceVerificationCheck;
  metadata?: Record<string, unknown>;
}

export interface WorkspaceResourceVerificationSummary {
  workspace_id: string;
  checked_at: string;
  session_id?: string | null;
  resources: ResourceVerificationItem[];
  verification_source?: "cache" | "computed";
  cache_hit?: boolean;
}

export interface WorkspaceKnowledgeBaseMountItem {
  id: string;
  name: string;
  document_count: number;
  mounted: boolean;
}

export interface WorkspaceKnowledgeBaseMountSummary {
  workspace_id: string;
  knowledge_base_ids: string[];
  mounted_knowledge_bases: WorkspaceKnowledgeBaseMountItem[];
  available_knowledge_bases: WorkspaceKnowledgeBaseMountItem[];
  missing_knowledge_base_ids: string[];
}

export interface WorkspaceDatabaseMountItem {
  connector_id: string;
  name: string;
  db_type: DatabaseType | string;
  readonly: boolean;
  mounted: boolean;
  last_test_status: string;
  connection_summary?: string | null;
}

export interface WorkspaceDatabaseMountSummary {
  workspace_id: string;
  connector_ids: string[];
  mounted_database_connectors: WorkspaceDatabaseMountItem[];
  available_database_connectors: WorkspaceDatabaseMountItem[];
  missing_connector_ids: string[];
}
