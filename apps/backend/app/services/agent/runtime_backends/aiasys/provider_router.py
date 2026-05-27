from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any

from app.services.agent.models.llm_config import LlmProviderConfig

from .llm_clients import create_llm_client
from .llm_clients.base import BaseLlmClient, LlmChunk, LlmRequestOptions
from .llm_clients.credential_pool import CredentialPool
from .llm_clients.error_classifier import classify_api_error
from .llm_clients.message_protocol import InternalMessage
from .llm_clients.retry_utils import jittered_backoff

logger = logging.getLogger(__name__)


class ProviderRouter(BaseLlmClient):
    """多 Provider 路由与自动降级。

    在初始化时绑定 primary provider 和 fallback providers，
    对外暴露与 BaseLlmClient 相同的 chat_stream / aclose 接口。

    降级策略：
      - 同一 provider 内：如果配置了多个 api_key（CredentialPool），
        优先在 pool 内轮换凭证，耗尽后再跨 provider fallback。
      - billing (402) / auth (401/403) / model_not_found (404)
        → 立即切换凭证或 provider
      - rate_limit (429) / server_error (500/502) / overloaded (503/529)
        → 在当前 provider 上带 jittered backoff 重试，重试耗尽后再 fallback
      - timeout / connection error
        → 重试一次，然后 fallback
      - context_overflow / payload_too_large
        → 记录但不上抛到上层（由 session 层的 context compressor 处理）
    """

    def __init__(
        self,
        primary: LlmProviderConfig,
        fallbacks: list[LlmProviderConfig],
        model: str,
        *,
        max_retries_per_provider: int = 2,
    ):
        self._providers = [primary] + list(fallbacks)
        self._model = model
        self._max_retries = max(1, max_retries_per_provider)
        self._current_client: Any | None = None

        # 为每个 provider 构建 credential pool（如果配置了多个 key）
        self._pools: dict[int, CredentialPool | None] = {}
        for idx, provider in enumerate(self._providers):
            pool = CredentialPool.from_provider_config(
                provider_id=getattr(provider, "name", f"provider-{idx}"),
                api_key=getattr(provider, "api_key", None),
                api_keys=getattr(provider, "api_keys", None),
            )
            self._pools[idx] = pool

    async def chat_stream(
        self,
        messages: list[InternalMessage],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None = None,
    ) -> AsyncGenerator[LlmChunk, None]:
        """流式对话，自动处理 provider 降级与凭证轮换。"""
        last_error: Exception | None = None

        for provider_idx, provider in enumerate(self._providers):
            provider_name = getattr(provider, "name", f"provider-{provider_idx}")
            pool = self._pools.get(provider_idx)

            # 如果该 provider 有 credential pool，先获取一个可用凭证
            credential = await pool.get_next() if pool is not None else None
            api_key_for_this_attempt = credential.api_key if credential is not None else None

            attempt = 0
            while attempt < self._max_retries:
                attempt += 1
                client: Any | None = None
                try:
                    client = create_llm_client(
                        provider, self._model, api_key_override=api_key_for_this_attempt
                    )
                    self._current_client = client
                    async for chunk in client.chat_stream(
                        messages=messages,
                        tools=tools,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        request_options=request_options,
                    ):
                        yield chunk
                    await client.aclose()
                    self._current_client = None
                    return

                except Exception as exc:
                    if client is not None:
                        await self._safe_close(client)
                    self._current_client = None
                    last_error = exc

                    classified = classify_api_error(
                        exc,
                        provider=provider_name,
                        model=self._model,
                        approx_tokens=_approximate_tokens(messages),
                    )

                    logger.warning(
                        "Provider %s error (attempt %d/%d): %s (status=%s, reason=%s)",
                        provider_name,
                        attempt,
                        self._max_retries,
                        classified.message[:200],
                        classified.status_code,
                        classified.reason.value,
                    )

                    # 上下文/负载过大：由上层处理，不在这里 fallback
                    if classified.should_compress:
                        logger.info(
                            "Provider %s reports context/payload too large; "
                            "raising to session layer for compression.",
                            provider_name,
                        )
                        raise

                    # 优先尝试同一 provider 的凭证轮换（billing/auth 等）
                    rotated = False
                    if pool is not None and credential is not None:
                        next_cred = await pool.mark_exhausted(
                            credential.id,
                            reason=classified.reason.value,
                        )
                        if next_cred is not None:
                            credential = next_cred
                            api_key_for_this_attempt = credential.api_key
                            logger.info(
                                "Rotated to next credential %s for provider %s",
                                credential.id,
                                provider_name,
                            )
                            # 用新凭证重试，不计入 attempt 次数
                            attempt -= 1
                            rotated = True
                            continue
                        # pool 内所有凭证耗尽
                        logger.warning(
                            "All credentials exhausted for provider %s, falling back",
                            provider_name,
                        )
                        classified.should_fallback = True

                    # 需要立即 fallback 到下一个 provider
                    if not rotated and classified.should_fallback:
                        if provider_idx < len(self._providers) - 1:
                            logger.info(
                                "Provider %s failed with %s, falling back to next provider",
                                provider_name,
                                classified.reason.value,
                            )
                            break  # 跳出当前 provider 的重试循环
                        logger.error(
                            "Provider %s failed with %s and no more fallbacks",
                            provider_name,
                            classified.reason.value,
                        )
                        raise

                    # 不可重试且不应 fallback：直接抛出
                    if not classified.retryable:
                        raise

                    # 可重试：jittered backoff 后重试
                    if attempt < self._max_retries:
                        delay = jittered_backoff(attempt)
                        logger.info(
                            "Retrying provider %s in %.1fs (attempt %d/%d)",
                            provider_name,
                            delay,
                            attempt,
                            self._max_retries,
                        )
                        await asyncio.sleep(delay)
                        continue

                    # 当前 provider 重试耗尽，尝试 fallback
                    if provider_idx < len(self._providers) - 1:
                        logger.info(
                            "Provider %s exhausted retries, falling back",
                            provider_name,
                        )
                        break

                    # 没有更多 fallback，抛出最后的错误
                    raise

        if last_error is not None:
            raise last_error

        raise RuntimeError("All providers failed without raising an error")

    async def aclose(self) -> None:
        """关闭当前持有的 client。"""
        if self._current_client is not None:
            await self._safe_close(self._current_client)
            self._current_client = None

    async def _safe_close(self, client: Any) -> None:
        """安全关闭 client，忽略异常。"""
        if client is not None and hasattr(client, "aclose"):
            try:
                await client.aclose()
            except Exception:
                pass


def _approximate_tokens(messages: list[InternalMessage]) -> int:
    """粗略估算消息列表的 token 数（用于 context overflow 判断）。"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += len(content) // 4
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text", "")
                    if isinstance(text, str):
                        total += len(text) // 4
        for key in ("tool_calls", "reasoning_content"):
            val = msg.get(key, "")
            if isinstance(val, str):
                total += len(val) // 4
            elif isinstance(val, list):
                total += len(str(val)) // 4
    return total
