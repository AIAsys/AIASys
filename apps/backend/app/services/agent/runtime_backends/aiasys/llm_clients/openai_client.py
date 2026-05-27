from __future__ import annotations

import logging
import platform
import socket
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk

from .base import BaseLlmClient, LlmChunk, LlmDelta, LlmRequestOptions
from .message_protocol import InternalMessage, to_openai_chat_messages

logger = logging.getLogger(__name__)

# Kimi Coding API 要求的设备标识 header（参考 kimi-cli）
_KIMI_CODING_HEADERS = {
    "User-Agent": "KimiCLI/1.16.0",
    "X-Msh-Platform": "kimi_cli",
    "X-Msh-Version": "1.16.0",
}


def _device_model() -> str:
    system = platform.system()
    arch = platform.machine() or ""
    if system == "Darwin":
        version = platform.mac_ver()[0] or platform.release()
        if version and arch:
            return f"macOS {version} {arch}"
        if version:
            return f"macOS {version}"
        return f"macOS {arch}".strip()
    if system == "Windows":
        release = platform.release()
        if release and arch:
            return f"Windows {release} {arch}"
        if release:
            return f"Windows {release}"
        return f"Windows {arch}".strip()
    if system:
        version = platform.release()
        if version and arch:
            return f"{system} {version} {arch}"
        if version:
            return f"{system} {version}"
        return f"{system} {arch}".strip()
    return "Unknown"


def _get_or_create_device_id() -> str:
    """获取或创建持久化设备 ID（参考 kimi-cli 的 device_id 机制）。"""
    share_dir = Path.home() / ".local" / "share" / "aiasys"
    share_dir.mkdir(parents=True, exist_ok=True)
    device_id_path = share_dir / "device_id"
    if device_id_path.exists():
        return device_id_path.read_text(encoding="utf-8").strip()
    device_id = uuid.uuid4().hex
    device_id_path.write_text(device_id, encoding="utf-8")
    return device_id


def _build_kimi_coding_headers() -> dict[str, str]:
    """构建 Kimi Coding API 要求的认证 header。"""
    headers = dict(_KIMI_CODING_HEADERS)
    headers["X-Msh-Device-Name"] = platform.node() or socket.gethostname()
    headers["X-Msh-Device-Model"] = _device_model()
    headers["X-Msh-Os-Version"] = platform.version()
    headers["X-Msh-Device-Id"] = _get_or_create_device_id()
    return headers


def _is_kimi_coding_endpoint(base_url: str) -> bool:
    """判断是否为 Kimi Coding API 端点。"""
    return "api.kimi.com" in base_url and "/coding" in base_url


