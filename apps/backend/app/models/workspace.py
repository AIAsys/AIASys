"""
任务工作区与对话投影模型
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.session import ExecutionRecord, RecoveryPolicy
from app.models.task_profile import TaskExecutionPolicy


class ExecutionResourceGroup(BaseModel):
    """工作区执行资源组：把 Python、Node.js、Docker 等运行时统一成可勾选组合。"""

    python_env_id: Optional[str] = Field(
        default=None,
        description="绑定的 Python 环境 ID（WorkspaceRuntimeEnv.env_id）",
    )
    node_env_id: Optional[str] = Field(
        default=None,
        description="绑定的 Node.js 环境 ID（NodeRuntimeEnv.env_id）",
    )
    docker_resource_id: Optional[str] = Field(
        default=None,
        description="绑定的 Docker 容器资源 ID",
    )

    @model_validator(mode="after")
    def _validate_docker_not_with_local(self) -> "ExecutionResourceGroup":
        """Docker 沙盒与本地 Python/Node 环境不叠加。"""
        if self.docker_resource_id and (self.python_env_id or self.node_env_id):
            raise ValueError("Docker 沙盒模式下不能同时绑定本地 Python/Node 环境")
        return self


class WorkspaceRuntimeBinding(BaseModel):
    """工作区运行时绑定：resources 是唯一真相源，sandbox_mode/env_id 为派生属性。"""

    model_config = ConfigDict(extra="ignore")

    env_vars: Optional[dict[str, str]] = Field(
        default=None,
        description="注入到执行环境的环境变量（Shell / Python Kernel / Notebook / Node）",
    )
    resources: ExecutionResourceGroup = Field(
        default_factory=ExecutionResourceGroup,
        description="执行资源组：工作区可勾选组合的 Python/Node/Docker 资源",
    )

    @property
    def sandbox_mode(self) -> Optional[str]:
        """从 resources 派生执行模式：docker / local / None。"""
        if self.resources.docker_resource_id:
            return "docker"
        if self.resources.python_env_id or self.resources.node_env_id:
            return "local"
        return None

    @property
    def env_id(self) -> Optional[str]:
        """从 resources 派生 Python 环境 ID（兼容旧消费方）。"""
        return self.resources.python_env_id

    def to_execution_summary(self) -> dict[str, Any]:
        """返回执行层需要的资源视图。"""
        return {
            "sandbox_mode": self.sandbox_mode,
            "env_id": self.env_id,
            "python_env_id": self.resources.python_env_id,
            "node_env_id": self.resources.node_env_id,
            "docker_resource_id": self.resources.docker_resource_id,
            "env_vars": self.env_vars,
        }


class CreateWorkspaceRequest(BaseModel):
    workspace_id: Optional[str] = Field(default=None, description="工作区 ID；为空时自动生成")
    title: str = Field(default="新任务", description="工作区标题")
    description: Optional[str] = Field(default=None, description="工作区描述")
    workspace_kind: Literal["task", "claw"] = Field(
        default="task",
        description="工作区类型：task（普通任务）、claw（远程会话）",
    )
    execution_policy: Optional[TaskExecutionPolicy] = Field(
        default=None,
        description="工作区默认运行行为策略；为空时使用系统默认值",
    )
    initial_conversation_id: Optional[str] = Field(
        default=None,
        description="首个对话 ID；为空时自动生成",
    )
    initial_conversation_title: str = Field(
        default="新对话",
        description="首个对话标题",
    )
    recovery_policy: Optional[RecoveryPolicy] = Field(
        default=None,
        description="执行恢复策略",
    )
    code_timeout: Optional[int] = Field(
        default=None,
        description="代码执行超时（秒）",
    )
    runtime_binding: Optional[WorkspaceRuntimeBinding] = Field(
        default=None,
        description="工作区默认执行绑定；为空表示新工作区不绑定 Python/沙盒环境，显式传入 workspace-default 时才创建并绑定 Python 环境",
    )
    template_id: Optional[str] = Field(
        default=None,
        description="模板 ID；选择模板后工作区将预置模板内容",
    )
    install_capabilities: Optional[list[str]] = Field(
        default=None,
        description="创建时自动安装的能力 ID 列表（统一能力层）；为 None 时按模板 recommended_capabilities 全装",
    )
    template_files: Optional[list[str]] = Field(
        default=None,
        description="从模板导入时只导入指定的文件路径列表；为 None 时导入模板全部文件",
    )
    source_folder_path: Optional[str] = Field(
        default=None,
        description="从本地文件夹导入时的源文件夹绝对路径（桌面版）",
    )
    temp_upload_id: Optional[str] = Field(
        default=None,
        description="Web 版文件夹上传后的临时上传 ID",
    )
    import_files: Optional[list[str]] = Field(
        default=None,
        description="从本地文件夹导入时只复制指定的相对路径列表；为 None 时复制全部预选文件",
    )


class FolderImportTreeItem(BaseModel):
    relative_path: str = Field(description="相对于源文件夹的相对路径")
    is_directory: bool = Field(default=False, description="是否为目录")
    size: Optional[int] = Field(default=None, description="文件大小（字节）；目录为 None")


class FolderImportPreviewResponse(BaseModel):
    source_path: str = Field(description="源文件夹绝对路径")
    files: list[FolderImportTreeItem] = Field(default_factory=list, description="完整文件树")
    excluded_files: list[str] = Field(default_factory=list, description="被排除规则过滤掉的路径")
    default_selected_files: list[str] = Field(default_factory=list, description="默认预选的路径")
    total_file_count: int = Field(default=0, description="文件总数")
    total_size_bytes: int = Field(default=0, description="预选文件总大小（字节）")


class FolderImportPreviewRequest(BaseModel):
    source_path: str = Field(description="源文件夹绝对路径")


class FolderImportProgressEvent(BaseModel):
    stage: Literal["scanning", "copying", "creating_workspace", "completed", "error"] = Field(
        default="scanning", description="当前阶段"
    )
    progress: int = Field(default=0, description="整体进度百分比（0-100）")
    message: str = Field(default="", description="当前阶段提示文本")
    workspace_id: Optional[str] = Field(default=None, description="完成时返回的工作区 ID")
    warnings: list[str] = Field(default_factory=list, description="非致命警告信息")


class UpdateWorkspaceRequest(BaseModel):
    title: Optional[str] = Field(default=None, description="工作区标题")
    description: Optional[str] = Field(default=None, description="工作区描述")
    execution_policy: Optional[TaskExecutionPolicy] = Field(
        default=None,
        description="工作区默认运行行为策略",
    )
    runtime_binding: Optional[WorkspaceRuntimeBinding] = Field(
        default=None,
        description="工作区默认执行绑定",
    )


class CreateConversationRequest(BaseModel):
    conversation_id: Optional[str] = Field(default=None, description="对话 ID；为空时自动生成")
    title: str = Field(default="新对话", description="对话标题")
    execution_policy: Optional[TaskExecutionPolicy] = Field(
        default=None,
        description="当前会话运行行为策略；为空时继承工作区默认",
    )
    branched_from_conversation_id: Optional[str] = Field(
        default=None,
        description="来源对话 ID；为空表示新空对话",
    )
    recovery_policy: Optional[RecoveryPolicy] = Field(
        default=None,
        description="执行恢复策略",
    )
    code_timeout: Optional[int] = Field(
        default=None,
        description="代码执行超时（秒）",
    )


class WorkspaceConversationSummary(BaseModel):
    workspace_id: str
    conversation_id: str
    session_id: str
    title: str
    created_at: str
    updated_at: str
    execution_policy: TaskExecutionPolicy = Field(default_factory=TaskExecutionPolicy)
    message_count: int = 0
    status: str = "draft"
    branched_from_conversation_id: Optional[str] = None
    last_execution_status: Optional[str] = None
    last_execution_record_id: Optional[str] = None
    execution_record_count: int = 0
    source: Optional[str] = None
    conversation_type: Optional[str] = None
    bound_host_session_id: Optional[str] = None
    auto_task_id: Optional[str] = None
    automation_continuation_id: Optional[str] = None
    automation_continuation_target_kind: Optional[str] = None


class WorkspaceSummary(BaseModel):
    workspace_id: str
    title: str
    description: Optional[str] = None
    created_at: str
    updated_at: str
    workspace_kind: Literal["task", "claw"] = "task"
    execution_policy: TaskExecutionPolicy = Field(default_factory=TaskExecutionPolicy)
    runtime_binding: WorkspaceRuntimeBinding = Field(
        default_factory=WorkspaceRuntimeBinding,
    )
    status: str = "active"
    current_conversation_id: Optional[str] = None
    conversation_count: int = 0
    current_conversation: Optional[WorkspaceConversationSummary] = None


class WorkspaceListItemResponse(WorkspaceSummary):
    conversations: list[WorkspaceConversationSummary] = Field(default_factory=list)


class WorkspaceDetailResponse(WorkspaceListItemResponse):
    warnings: list[str] = Field(
        default_factory=list, description="工作区创建或初始化时的非致命警告信息"
    )


class WorkspaceListResponse(BaseModel):
    workspaces: list[WorkspaceListItemResponse]
    total: int


class WorkspaceOverviewWorkspace(BaseModel):
    workspace_id: str
    title: str
    description: Optional[str] = None
    created_at: str
    updated_at: str
    status: str = "active"
    workspace_kind: Literal["task", "claw"] = "task"
    execution_policy: TaskExecutionPolicy = Field(default_factory=TaskExecutionPolicy)
    runtime_binding: WorkspaceRuntimeBinding = Field(default_factory=WorkspaceRuntimeBinding)
    current_conversation_id: Optional[str] = None
    conversation_count: int = 0


class WorkspaceOverviewSession(BaseModel):
    workspace_id: str
    conversation_id: str
    session_id: str
    title: str
    created_at: str
    updated_at: str
    status: str = "draft"
    execution_policy: TaskExecutionPolicy = Field(default_factory=TaskExecutionPolicy)
    message_count: int = 0
    execution_record_count: int = 0
    last_execution_status: Optional[str] = None
    last_execution_record_id: Optional[str] = None
    source: Optional[str] = None
    conversation_type: Optional[str] = None
    bound_host_session_id: Optional[str] = None
    is_current: bool = False


class WorkspaceOverviewRuntime(BaseModel):
    session_id: Optional[str] = None
    env_id: Optional[str] = None
    sandbox_mode: Optional[str] = None
    last_runtime_state: Optional[str] = None
    runtime_busy: bool = False
    can_start_runtime: bool = False
    can_stop_runtime: bool = False
    runtime_control_reason: Optional[str] = None
    runtime_summary: dict[str, Any] = Field(default_factory=dict)


class WorkspaceOverviewConfig(BaseModel):
    config_sync_state: Literal["aligned", "pending", "unknown"] = "unknown"
    agent_config_effect: Literal["next_run_only"] = "next_run_only"
    task_profile_effect: Literal["next_run_only"] = "next_run_only"
    memory_effect: Literal["next_run_only"] = "next_run_only"
    can_edit_agent_config_now: bool = False
    can_edit_task_profile_now: bool = False
    rebuild_required: bool = False
    rebuild_required_reasons: list[str] = Field(default_factory=list)
    current_agent_config_version: Optional[str] = None
    applied_agent_config_version: Optional[str] = None
    pending_agent_config_version: Optional[str] = None
    current_capability_snapshot_version: Optional[str] = None
    applied_capability_snapshot_version: Optional[str] = None
    pending_capability_snapshot_version: Optional[str] = None
    config_state_updated_at: Optional[str] = None
    projection: dict[str, Any] = Field(default_factory=dict)


class WorkspaceOverviewResourceBucket(BaseModel):
    resource_key: Literal["mcp", "knowledge_base", "knowledge_graph", "database", "file"]
    display_name: str
    status: Literal["ready", "empty", "not_verified", "degraded", "unavailable"] = "empty"
    user_asset_count: int = 0
    workspace_default_count: int = 0
    session_attached_count: int = 0
    runtime_available_count: int = 0
    configured: bool = False
    mounted: bool = False
    verified: bool = False
    available: bool = False
    stale: bool = False
    primary_action: Optional[str] = None
    disabled_reason: Optional[str] = None
    next_check_hint: Optional[str] = None
    ids: list[str] = Field(default_factory=list)
    detail: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceOverviewVerificationSummary(BaseModel):
    status: Literal["not_verified", "passed", "warning", "failed", "unknown"] = "not_verified"
    checked_at: Optional[str] = None
    resource_count: int = 0
    failed_count: int = 0
    warning_count: int = 0


class WorkspaceOverviewResources(BaseModel):
    mcp: WorkspaceOverviewResourceBucket
    knowledge_base: WorkspaceOverviewResourceBucket
    knowledge_graph: WorkspaceOverviewResourceBucket
    database: WorkspaceOverviewResourceBucket
    file: WorkspaceOverviewResourceBucket
    verification: WorkspaceOverviewVerificationSummary = Field(
        default_factory=WorkspaceOverviewVerificationSummary
    )


class WorkspaceOverviewExperts(BaseModel):
    profile_name: Optional[str] = None
    available_role_count: int = 0
    enabled_role_count: int = 0
    enabled_role_ids: list[str] = Field(default_factory=list)
    policy_effect: Literal["next_run_only"] = "next_run_only"
    status: Literal["ready", "empty", "unavailable"] = "empty"
    detail: Optional[str] = None


class WorkspaceOverviewArtifacts(BaseModel):
    workspace_file_count: int = 0
    artifact_file_count: int = 0
    execution_record_count: int = 0
    last_execution_status: Optional[str] = None
    last_execution_record_id: Optional[str] = None


class WorkspaceOverviewMemory(BaseModel):
    effect: Literal["next_run_only"] = "next_run_only"
    has_memory: bool = False
    document_count: int = 0
    version: Optional[str] = None
    snapshot_hash: Optional[str] = None
    pending_snapshot_version: Optional[str] = None
    preview: dict[str, Any] = Field(default_factory=dict)


class WorkspaceOverviewResponse(BaseModel):
    generated_at: str
    workspace: WorkspaceOverviewWorkspace
    current_session: Optional[WorkspaceOverviewSession] = None
    sessions: list[WorkspaceOverviewSession] = Field(default_factory=list)
    runtime: WorkspaceOverviewRuntime = Field(default_factory=WorkspaceOverviewRuntime)
    config: WorkspaceOverviewConfig = Field(default_factory=WorkspaceOverviewConfig)
    resources: WorkspaceOverviewResources
    experts: WorkspaceOverviewExperts = Field(default_factory=WorkspaceOverviewExperts)
    artifacts: WorkspaceOverviewArtifacts = Field(default_factory=WorkspaceOverviewArtifacts)
    memory: WorkspaceOverviewMemory = Field(default_factory=WorkspaceOverviewMemory)


class WorkspaceResourceLayerSummaryResponse(BaseModel):
    workspace_id: str
    session_id: Optional[str] = None
    generated_at: str
    resources: WorkspaceOverviewResources


class DeleteWorkspaceResponse(BaseModel):
    success: bool = True
    workspace_id: str


class ResourceVerificationCheck(BaseModel):
    status: Literal["passed", "failed", "warning", "skipped", "unknown"] = "unknown"
    summary: str
    detail: Optional[str] = None
    duration_ms: Optional[int] = None
    error_code: Optional[str] = None


class ResourceVerificationItem(BaseModel):
    resource_key: Literal["mcp", "knowledge_base", "knowledge_graph", "database", "file"]
    display_name: str
    scope: Literal["task", "catalog", "system"] = "task"
    session_id: Optional[str] = None
    mounted: bool = False
    mounted_summary: str
    health: ResourceVerificationCheck
    smoke: ResourceVerificationCheck
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceResourceVerificationResponse(BaseModel):
    workspace_id: str
    checked_at: str
    session_id: Optional[str] = None
    resources: list[ResourceVerificationItem] = Field(default_factory=list)
    verification_source: Literal["cache", "computed"] = "computed"
    cache_hit: bool = False


class WorkspaceMountedKnowledgeBaseSummary(BaseModel):
    id: str
    name: str
    document_count: int = 0
    mounted: bool = False


class WorkspaceKnowledgeBaseMountRequest(BaseModel):
    knowledge_base_ids: list[str] = Field(default_factory=list)


class WorkspaceKnowledgeBaseMountResponse(BaseModel):
    workspace_id: str
    knowledge_base_ids: list[str] = Field(default_factory=list)
    mounted_knowledge_bases: list[WorkspaceMountedKnowledgeBaseSummary] = Field(
        default_factory=list
    )
    available_knowledge_bases: list[WorkspaceMountedKnowledgeBaseSummary] = Field(
        default_factory=list
    )
    missing_knowledge_base_ids: list[str] = Field(default_factory=list)


class WorkspaceMountedDatabaseConnectorSummary(BaseModel):
    connector_id: str
    name: str
    db_type: str
    readonly: bool = True
    mounted: bool = False
    last_test_status: str = "untested"
    connection_summary: Optional[str] = None


class WorkspaceDatabaseMountRequest(BaseModel):
    connector_ids: list[str] = Field(default_factory=list)


class WorkspaceDatabaseMountResponse(BaseModel):
    workspace_id: str
    connector_ids: list[str] = Field(default_factory=list)
    mounted_database_connectors: list[WorkspaceMountedDatabaseConnectorSummary] = Field(
        default_factory=list
    )
    available_database_connectors: list[WorkspaceMountedDatabaseConnectorSummary] = Field(
        default_factory=list
    )
    missing_connector_ids: list[str] = Field(default_factory=list)


class ConversationListResponse(BaseModel):
    workspace_id: str
    conversations: list[WorkspaceConversationSummary]
    total: int


class ConversationRunsResponse(BaseModel):
    workspace_id: str
    conversation_id: str
    runs: list[ExecutionRecord]
    total: int


class WorkspaceConversationRuntimeSummary(BaseModel):
    workspace_id: str
    conversation_id: str
    session_id: str
    title: str
    updated_at: str
    source: Optional[str] = None
    conversation_type: Optional[str] = None
    bound_host_session_id: Optional[str] = None
    execution_policy: TaskExecutionPolicy = Field(default_factory=TaskExecutionPolicy)
    status: str = "draft"
    message_count: int = 0
    execution_record_count: int = 0
    last_runtime_state: Optional[str] = None
    runtime_summary: dict[str, Any] = Field(default_factory=dict)
    can_start_runtime: bool = False
    can_stop_runtime: bool = False
    runtime_control_reason: Optional[str] = None
    is_current: bool = False


class ConversationRuntimeListResponse(BaseModel):
    workspace_id: str
    current_conversation_id: Optional[str] = None
    conversation_runtimes: list[WorkspaceConversationRuntimeSummary] = Field(default_factory=list)
    total: int


class ConversationRuntimeActionResponse(BaseModel):
    success: bool = True
    action: Literal["start", "stop"]
    message: Optional[str] = None
    workspace_id: str
    conversation_id: str
    session_id: str
    runtime: WorkspaceConversationRuntimeSummary


class OrphanConversationCleanupCandidate(BaseModel):
    session_id: str
    path: str
    reason: str


class OrphanConversationCleanupResponse(BaseModel):
    user_id: str
    dry_run: bool
    deleted_count: int
    deleted_session_ids: list[str] = Field(default_factory=list)
    candidates: list[OrphanConversationCleanupCandidate] = Field(default_factory=list)
