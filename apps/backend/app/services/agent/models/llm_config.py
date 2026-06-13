"""
AIASys 自有的 LLM 配置模型，替代上游 runtime config 对象。
"""

from pydantic import BaseModel, Field, model_validator


class LoopControl(BaseModel):
    """
    对齐当前 runtime backend 所需的最小 loop_control 字段集。
    """

    max_steps_per_turn: int = 500
    max_retries_per_step: int = 3
    reserved_context_size: int = 50000
    compaction_trigger_ratio: float = 0.85
    max_preserved_messages: int = Field(
        default=2,
        description="压缩时保留的最近 user/assistant 消息条数",
        ge=0,
    )
    max_preserved_tokens: int = Field(
        default=20000,
        description="压缩时保留的最近消息总 token 上限（与 max_preserved_messages 同时生效）",
        ge=0,
    )
    max_summary_tokens: int = Field(
        default=2000,
        description="LLM 生成摘要时的最大输出 token 数",
        gt=0,
    )
    tool_snip_max_chars: int = Field(
        default=1000,
        description="保留窗口内 tool 消息超过此长度则截断（0 表示不截断）",
        ge=0,
    )
    keep_tool_context_turns: int = Field(
        default=2,
        description="保留最近 N 轮 user/assistant 轮次内的完整 tool 结果，更旧的 tool 结果在 pre-turn 阶段被清零",
        ge=0,
    )
    enable_pre_turn_clearing: bool = Field(
        default=True,
        description="是否开启每次 LLM 调用前的 tool 结果清零（Tier 1 零成本压缩）",
    )
    enable_compaction_verification: bool = Field(
        default=False,
        description="是否在 LLM 摘要后运行轻量级验证 probe",
    )
    effective_context_window_percent: float = Field(
        default=95.0,
        description="有效上下文窗口百分比，为系统提示、工具 schema 和模型输出留余量",
        ge=50.0,
        le=100.0,
    )


class LlmProviderConfig(BaseModel):
    """LLM provider 配置项。"""

    type: str | None = None
    protocol: str | None = Field(
        default=None,
        description="API 协议: openai_chat_completions | openai_responses | anthropic_messages | codex",
    )
    base_url: str | None = None
    api_key: str | None = None
    api_keys: list[str] | None = Field(
        default=None,
        description="同一 provider 的多个 API key，支持耗尽时自动轮换",
    )
    model_prefix: str | None = None
    region: str | None = None
    reasoning_key: str | None = None
    reasoning_format: str | None = None

    @model_validator(mode="after")
    def _infer_protocol_from_type(self) -> "LlmProviderConfig":
        """当 protocol 缺失时，把当前协议型 type 作为 protocol。"""
        if self.protocol:
            return self
        self.protocol = self.type or "openai_chat_completions"
        return self


class LlmModelConfig(BaseModel):
    """LLM model 配置项。"""

    model: str | None = None
    provider: str | None = None
    max_context_size: int | None = None
    capabilities: list[str] | None = None
    api_key: str | None = None
    base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    thinking_effort: str | None = None


class AiasysLlmConfig(BaseModel):
    """
    AIASys runtime 层使用的 LLM 统一配置。
    """

    default_model: str
    default_thinking: bool = False
    providers: dict[str, LlmProviderConfig] = Field(default_factory=dict)
    models: dict[str, LlmModelConfig] = Field(default_factory=dict)
    loop_control: LoopControl = Field(default_factory=LoopControl)
    fallback_order: list[str] = Field(
        default_factory=list,
        description="Provider fallback 优先级列表（provider_id 列表）",
    )
    task_models: dict[str, str] = Field(
        default_factory=dict,
        description="任务类型到模型ID的映射，如 {'compaction': 'gemini-flash'}",
    )