class OpenAIChatClient(BaseLlmClient):
    """基于官方 openai.AsyncOpenAI 的流式客户端。

    支持任何 OpenAI-compatible 端点（OpenAI、Kimi、DeepSeek、DashScope 等）。
    对 Kimi Coding API 自动注入必要的认证 header。
    """

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        reasoning_key: str | None = None,
        reasoning_format: str | None = None,
    ):
        self.model = model.strip()
        self._base_url = base_url.rstrip("/") if base_url else ""
        self._reasoning_key = reasoning_key
        self._reasoning_format = reasoning_format

        client_kwargs: dict[str, Any] = {
            "api_key": api_key.strip(),
            "base_url": self._base_url or None,
            "timeout": 900.0,
            "max_retries": 2,
        }

        # 对 Kimi Coding API 自动注入认证 header
        if self._base_url and _is_kimi_coding_endpoint(self._base_url):
            client_kwargs["default_headers"] = _build_kimi_coding_headers()
            logger.info("检测到 Kimi Coding API，已注入认证 header")

        self._client = AsyncOpenAI(**client_kwargs)

    async def chat_stream(
        self,
        messages: list[InternalMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None = None,
    ) -> AsyncGenerator[LlmChunk, None]:
        kwargs = self._build_chat_kwargs(messages, tools, temperature, max_tokens, request_options)

        try:
            async for chunk in self._do_stream(**kwargs):
                yield chunk
        except Exception as exc:
            error_text = str(exc).lower()
            if kwargs.get("stream_options") and (
                "stream_options" in error_text or "include_usage" in error_text
            ):
                logger.warning("Provider 不支持 stream_options，尝试 fallback: %s", exc)
                kwargs.pop("stream_options", None)
                async for chunk in self._do_stream(**kwargs):
                    yield chunk
                return
            raise

    def _build_chat_kwargs(
        self,
        messages: list[InternalMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None,
    ) -> dict[str, Any]:
        """构造 chat.completions.create 的请求参数，子类可重写以添加厂商特有参数。"""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._convert_messages(messages),
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if tools:
            kwargs["tools"] = tools
        if temperature is not None:
            kwargs["temperature"] = temperature
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if request_options and request_options.thinking_enabled:
            effort = (request_options.thinking_effort or "high").strip().lower()
            if effort in ("low", "medium", "high"):
                kwargs["reasoning_effort"] = effort
            if getattr(self, "_reasoning_format", None):
                # OpenAI SDK 不识别 reasoning_format 参数，通过 extra_body 透传
                extra_body = kwargs.setdefault("extra_body", {})
                extra_body["reasoning_format"] = self._reasoning_format
        return kwargs

    async def _do_stream(self, **kwargs: Any) -> AsyncGenerator[LlmChunk, None]:
        async for raw in await self._client.chat.completions.create(**kwargs):
            chunk = self._normalize_chunk(raw)
            if chunk is not None:
                yield chunk

    def _convert_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted = to_openai_chat_messages(messages)
        # 如果 provider 配置了自定义 reasoning_key，将 reasoning_content 映射到对应字段
        reasoning_key = getattr(self, "_reasoning_key", None)
        if reasoning_key is None:
            reasoning_key = "reasoning_content"
        if reasoning_key and reasoning_key != "reasoning_content":
            for msg in converted:
                if "reasoning_content" in msg:
                    msg[reasoning_key] = msg.pop("reasoning_content")
        return converted

    def _normalize_chunk(self, raw: ChatCompletionChunk) -> LlmChunk | None:
        """将 OpenAI SDK 的 ChatCompletionChunk 转为 LlmChunk。"""
        choices = raw.choices
        if not choices:
            # usage-only chunk (when stream_options.include_usage=True)
            if raw.usage is not None:
                return LlmChunk(
                    delta=LlmDelta(),
                    usage={
                        "prompt_tokens": raw.usage.prompt_tokens,
                        "completion_tokens": raw.usage.completion_tokens,
                        "input_tokens": getattr(raw.usage, "prompt_tokens", 0),
                        "output_tokens": getattr(raw.usage, "completion_tokens", 0),
                    },
                )
            return None

        choice = choices[0]
        delta = choice.delta

        tool_calls: list[dict[str, Any]] | None = None
        if delta.tool_calls:
            tool_calls = []
            for tc in delta.tool_calls:
                tool_calls.append(
                    {
                        "index": tc.index,
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name if tc.function else None,
                            "arguments": tc.function.arguments if tc.function else None,
                        },
                    }
                )

        reasoning_content: str | None = None
        reasoning_key = getattr(self, "_reasoning_key", None)
        if reasoning_key is None:
            reasoning_key = "reasoning_content"
        if reasoning_key and hasattr(delta, reasoning_key):
            val = getattr(delta, reasoning_key, None)
            if val:
                reasoning_content = val

        return LlmChunk(
            delta=LlmDelta(
                content=delta.content,
                reasoning_content=reasoning_content,
                tool_calls=tool_calls,
            ),
            finish_reason=choice.finish_reason,
            usage=None,
        )

    async def aclose(self) -> None:
        await self._client.close()
