from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any

from .base import BaseLlmClient, LlmChunk, LlmDelta, LlmRequestOptions
from .message_protocol import (
    InternalMessage,
    to_anthropic_messages,
    to_anthropic_tools,
)

logger = logging.getLogger(__name__)

# Adaptive thinking was introduced with Opus 4.6 / Sonnet 4.6.
_ADAPTIVE_MIN_VERSION: tuple[int, int] = (4, 6)
_FAMILY_VERSION_RE = re.compile(r"(?:opus|sonnet|haiku)[.-](\d+)[.-](\d{1,2})(?!\d)")
_ADAPTIVE_MARKERS: tuple[str, ...] = ("mythos",)


def _supports_adaptive_thinking(model: str) -> bool:
    """检测模型是否支持 adaptive thinking（Opus 4.6+ / Sonnet 4.6+ / Mythos）。"""
    m = model.lower()
    if any(marker in m for marker in _ADAPTIVE_MARKERS):
        return True
    match = _FAMILY_VERSION_RE.search(m)
    if not match:
        return False
    major = int(match.group(1))
    minor = int(match.group(2))
    return (major, minor) >= _ADAPTIVE_MIN_VERSION


def _is_opus_4_7(model: str) -> bool:
    """Opus 4.7 特指支持 xhigh effort 的模型。"""
    m = model.lower()
    return "opus-4-7" in m or "opus-4.7" in m


def _clamp_effort(effort: str, model: str) -> str:
    """将 effort clamp 到模型支持的最高级别。"""
    if effort == "off":
        return effort
    if _is_opus_4_7(model):
        supported = {"low", "medium", "high", "xhigh", "max"}
    elif _supports_adaptive_thinking(model):
        supported = {"low", "medium", "high", "max"}
    else:
        supported = {"low", "medium", "high"}
    if effort in supported:
        return effort
    return "high"


def _supports_effort_param(model: str) -> bool:
    """模型是否接受 output_config.effort 参数。"""
    if _supports_adaptive_thinking(model):
        return True
    m = model.lower()
    return "opus-4-5" in m or "opus-4.5" in m


def _effort_to_budget(effort: str) -> int:
    """将 effort 映射到 legacy thinking 的 budget_tokens。"""
    return {"low": 1024, "medium": 4096, "high": 32000}.get(effort, 4096)


