from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import Any

from .base import BaseLlmClient, LlmChunk, LlmDelta, LlmRequestOptions
from .message_protocol import InternalMessage, to_responses_input_messages

logger = logging.getLogger(__name__)


class CodexChatClient(BaseLlmClient):
    """基于 OpenAI Responses API 的流式客户端。

    Codex 使用 Responses API（非 Chat Completions），此适配器将其
    包装为与 chat.completions 等效的 LlmChunk 流。
    """

    def __init__(self, api_key: str, base_url: str | None, model: str):
        self.model = model.strip()
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise ImportError("The 'openai' package is required for the Codex provider.") from exc
        self._client = AsyncOpenAI(
            api_key=api_key.strip(),
            base_url=base_url.rstrip("/") if base_url else None,
            timeout=900.0,
            max_retries=2,
        )

    async def chat_stream(
        self,
        messages: list[InternalMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None = None,
    ) -> AsyncGenerator[LlmChunk, None]:
        # Convert ChatCompletion messages to Responses API input format
        input_messages = self._convert_messages(messages)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "input": input_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = self._convert_tools(tools)
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_output_tokens"] = max_tokens
        if request_options and request_options.thinking_enabled:
            effort = (request_options.thinking_effort or "high").strip().lower()
            if effort == "minimal":
                effort = "low"
            if effort in {"low", "medium", "high", "xhigh"}:
                kwargs["reasoning"] = {"effort": effort, "summary": "auto"}
                kwargs["include"] = ["reasoning.encrypted_content"]

        async for event in await self._client.responses.create(**kwargs):
            chunk = self._normalize_event(event)
            if chunk is not None:
                yield chunk

    def _normalize_event(self, event: Any) -> LlmChunk | None:
        """将 Responses API event 转为 LlmChunk。"""
        event_type = getattr(event, "type", None)

        if event_type == "response.output_text.delta":
            return LlmChunk(
                delta=LlmDelta(content=getattr(event, "delta", None)),
            )

        if event_type == "response.output_item.added":
            item = getattr(event, "item", None)
            if item and getattr(item, "type", None) == "function_call":
                return LlmChunk(
                    delta=LlmDelta(
                        tool_calls=[
                            {
                                "index": 0,
                                "id": getattr(item, "call_id", getattr(item, "id", "")),
                                "type": "function",
                                "function": {
                                    "name": getattr(item, "name", ""),
                                    "arguments": getattr(item, "arguments", "{}"),
                                },
                            }
                        ]
                    ),
                )

        if event_type == "response.completed":
            response = getattr(event, "response", None)
            if response and getattr(response, "usage", None):
                u = response.usage
                return LlmChunk(
                    delta=LlmDelta(),
                    finish_reason="stop",
                    usage={
                        "input_tokens": getattr(u, "input_tokens", 0),
                        "output_tokens": getattr(u, "output_tokens", 0),
                        "prompt_tokens": getattr(u, "input_tokens", 0),
                        "completion_tokens": getattr(u, "output_tokens", 0),
                    },
                )

        return None

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将内部统一消息协议转为 Responses API input 格式。"""
        return to_responses_input_messages(messages)

    def _convert_tools(self, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """将 OpenAI function schema 转为 Responses API tool format。"""
        result: list[dict[str, Any]] = []
        for t in tools:
            fn = t.get("function", {})
            result.append(
                {
                    "type": "function",
                    "name": fn.get("name", ""),
                    "description": fn.get("description", ""),
                    "parameters": fn.get("parameters", {"type": "object"}),
                }
            )
        return result

    async def aclose(self) -> None:
        await self._client.close()
