from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any, Literal

from .message_protocol import InternalMessage

logger = logging.getLogger(__name__)

# 归一化停止原因。各协议原生值语义不一（OpenAI length = Anthropic max_tokens =
# Gemini MAX_TOKENS；Responses 在工具调用场景只报 completed），循环层只消费本枚举，
# 不再裸判 provider 原始字符串。原始值另存 LlmChunk.raw_finish_reason 作为逃生舱。
FinishReason = Literal[
    "completed",  # 正常结束
    "tool_calls",  # 需要执行工具后继续
    "truncated",  # 输出长度受限被截断，可续写
    "filtered",  # 被内容安全策略拦截
    "paused",  # provider 主动暂停轮次（Anthropic pause_turn）
    "other",  # 未识别值，配合 raw_finish_reason 诊断
]

_OPENAI_FINISH_REASON_MAP: dict[str, FinishReason] = {
    "stop": "completed",
    "length": "truncated",
    "tool_calls": "tool_calls",
    "function_call": "tool_calls",
    "content_filter": "filtered",
}

_ANTHROPIC_STOP_REASON_MAP: dict[str, FinishReason] = {
    "end_turn": "completed",
    "stop_sequence": "completed",
    "max_tokens": "truncated",
    "tool_use": "tool_calls",
    "pause_turn": "paused",
    "refusal": "filtered",
}


def normalize_openai_finish_reason(raw: str | None) -> FinishReason | None:
    """OpenAI Chat Completions finish_reason → 归一化枚举。"""
    if raw is None:
        return None
    return _OPENAI_FINISH_REASON_MAP.get(str(raw), "other")


def normalize_anthropic_stop_reason(raw: str | None) -> FinishReason | None:
    """Anthropic stop_reason → 归一化枚举。"""
    if raw is None:
        return None
    return _ANTHROPIC_STOP_REASON_MAP.get(str(raw), "other")


_VALID_FINISH_REASONS: frozenset[str] = frozenset(FinishReason.__args__)


@dataclass(slots=True)
class LlmDelta:
    """标准化 LLM 流式输出 delta。"""

    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    # Anthropic thinking 块的 signature。原样透传、原样回灌，绝不伪造。
    # Responses 的 reasoning.encrypted_content 尚未接入（见 message_protocol 同名字段注释）。
    reasoning_signature: str | None = None
    # Anthropic redacted_thinking 块的 data：内容不可读，回灌时必须作为独立的
    # {"type":"redacted_thinking","data":...} 块发出，不能塞进 thinking.signature
    # （类型错位会被校验拒绝，且会覆盖同一轮的真签名）。故与上一字段分开承载。
    reasoning_redacted_data: str | None = None


@dataclass(slots=True)
class LlmChunk:
    """标准化 LLM 流式输出 chunk。"""

    delta: LlmDelta
    finish_reason: FinishReason | None = None
    usage: dict[str, Any] | None = None
    # provider 原始停止值，仅用于诊断与日志，不参与循环控制流。
    raw_finish_reason: str | None = None

    def __post_init__(self) -> None:
        # 护栏：finish_reason 直接驱动 ReAct 循环的继续/续写/终止，
        # provider 适配器若漏做归一化，写错的值会静默改变控制流。
        # 这里把非法值降级为 other 并保留原始值，让问题暴露在日志里而非行为里。
        if self.finish_reason is None or self.finish_reason in _VALID_FINISH_REASONS:
            return
        logger.warning(
            "provider 适配器返回了未归一化的 finish_reason=%r，已降级为 other。"
            "请在 client 侧调用 normalize_* 函数。",
            self.finish_reason,
        )
        if self.raw_finish_reason is None:
            self.raw_finish_reason = str(self.finish_reason)
        self.finish_reason = "other"


@dataclass(slots=True)
class LlmRequestOptions:
    """单次 LLM 请求的跨协议运行参数。"""

    thinking_enabled: bool = False
    thinking_effort: str | None = None
    thinking_budget_tokens: int | None = None
    thinking_disabled: bool = False


class BaseLlmClient(ABC):
    """多协议 LLM Client 抽象基类。"""

    @abstractmethod
    async def chat_stream(
        self,
        messages: list[InternalMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None = None,
    ) -> AsyncGenerator[LlmChunk, None]:
        """流式对话，统一输出 LlmChunk。"""
        ...

    @abstractmethod
    async def aclose(self) -> None:
        """关闭客户端资源。"""
        ...
