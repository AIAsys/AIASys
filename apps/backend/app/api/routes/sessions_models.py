"""Session API 请求/响应模型。

从 sessions.py 提取的 Pydantic 模型，供路由和 helpers 模块共用。
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.session import MessageContent, RecoveryPolicy
from app.models.task_profile import TaskExecutionPolicy


class CreateSessionRequest(BaseModel):
    """创建会话请求"""

    user_id: Optional[str] = Field(None, description="用户 ID（可选，优先使用认证信息）")
    session_id: str = Field(..., description="会话 ID")
    title: str = Field(default="新会话", description="会话标题")
    workspace_id: Optional[str] = Field(
        default=None,
        description="要绑定的工作区 ID；为空时自动创建一个同名工作区并绑定",
    )
    recovery_policy: Optional[RecoveryPolicy] = Field(
        default=None,
        description="执行恢复策略: discard/journal_only/manual_replay",
    )
    code_timeout: Optional[int] = Field(
        default=None,
        description="代码执行超时时间（秒）；为空时使用全局默认配置",
    )
    execution_policy: Optional[TaskExecutionPolicy] = Field(
        default=None,
        description="当前任务工作层运行行为策略；为空时使用系统默认值",
    )


class UpdateRecoveryPolicyRequest(BaseModel):
    recovery_policy: RecoveryPolicy = Field(
        ...,
        description="执行恢复策略: discard/journal_only/manual_replay",
    )


class ManualReplayRequest(BaseModel):
    selected_sequences: Optional[list[int]] = Field(
        default=None,
        description="显式选择要重放的 sequence 列表；当前版本只接受连续前缀",
    )
    upto_sequence: Optional[int] = Field(
        default=None,
        ge=1,
        description="仅重放到指定 sequence（含）",
    )
    include_failed: bool = Field(
        default=False,
        description="是否包含失败记录",
    )
    restart_runtime: bool = Field(
        default=True,
        description="重放前是否重启 runtime",
    )
    risk_acknowledged: bool = Field(
        default=False,
        description="是否已确认当前选择中可能重复产生副作用的风险",
    )


class RewriteMessageRequest(BaseModel):
    message_id: str = Field(..., min_length=1, description="要重写的用户消息 ID")
    content: str = Field(..., min_length=1, description="重写后的用户消息内容")
    preserve_attachments: bool = Field(
        default=True,
        description="第一版固定保留原附件引用",
    )
    confirm_drop_tail: bool = Field(
        default=False,
        description="是否确认删除目标消息之后的当前对话上下文",
    )


class SessionResponse(BaseModel):
    """会话响应"""

    session_id: str
    title: str
    created_at: str
    message_count: int = 0
    code_timeout: Optional[int] = None


class MessageRequest(BaseModel):
    """添加消息请求"""

    role: str = Field(..., description="消息角色: user/assistant/system")
    content: MessageContent = Field(..., description="消息内容")


class UpdateTitleRequest(BaseModel):
    """更新会话标题请求"""

    title: str = Field(..., description="新标题")


class UpdateTaskProfileRequest(BaseModel):
    execution_policy: Optional[TaskExecutionPolicy] = Field(
        default=None,
        description="当前任务工作层运行行为策略",
    )


class SetSessionBudgetRequest(BaseModel):
    token_budget: Optional[int] = Field(
        default=None, ge=1, description="token 预算上限，null 表示不限制"
    )
    time_budget_seconds: Optional[int] = Field(
        default=None, ge=1, description="时间预算上限（秒），null 表示不限制"
    )


class BudgetResponse(BaseModel):
    token_budget: Optional[int] = None
    tokens_used: int
    time_budget_seconds: Optional[int] = None
    time_used_seconds: int
    status: Literal["active", "budget_limited"]


class TokenStatsResponse(BaseModel):
    """Session Token 监控数据（聊天区指示器用）"""

    tokens_used: int = 0
    token_budget: Optional[int] = None
    context_tokens: int = 0
    context_window: Optional[int] = None  # 模型上下文窗口大小，null 表示未知
    context_usage_pct: float = 0.0  # 0-100
    budget_status: str = "active"


class CompactionEvent(BaseModel):
    """单次上下文压缩事件的指标。"""

    tier_used: Literal["tool_clear", "llm_summary", "none"] = Field(
        ..., description="使用的压缩层级"
    )
    compacted_count: int = Field(0, description="被压缩/清理的消息数量")
    preserved_count: int = Field(0, description="被保留的消息数量")
    tokens_before: int = Field(0, description="压缩前估算 token 数")
    tokens_after: int = Field(0, description="压缩后估算 token 数")
    saved_tokens: int = Field(0, description="节省的 token 数")
    saved_chars: Optional[int] = Field(None, description="Tier 1 节省的字符数")
    summary_tokens: Optional[int] = Field(None, description="LLM 摘要输出的 token 数")
    elapsed_ms: int = Field(0, description="耗时毫秒")


class CompactSessionResponse(BaseModel):
    """压缩会话响应。"""

    success: bool
    session: dict[str, Any] = Field(default_factory=dict)
    compaction: Optional[CompactionEvent] = None


# ---------------------------------------------------------------------------
# Monitor 相关模型
# ---------------------------------------------------------------------------


class MonitorInfoResponse(BaseModel):
    id: str
    command: str
    status: str
    exit_code: int | None
    mode: str = "notify"
    created_at: float
    completed_at: float | None


class MonitorSegment(BaseModel):
    index: int
    timestamp: str
    content: str
    is_stderr: bool


class MonitorListResponse(BaseModel):
    monitors: list[MonitorInfoResponse]


class MonitorDetailResponse(BaseModel):
    info: MonitorInfoResponse
    segments: list[MonitorSegment]


class MonitorSegmentsResponse(BaseModel):
    monitor_id: str
    segments: list[MonitorSegment]


class MonitorSpawnRequest(BaseModel):
    command: str
    description: str | None = None
    timeout_seconds: int | None = None
    cwd: str | None = None
    mode: str | None = "notify"


class MonitorSpawnResponse(BaseModel):
    monitor_id: str
    command: str
    status: str
    mode: str = "notify"
    created_at: float


class GlobalMonitorInfoResponse(BaseModel):
    id: str
    command: str
    status: str
    exit_code: int | None
    mode: str = "notify"
    created_at: float
    completed_at: float | None
    session_id: str
    session_key: str
    workspace_id: str
    workspace_title: str


class GlobalMonitorListResponse(BaseModel):
    monitors: list[GlobalMonitorInfoResponse]


class GlobalMonitorSummaryResponse(BaseModel):
    total: int
    running: int
    completed: int
    error: int
    killed: int
