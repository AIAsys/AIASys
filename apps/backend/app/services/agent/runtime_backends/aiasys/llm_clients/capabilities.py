"""Provider 能力声明模型。

每个 provider 通过 ProviderCapabilities 在一处声明自己的所有特殊行为，
消除散落在各处的 isinstance 检查、URL 字符串匹配等 provider 检测逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class ProviderCapabilities:
    """Provider 级别的静态能力声明，由每个 client 类在注册时提供。

    所有字段都有合理默认值，新增 provider 只需声明与默认值不同的能力即可。
    """

    # -- 连接与认证 --
    custom_headers: dict[str, str] | None = None
    """静态的额外 HTTP headers（如特定 User-Agent）"""
    custom_headers_builder: Callable[..., dict[str, str]] | None = None
    """动态 header 构建函数（如 Kimi Coding 的 device_id 生成）。
    接受可选的 base_url 参数用于判断端点类型。
    优先级高于 custom_headers，两者会被合并（custom_headers 作为 base）。"""

    # -- 流式行为 --
    supports_stream_options: bool = True
    """是否支持 stream_options.include_usage（某些兼容服务商会拒绝此参数）"""
    usage_in_stream_chunk: bool = True
    """usage 是否随 stream chunk 返回。
    False 表示需要额外调用获取（如 Anthropic 的 get_final_message()）。"""
    usage_field_mapping: dict[str, str] | None = None
    """usage 字段名映射，将 provider 原生字段名映射到标准化名称。
    如 {"prompt_tokens": "input_tokens", "completion_tokens": "output_tokens"}。
    标准化后 client 输出的 usage 统一使用 input_tokens / output_tokens 作为主键。"""

    # -- Thinking/Reasoning --
    supports_thinking: bool = False
    thinking_format: str | None = None
    """thinking 参数格式：'effort' (OpenAI reasoning_effort) |
    'budget' (Anthropic legacy budget_tokens) | 'adaptive' (Anthropic 新版 adaptive)"""
    thinking_effort_levels: list[str] | None = None
    """支持的 effort 级别列表，如 ['low', 'medium', 'high']"""
    reasoning_key: str = "reasoning_content"
    """stream delta 中 reasoning 内容的字段名。不同 provider 可能用不同字段名。"""
    reasoning_format: str | None = None
    """厂商特有的 reasoning 格式控制参数值（透传到 extra_body）。"""

    # -- Tool 行为 --
    tool_strategy: str = "search"
    """默认 tool 策略：'passthrough' | 'deferred' | 'search'"""
    supports_parallel_tool_calls: bool = True
    supports_tool_search: bool = True

    # -- Tool Call 解析 --
    tool_call_parser: str | None = None
    """当结构化 tool_calls 缺失时，优先使用的 parser 名称"""
    tool_call_parsers_fallback: list[str] | None = None
    """fallback parser 链（primary parser 失败后按顺序尝试）"""

    # -- 消息格式 --
    system_message_format: str = "message"
    """system prompt 格式：'message' (作为独立消息) | 'separate' (作为独立参数，如 Anthropic)"""

    # -- 其他 --
    requires_base_url_trailing_slash_cleanup: bool = False
    """是否需要清理 base_url 尾部路径（如 Anthropic SDK 自动追加 /v1/messages，
    需要避免 base_url/v1 被拼成 /v1/v1/messages）"""
    max_tokens_override_for_thinking: bool = False
    """开启 thinking 时是否需要把 max_tokens 改为 budget + thinking_tokens"""
    force_temperature_for_thinking: float | None = None
    """开启 thinking 时是否强制覆盖 temperature（如 Anthropic legacy extended thinking 要求 temp=1）"""  # noqa: E501

    # -- 版本检测 --
    version_detector: Callable[[str], dict[str, Any]] | None = None
    """模型版本检测函数，输入 model 名，返回能力覆盖 dict。
    用于处理同一 provider 内不同模型版本的能力差异（如 Claude 4.6+ 支持 adaptive thinking）。"""

    # -- 通用标记 --
    is_coding_only: bool = False
    """是否为纯代码/编码专用 provider（如 Kimi Coding API）。
    GraphRAG 等非编码场景应跳过此类 provider。"""
