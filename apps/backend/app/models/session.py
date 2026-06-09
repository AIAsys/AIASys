"""
会话相关数据模型
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, model_serializer, model_validator

from app.models.task_profile import (
    TaskExecutionPolicy,
    normalize_execution_policy,
)
from app.services.agent.message_content import MessageContent

RecoveryPolicy = Literal["discard", "journal_only", "manual_replay"]
ExecutionRiskLevel = Literal["low", "medium", "high"]

AutoTaskSignalStatus = Literal["active", "paused", "completed"]


class AutoTaskSignal(BaseModel):
    """连续自动任务在单轮会话内写回的完成信号。"""

    auto_task_id: str = Field(..., description="关联的自动任务 ID")
    status: AutoTaskSignalStatus = Field(
        default="active",
        description="自动任务信号状态",
    )
    reason: Optional[str] = Field(default=None, description="暂停或完成说明")
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="信号创建时间",
    )
    updated_at: Optional[str] = Field(
        default=None,
        description="信号最后更新时间",
    )

    @model_validator(mode="after")
    def _update_timestamp(self) -> "AutoTaskSignal":
        if self.updated_at is None:
            self.updated_at = datetime.now().isoformat()
        return self


class SessionTaskItem(BaseModel):
    """会话内任务条目。"""

    id: str = Field(..., description="任务唯一标识")
    content: str = Field(..., description="任务描述")
    status: Literal["pending", "in_progress", "completed", "cancelled"] = Field(
        default="pending",
        description="任务状态",
    )
    dependencies: list[str] = Field(default_factory=list, description="依赖的任务 ID")
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="创建时间",
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="更新时间",
    )
    completed_at: Optional[str] = Field(default=None, description="完成时间")


class SessionPlanState(BaseModel):
    """会话内 plan 状态。"""

    mode: Literal["active", "inactive"] = Field(default="inactive")
    approval_status: Literal["draft", "pending_approval", "approved", "rejected"] = Field(
        default="draft",
    )
    current_plan_file: Optional[str] = Field(default=None)
    pre_plan_permission_mode: Optional[str] = Field(default=None)
    updated_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="更新时间",
    )


class SessionBudget(BaseModel):
    """Session 级独立预算控制。"""

    token_budget: Optional[int] = Field(
        default=None,
        ge=1,
        description="token 预算上限；null 表示不限制",
    )
    tokens_used: int = Field(default=0)
    time_budget_seconds: Optional[int] = Field(
        default=None,
        ge=1,
        description="时间预算上限（秒）；null 表示不限制",
    )
    time_used_seconds: int = Field(default=0)
    status: Literal["active", "budget_limited"] = Field(default="active")
    # 当前上下文占用的 token 估算值
    context_tokens: int = Field(default=0)

    def remaining_tokens(self) -> Optional[int]:
        if self.token_budget is None:
            return None
        return max(0, self.token_budget - self.tokens_used)

    def is_exhausted(self) -> bool:
        if self.token_budget is not None and self.tokens_used >= self.token_budget:
            return True
        if (
            self.time_budget_seconds is not None
            and self.time_used_seconds >= self.time_budget_seconds
        ):
            return True
        return False


class SessionCollaborationPolicy(BaseModel):
    """当前会话的协作节点运行策略。"""

    max_depth: int = Field(
        default=1,
        ge=1,
        le=5,
        description="协作节点最大派发深度；Host 为 0，一层协作节点为 1",
    )
    max_threads: Optional[int] = Field(
        default=None,
        ge=1,
        le=32,
        description="当前会话允许同时运行的协作节点数量；null 表示沿用运行时默认",
    )
    allow_nested_spawn: bool = Field(
        default=False,
        description="是否允许协作节点继续派发新的协作节点",
    )
    budget_policy: dict[str, Any] = Field(
        default_factory=dict,
        description="协作节点预算策略预留字段",
    )
    timeout_policy: dict[str, Any] = Field(
        default_factory=dict,
        description="协作节点超时策略预留字段",
    )
    stop_policy: dict[str, Any] = Field(
        default_factory=dict,
        description="协作节点停止策略预留字段",
    )

    @model_validator(mode="after")
    def _normalize_depth(self) -> "SessionCollaborationPolicy":
        if not self.allow_nested_spawn and self.max_depth > 1:
            # UI 可以先保存显式深度值，但运行态默认不开放嵌套派发。
            return self
        return self


class FileSnapshot(BaseModel):
    """文件快照（仅记录文件名列表）"""

    files: List[str] = Field(default_factory=list, description="文件路径列表")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="快照时间戳",
    )


class StructuredMessage(BaseModel):
    """结构化消息"""

    role: str = Field(..., description="消息角色: user/assistant/system")
    content: MessageContent = Field(..., description="消息内容")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="消息时间戳",
    )
    metadata: dict = Field(default_factory=dict, description="额外元数据")
    file_snapshot: Optional[FileSnapshot] = Field(None, description="当时的文件快照")


class ExecutionStep(BaseModel):
    """执行步骤"""

    step_type: str = Field(..., description="步骤类型: tool_call/tool_result/observation")
    tool_name: Optional[str] = Field(None, description="工具名称")
    input: Optional[Any] = Field(None, description="输入参数")
    output: Optional[Any] = Field(None, description="输出结果")
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
    )
    error: Optional[str] = Field(None, description="错误信息")


class VariableDigest(BaseModel):
    """代码执行后的变量变化摘要"""

    new_variables: List[str] = Field(default_factory=list, description="新增变量")
    mutated_variables: List[str] = Field(default_factory=list, description="变更变量")
    deleted_variables: List[str] = Field(default_factory=list, description="删除变量")


class ExecutionResultPreview(BaseModel):
    """执行结果预览"""

    type: str = Field(default="text", description="预览类型")
    text: str = Field(default="", description="文本预览内容")


class ExecutionOrigin(BaseModel):
    """执行来源信息"""

    source: str = Field(default="local_ipython_box", description="执行来源")
    tool_name: Optional[str] = Field(default=None, description="工具名称")
    request_id: Optional[str] = Field(default=None, description="请求标识")
    target_path: Optional[str] = Field(
        default=None,
        description="可选目标对象路径，例如 notebook 相对路径",
    )


class ExecutionRuntimeInfo(BaseModel):
    """执行运行时信息"""

    sandbox_mode: Optional[str] = Field(default=None, description="沙盒模式")
    env_id: Optional[str] = Field(default=None, description="环境 ID")


class ExecutionReplayRisk(BaseModel):
    """执行记录的重放风险摘要"""

    level: ExecutionRiskLevel = Field(default="low", description="风险等级")
    tags: List[str] = Field(default_factory=list, description="风险标签")
    reasons: List[str] = Field(default_factory=list, description="风险原因")
    has_side_effect_risk: bool = Field(
        default=False,
        description="是否包含可能重复产生副作用的步骤",
    )


class ExecutionRecord(BaseModel):
    """结构化执行记录"""

    record_id: str = Field(..., description="记录唯一标识")
    session_id: str = Field(..., description="会话 ID")
    project_id: Optional[str] = Field(default=None, description="项目 ID")
    run_id: Optional[str] = Field(default=None, description="运行 ID")
    attempt_id: Optional[str] = Field(default=None, description="尝试 ID")
    sequence: int = Field(..., description="会话内执行序号")
    origin: ExecutionOrigin = Field(default_factory=ExecutionOrigin, description="执行来源")
    runtime: ExecutionRuntimeInfo = Field(
        default_factory=ExecutionRuntimeInfo, description="运行时信息"
    )
    started_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="开始时间",
    )
    finished_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="结束时间",
    )
    status: str = Field(..., description="执行状态: completed/failed")
    language: str = Field(default="python", description="执行语言")
    code: str = Field(default="", description="执行代码")
    stdout_ref: Optional[str] = Field(default=None, description="stdout 产物引用")
    stderr_ref: Optional[str] = Field(default=None, description="stderr 产物引用")
    result_preview: ExecutionResultPreview = Field(
        default_factory=ExecutionResultPreview,
        description="结果摘要预览",
    )
    artifact_refs: List[str] = Field(default_factory=list, description="产物引用")
    variable_digest: VariableDigest = Field(
        default_factory=VariableDigest, description="变量变化摘要"
    )
    replay_risk: ExecutionReplayRisk = Field(
        default_factory=ExecutionReplayRisk,
        description="手动重放时的副作用风险摘要",
    )
    error: Optional[str] = Field(default=None, description="结构化错误信息")
    agent_config_snapshot: Optional[dict[str, Any]] = Field(
        default=None,
        description="本轮执行实际使用的 Agent 配置快照",
    )


class SessionSettingsSummaryResponse(BaseModel):
    """当前会话设置页读模型。"""

    user_id: str
    session_id: str
    workspace_id: Optional[str] = None
    generated_at: str
    agent_config: dict[str, Any] = Field(default_factory=dict)
    model_selection: dict[str, Any] = Field(default_factory=dict)
    expert_policy: dict[str, Any] = Field(default_factory=dict)
    memory: dict[str, Any] = Field(default_factory=dict)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    execution: dict[str, Any] = Field(default_factory=dict)


class SessionReferenceItem(BaseModel):
    reference_id: str
    reference_kind: Literal[
        "file",
        "resource_asset",
        "database_connector",
        "database_handle",
        "knowledge_base",
        "knowledge_graph",
        "expert",
        "capability",
        "tool",
    ]
    display_name: str
    description: Optional[str] = None
    scope: Literal["user", "workspace", "session", "runtime"] = "session"
    available: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionReferenceSearchResponse(BaseModel):
    user_id: str
    session_id: str
    workspace_id: Optional[str] = None
    query: str = ""
    items: list[SessionReferenceItem] = Field(default_factory=list)
    total: int = 0


class SessionReferenceResolveRequest(BaseModel):
    reference_ids: list[str] = Field(default_factory=list)


class SessionReferenceResolveResponse(BaseModel):
    user_id: str
    session_id: str
    workspace_id: Optional[str] = None
    resolved: list[SessionReferenceItem] = Field(default_factory=list)
    unresolved_reference_ids: list[str] = Field(default_factory=list)
    task_resource_context: dict[str, Any] = Field(default_factory=dict)


class SessionMetadata(BaseModel):
    """会话元数据（内部存储模型）"""

    schema_version: int = Field(default=1, description="数据格式版本")
    session_id: str = Field(..., description="会话唯一标识")
    title: str = Field(default="新会话", description="会话标题")
    created_at: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="创建时间",
    )
    updated_at: Optional[str] = Field(None, description="最后更新时间")
    message_count: int = Field(default=0, description="消息数量")
    agent_type: str = Field(default="analysis", description="Agent 类型")
    status: str = Field(default="draft", description="会话状态: draft/active/completed")
    completed_at: Optional[str] = Field(None, description="完成时间（当 status=completed 时记录）")
    completed_message_count: Optional[int] = Field(
        None, description="完成时消息数量，用于判断是否被新消息重新激活"
    )
    tags: List[str] = Field(default_factory=list, description="标签")
    env_id: Optional[str] = Field(None, description="会话绑定的运行环境ID")
    sandbox_mode: Optional[str] = Field(None, description="沙盒模式；当前主线仅支持 local")
    workspace_id: Optional[str] = Field(None, description="会话绑定的工作区ID")
    recovery_policy: RecoveryPolicy = Field(
        default="journal_only",
        description="执行恢复策略: discard/journal_only/manual_replay",
    )
    code_timeout: Optional[int] = Field(
        None,
        description="代码执行超时（秒）；None = 使用全局默认",
    )
    preferred_model_id: Optional[str] = Field(
        default=None,
        description="当前会话私有 LLM 模型覆盖；为空时继承工作区默认，再回退到全局默认",
    )

    execution_policy: TaskExecutionPolicy = Field(
        default_factory=TaskExecutionPolicy,
        description="当前任务工作层的运行行为策略",
    )
    enabled_expert_role_ids: list[str] | None = Field(
        default=None,
        description="当前会话显式启用的专家角色列表；为空表示继承当前目录中的全部角色",
    )
    expert_role_tool_ids: dict[str, list[str]] | None = Field(
        default=None,
        description="当前会话显式裁剪的专家工具子集；为空表示各角色继承系统上限工具",
    )
    collaboration_policy: SessionCollaborationPolicy = Field(
        default_factory=SessionCollaborationPolicy,
        description="当前会话协作节点运行策略",
    )
    authorization_mode: Optional[str] = Field(
        default=None,
        description="能力授权模式: manual/smart/auto/full_auto；None 表示继承工作区/全局默认",
    )

    # 项目协作相关字段（新命名体系）
    # 会话可见性控制
    exclude_from_user_history: bool = Field(default=False, description="是否从用户历史列表中隐藏")
    # 来源标记
    source: Optional[str] = Field(None, description="来源: auto_task/manual")
    conversation_type: Optional[str] = Field(
        default=None,
        description="会话类型: chat/hosting_agent/worker/orchestrator",
    )
    auto_task_id: Optional[str] = Field(None, description="创建此会话的自动任务 ID")
    automation_continuation_id: Optional[str] = Field(
        None,
        description="若由自动研究 continuation 创建，则记录 continuation ID",
    )
    automation_continuation_target_kind: Optional[str] = Field(
        None,
        description="若由自动研究 continuation 创建，则记录 continuation target_kind",
    )
    project_id: Optional[str] = Field(None, description="所属项目 ID")
    team_id: Optional[str] = Field(None, description="所属团队 ID")
    bound_lead_session_id: Optional[str] = Field(None, description="绑定的主控会话 ID")
    bound_host_session_id: Optional[str] = Field(
        None,
        description="若当前会话是托管会话，则记录它绑定的主控会话 ID",
    )
    auto_task_signal: Optional[AutoTaskSignal] = Field(
        default=None,
        description="连续自动任务在本轮会话中写回的状态信号",
    )
    tasks: list[SessionTaskItem] = Field(
        default_factory=list,
        description="当前会话内结构化任务清单",
    )
    plan_state: SessionPlanState = Field(
        default_factory=SessionPlanState,
        description="当前会话计划模式状态",
    )
    budget: Optional[SessionBudget] = Field(default=None, description="当前会话的独立预算控制")

    @model_validator(mode="after")
    def _hydrate_task_profile_defaults(self) -> SessionMetadata:
        self.execution_policy = normalize_execution_policy(
            self.execution_policy,
        )
        self.expert_role_tool_ids = _normalize_expert_role_tool_ids(self.expert_role_tool_ids)
        self.collaboration_policy = normalize_collaboration_policy(self.collaboration_policy)
        return self

    @model_serializer(mode="wrap")
    def _inject_schema_version(self, serializer, info) -> dict[str, Any]:
        data = serializer(self)
        data["_schema_version"] = data.pop("schema_version", 1)
        return data


class SessionHistory(BaseModel):
    """会话完整历史"""

    session_id: str
    user_id: str
    messages: List[StructuredMessage]
    execution_steps: List[ExecutionStep]
    created_at: str
    updated_at: str


def _normalize_expert_role_tool_ids(
    value: Any,
) -> dict[str, list[str]] | None:
    if value is None or not isinstance(value, dict):
        return None

    normalized: dict[str, list[str]] = {}
    for raw_role_id, raw_tool_ids in value.items():
        role_id = str(raw_role_id or "").strip()
        if not role_id or not isinstance(raw_tool_ids, list):
            continue

        tool_ids: list[str] = []
        seen_tool_ids: set[str] = set()
        for raw_tool_id in raw_tool_ids:
            tool_id = str(raw_tool_id or "").strip()
            if not tool_id or tool_id in seen_tool_ids:
                continue
            tool_ids.append(tool_id)
            seen_tool_ids.add(tool_id)

        if tool_ids or isinstance(raw_tool_ids, list):
            normalized[role_id] = tool_ids

    return normalized or None


def normalize_collaboration_policy(value: Any) -> SessionCollaborationPolicy:
    if isinstance(value, SessionCollaborationPolicy):
        return value
    if isinstance(value, dict):
        return SessionCollaborationPolicy(**value)
    return SessionCollaborationPolicy()