class AnthropicChatClient(BaseLlmClient):
    """基于官方 anthropic.AsyncAnthropic 的流式客户端。

    将 Anthropic Messages API 的输出统一转换为 LlmChunk 格式。
    支持 adaptive thinking（Opus 4.6+ / Sonnet 4.6+）和 legacy thinking。
    支持 thinking / reasoning_content / tool_use。
    """

    def __init__(self, api_key: str, base_url: str | None, model: str):
        self.model = model.strip()
        self._base_url = (base_url or "").strip()
        self._tool_use_blocks: dict[int, dict[str, Any]] = {}
        try:
            import anthropic as _anthropic
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required. "
                "Install it with: pip install 'anthropic>=0.39.0'"
            ) from exc

        kwargs: dict[str, Any] = {"api_key": api_key.strip(), "timeout": 900.0}
        if base_url:
            # anthropic SDK 会自动在 base_url 后拼接 /v1/messages，
            # 如果用户配置的 base_url 已经以 /v1 结尾，需要去掉，避免变成 /v1/v1/messages
            base_url = base_url.rstrip("/")
            if base_url.endswith("/v1"):
                base_url = base_url[:-3]
            kwargs["base_url"] = base_url
        self._client = _anthropic.AsyncAnthropic(**kwargs)

    async def chat_stream(
        self,
        messages: list[InternalMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None = None,
    ) -> AsyncGenerator[LlmChunk, None]:
        self._tool_use_blocks = {}
        system_msg, anthropic_messages = self._convert_messages(messages)
        anthropic_tools = self._convert_tools(tools) if tools else None

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens if max_tokens is not None else 32000,
        }
        if system_msg:
            kwargs["system"] = system_msg
        if anthropic_tools:
            kwargs["tools"] = anthropic_tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if request_options and request_options.thinking_enabled:
            raw_effort = (request_options.thinking_effort or "high").strip().lower()
            effort = _clamp_effort(raw_effort, self.model)

            if _supports_adaptive_thinking(self.model):
                # Opus 4.6+ / Sonnet 4.6+ / Mythos: adaptive thinking
                # display: "summarized" 在 Opus 4.7+ 是必需的（默认已变为 omitted）
                kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
                kwargs["output_config"] = {"effort": effort}
            else:
                # Pre-4.6 models: legacy budget-based thinking
                budget = max(
                    int(request_options.thinking_budget_tokens or _effort_to_budget(effort)),
                    1024,
                )
                kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
                kwargs["max_tokens"] = max(
                    int(kwargs.get("max_tokens") or 8192),
                    budget + 2048,
                )
                if self._is_native_anthropic_endpoint():
                    # Legacy extended thinking requires temperature=1 on older models.
                    kwargs["temperature"] = 1
                if _supports_effort_param(self.model):
                    kwargs["output_config"] = {"effort": effort}

        async with self._client.messages.stream(**kwargs) as stream:
            async for event in stream:
                chunk = self._normalize_event(event)
                if chunk is not None:
                    yield chunk

            # Final usage chunk
            final = await stream.get_final_message()
            if final.usage is not None:
                yield LlmChunk(
                    delta=LlmDelta(),
                    finish_reason="stop",
                    usage={
                        "input_tokens": getattr(final.usage, "input_tokens", 0),
                        "output_tokens": getattr(final.usage, "output_tokens", 0),
                        "prompt_tokens": getattr(final.usage, "input_tokens", 0),
                        "completion_tokens": getattr(final.usage, "output_tokens", 0),
                    },
                )

    def _normalize_event(self, event: Any) -> LlmChunk | None:
        """将 Anthropic stream event 转为 LlmChunk。"""
        event_type = getattr(event, "type", None)

        if event_type == "content_block_start":
            content_block = getattr(event, "content_block", None)
            block_type = getattr(content_block, "type", None)
            if block_type == "thinking":
                # 捕获 thinking 块的初始内容（含 signature）
                thinking_text = getattr(content_block, "thinking", "") or ""
                return LlmChunk(
                    delta=LlmDelta(reasoning_content=thinking_text),
                )
            if block_type == "tool_use":
                index = int(getattr(event, "index", 0) or 0)
                tool_id = str(getattr(content_block, "id", "") or "")
                tool_name = str(getattr(content_block, "name", "") or "")
                raw_input = getattr(content_block, "input", None)
                arguments = ""
                if raw_input not in (None, "", {}, []):
                    arguments = (
                        raw_input
                        if isinstance(raw_input, str)
                        else json.dumps(raw_input, ensure_ascii=False)
                    )
                self._tool_use_blocks[index] = {
                    "id": tool_id,
                    "name": tool_name,
                }
                return LlmChunk(
                    delta=LlmDelta(
                        tool_calls=[
                            {
                                "index": index,
                                "id": tool_id,
                                "type": "function",
                                "function": {
                                    "name": tool_name,
                                    "arguments": arguments,
                                },
                            }
                        ]
                    ),
                )

        if event_type == "content_block_delta":
            delta = event.delta
            delta_type = getattr(delta, "type", None)

            if delta_type == "text_delta":
                return LlmChunk(
                    delta=LlmDelta(content=getattr(delta, "text", None)),
                )
            if delta_type == "thinking_delta":
                return LlmChunk(
                    delta=LlmDelta(reasoning_content=getattr(delta, "thinking", None)),
                )
            if delta_type == "input_json_delta":
                index = int(getattr(event, "index", 0) or 0)
                tool_meta = self._tool_use_blocks.get(index, {})
                partial_json = str(getattr(delta, "partial_json", "") or "")
                if not partial_json and not tool_meta:
                    return None
                return LlmChunk(
                    delta=LlmDelta(
                        tool_calls=[
                            {
                                "index": index,
                                "id": str(tool_meta.get("id", "") or ""),
                                "type": "function",
                                "function": {
                                    "name": str(tool_meta.get("name", "") or ""),
                                    "arguments": partial_json,
                                },
                            }
                        ]
                    ),
                )

        if event_type == "message_delta":
            delta = getattr(event, "delta", None)
            stop_reason = getattr(delta, "stop_reason", None)
            finish_map = {
                "tool_use": "tool_calls",
                "end_turn": "stop",
                "max_tokens": "length",
                "stop_sequence": "stop",
            }
            if stop_reason:
                return LlmChunk(
                    delta=LlmDelta(),
                    finish_reason=finish_map.get(str(stop_reason), str(stop_reason)),
                )

        if event_type == "message_stop":
            return LlmChunk(
                delta=LlmDelta(),
                finish_reason="stop",
            )

        return None

    def _convert_messages(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """将内部统一消息协议转为 Anthropic Messages API 格式。"""
        return to_anthropic_messages(messages)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 OpenAI function schema 转为 Anthropic tool schema。"""
        return to_anthropic_tools(tools)

    def _is_native_anthropic_endpoint(self) -> bool:
        if not self._base_url:
            return True
        return "anthropic.com" in self._base_url.rstrip("/").lower()

    async def aclose(self) -> None:
        await self._client.close()
