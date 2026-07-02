from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from .message_protocol import InternalMessage


@dataclass(slots=True)
class LlmDelta:
    """标准化 LLM 流式输出 delta。"""

    content: str | None = None
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


@dataclass(slots=True)
class LlmChunk:
    """标准化 LLM 流式输出 chunk。"""

    delta: LlmDelta
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None


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
