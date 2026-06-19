from __future__ import annotations

from typing import Any

from app.services.agent.models.llm_config import LlmModelConfig, LlmProviderConfig

from .anthropic_client import AnthropicChatClient
from .base import BaseLlmClient, LlmChunk, LlmDelta, LlmRequestOptions
from .codex_client import CodexChatClient
from .openai_client import OpenAIChatClient

__all__ = [
    "BaseLlmClient",
    "LlmChunk",
    "LlmDelta",
    "LlmRequestOptions",
    "MultiProtocolClient",
    "OpenAIChatClient",
    "AnthropicChatClient",
    "CodexChatClient",
    "create_llm_client",
]


def _get_provider_attr(provider: LlmProviderConfig | dict[str, Any], key: str) -> Any:
    """从 provider 配置中获取属性值，支持 Pydantic 模型和 dict。"""
    if isinstance(provider, dict):
        return provider.get(key)
    return getattr(provider, key, None)


def create_llm_client(
    provider: LlmProviderConfig,
    model: str,
    *,
    api_key_override: str | None = None,
    model_config: LlmModelConfig | dict[str, Any] | None = None,
) -> BaseLlmClient:
    """根据 provider 配置创建对应协议的 LLM Client。

    Args:
        provider: LLM provider 配置（含 protocol, base_url, api_key, region 等）
        model: 模型名称
        api_key_override: 可选，覆盖 provider.api_key 的 API key（用于 credential pool 轮换）
        model_config: 可选，模型级别配置；其中的 reasoning_key 会覆盖 provider 级别的配置。

    Returns:
        对应协议的 BaseLlmClient 实例
    """
    protocol = (
        str(
            _get_provider_attr(provider, "protocol")
            or _get_provider_attr(provider, "type")
            or "openai_chat_completions"
        )
        .strip()
        .lower()
    )
    api_key = (
        api_key_override
        if api_key_override is not None
        else str(_get_provider_attr(provider, "api_key") or "").strip()
    )
    base_url = str(_get_provider_attr(provider, "base_url") or "").strip() or None
    _region = str(_get_provider_attr(provider, "region") or "").strip() or None
    reasoning_format = _get_provider_attr(provider, "reasoning_format")

    # 模型级别的 reasoning_key 优先级高于 provider 级别，与 kimi-code 的 alias.reasoningKey 语义对齐
    reasoning_key = _get_provider_attr(model_config, "reasoning_key")
    if reasoning_key is None:
        reasoning_key = _get_provider_attr(provider, "reasoning_key")

    if protocol == "openai_chat_completions":
        return OpenAIChatClient(
            api_key=api_key,
            base_url=base_url or "",
            model=model,
            reasoning_key=reasoning_key,
            reasoning_format=reasoning_format,
        )
    if protocol == "openai_responses":
        return CodexChatClient(api_key=api_key, base_url=base_url, model=model)
    if protocol == "anthropic_messages":
        return AnthropicChatClient(api_key=api_key, base_url=base_url, model=model)
    if protocol in ("codex", "openai-codex"):
        return CodexChatClient(api_key=api_key, base_url=base_url, model=model)

    raise ValueError(f"Unsupported LLM protocol: {protocol}")


class MultiProtocolClient:
    """多协议 LLM Client 的统一包装。

    根据 provider 配置自动选择底层 client，对外暴露统一的 chat_stream 接口。
    """

    def __init__(self, client: BaseLlmClient):
        self._client = client

    @property
    def inner(self) -> BaseLlmClient:
        return self._client

    async def chat_stream(self, *args, **kwargs):
        async for chunk in self._client.chat_stream(*args, **kwargs):
            yield chunk

    async def aclose(self) -> None:
        await self._client.aclose()
