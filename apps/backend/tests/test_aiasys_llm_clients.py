from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace
from typing import Any

import pytest

from app.services.agent.runtime_backends.aiasys.llm_clients.base import (
    LlmChunk,
    LlmDelta,
    LlmRequestOptions,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.codex_client import (
    CodexChatClient,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.error_classifier import (
    ClassifiedError,
    FailoverReason,
    classify_api_error,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.openai_client import (
    OpenAIChatClient,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.retry_utils import jittered_backoff
from app.services.agent.runtime_backends.aiasys.llm_clients.anthropic_client import (
    AnthropicChatClient,
)
from app.services.agent.runtime_backends.aiasys.llm_clients import create_llm_client


# ── Error Classifier Tests ──────────────────────────────────────────────


class FakeHttpError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class FakeOpenAIError(Exception):
    """模拟 OpenAI SDK 风格的错误。"""

    def __init__(self, message: str, status_code: int | None = None, body: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class FakeAnthropicError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def test_create_llm_client_uses_responses_client_for_openai_responses_protocol():
    provider = LlmProviderConfig(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        type="openai_responses",
    )

    client = create_llm_client(provider, "gpt-5")

    assert isinstance(client, CodexChatClient)
    asyncio.run(client.aclose())


def test_classify_billing_402():
    err = FakeHttpError("Payment required", 402)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.billing
    assert result.retryable is False
    assert result.should_fallback is True


def test_classify_rate_limit_429():
    err = FakeHttpError("Rate limit exceeded", 429)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.rate_limit
    assert result.retryable is True


def test_classify_billing_in_429_message():
    err = FakeHttpError("429: insufficient credits, please top up", 429)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.billing
    assert result.retryable is False
    assert result.should_fallback is True


def test_classify_auth_401():
    err = FakeHttpError("Unauthorized", 401)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.auth
    assert result.retryable is False
    assert result.should_rotate_credential is True


def test_classify_auth_403():
    err = FakeHttpError("Forbidden", 403)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.auth


def test_classify_context_overflow():
    err = FakeHttpError("context length exceeded, reduce the length")
    result = classify_api_error(err)
    assert result.reason == FailoverReason.context_overflow
    assert result.should_compress is True


def test_classify_model_not_found_404():
    err = FakeHttpError("model not found: gpt-unknown", 404)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.model_not_found
    assert result.should_fallback is True


def test_classify_server_error_500():
    err = FakeHttpError("Internal server error", 500)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.server_error
    assert result.retryable is True


def test_classify_overloaded_503():
    err = FakeHttpError("Service overloaded", 503)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.overloaded
    assert result.retryable is True


def test_classify_timeout_transport():
    err = TimeoutError("Connection timed out")
    result = classify_api_error(err)
    assert result.reason == FailoverReason.timeout
    assert result.retryable is True


def test_classify_openai_sdk_error():
    err = FakeOpenAIError("rate limit exceeded", 429)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.rate_limit


def test_classify_thinking_signature():
    err = FakeAnthropicError("Invalid thinking block signature", 400)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.thinking_signature


def test_classify_long_context_tier():
    err = FakeHttpError("extra usage long context tier gate", 429)
    result = classify_api_error(err)
    assert result.reason == FailoverReason.long_context_tier
    assert result.should_compress is True


def test_classify_unknown():
    err = Exception("something weird happened")
    result = classify_api_error(err)
    assert result.reason == FailoverReason.unknown
    assert result.retryable is True


def test_classify_extracts_status_code_from_message():
    err = Exception("HTTP 529 service unavailable")
    result = classify_api_error(err)
    assert result.status_code == 529
    assert result.reason == FailoverReason.overloaded


def test_classified_error_is_auth_property():
    billing = ClassifiedError(reason=FailoverReason.billing)
    assert billing.is_auth is False

    auth = ClassifiedError(reason=FailoverReason.auth)
    assert auth.is_auth is True

    auth_perm = ClassifiedError(reason=FailoverReason.auth_permanent)
    assert auth_perm.is_auth is True


# ── Retry Utils Tests ───────────────────────────────────────────────────


def test_jittered_backoff_increases_with_attempt():
    d1 = jittered_backoff(1)
    d2 = jittered_backoff(2)
    d3 = jittered_backoff(3)
    assert d1 >= 5.0
    assert d2 >= d1
    assert d3 >= d2


def test_jittered_backoff_respects_max_delay():
    d = jittered_backoff(10, base_delay=5.0, max_delay=60.0)
    assert d <= 60.0 * 1.5  # max_delay + max jitter


def test_jittered_backoff_has_jitter():
    delays = [jittered_backoff(2, base_delay=5.0, jitter_ratio=0.5) for _ in range(20)]
    # Not all identical because of jitter
    assert len(set(round(d, 2) for d in delays)) > 1


def test_jittered_backoff_decorrelation():
    # Two calls in quick succession should not return identical delays
    d1 = jittered_backoff(1)
    d2 = jittered_backoff(1)
    assert d1 != d2 or abs(d1 - d2) < 0.01  # extremely unlikely to be equal


# ── Provider Router Tests ───────────────────────────────────────────────

from app.services.agent.models.llm_config import LlmProviderConfig
from app.services.agent.runtime_backends.aiasys.provider_router import ProviderRouter


class _FakeLlmClient:
    """可编程的 fake LLM client，用于测试 ProviderRouter。"""

    def __init__(self, chunks: list[LlmChunk] | None = None, fail_with: Exception | None = None):
        self.chunks = chunks or []
        self.fail_with = fail_with
        self.closed = False
        self.calls: list[tuple] = []

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options: LlmRequestOptions | None = None,
    ) -> AsyncGenerator[LlmChunk, None]:
        if self.fail_with is not None:
            raise self.fail_with
        self.calls.append((messages, tools, temperature, max_tokens, request_options))
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _FakeFailingClientFactory:
    """控制 create_llm_client 返回的 client 序列。"""

    def __init__(self, clients: list[_FakeLlmClient]):
        self.clients = list(clients)
        self.index = 0

    def __call__(self, provider: LlmProviderConfig, model: str) -> _FakeLlmClient:
        client = self.clients[self.index]
        self.index += 1
        return client


@pytest.fixture(autouse=True)
def _patch_create_llm_client(monkeypatch):
    """在测试中将 create_llm_client 替换为可控版本。"""
    import app.services.agent.runtime_backends.aiasys.provider_router as pr_mod
    import app.services.agent.runtime_backends.aiasys.llm_clients as lc_mod

    _original_pr = pr_mod.create_llm_client
    _original_lc = lc_mod.create_llm_client

    def _restore():
        pr_mod.create_llm_client = _original_pr
        lc_mod.create_llm_client = _original_lc

    monkeypatch.setattr(pr_mod, "create_llm_client", lambda p, m, **kwargs: _fake_factory(p, m))
    monkeypatch.setattr(lc_mod, "create_llm_client", lambda p, m, **kwargs: _fake_factory(p, m))
    yield
    _restore()


_fake_factory = None


async def test_router_primary_succeeds():
    global _fake_factory
    primary = _FakeLlmClient(chunks=[LlmChunk(delta=LlmDelta(content="ok"))])
    _fake_factory = lambda p, m: primary

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1"),
        fallbacks=[LlmProviderConfig(api_key="k2", base_url="http://p2")],
        model="gpt-4",
    )

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="high",
        thinking_budget_tokens=8192,
    )
    chunks = [c async for c in router.chat_stream([], None, 0.7, 1024, request_options)]
    assert len(chunks) == 1
    assert chunks[0].delta.content == "ok"
    assert primary.calls[0][4] is request_options
    assert primary.closed is True


async def test_router_fallback_on_billing_error():
    global _fake_factory
    primary = _FakeLlmClient(fail_with=FakeHttpError("insufficient credits", 402))
    fallback = _FakeLlmClient(chunks=[LlmChunk(delta=LlmDelta(content="fallback ok"))])
    clients = [primary, fallback]
    _fake_factory = lambda p, m: clients.pop(0)

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1"),
        fallbacks=[LlmProviderConfig(api_key="k2", base_url="http://p2")],
        model="gpt-4",
    )

    chunks = [c async for c in router.chat_stream([], None, 0.7, 1024)]
    assert len(chunks) == 1
    assert chunks[0].delta.content == "fallback ok"
    assert primary.closed is True
    assert fallback.closed is True


async def test_router_fallback_on_rate_limit_after_retries():
    global _fake_factory
    primary = _FakeLlmClient(fail_with=FakeHttpError("rate limit", 429))
    fallback = _FakeLlmClient(chunks=[LlmChunk(delta=LlmDelta(content="ok"))])
    clients = [primary, fallback]
    _fake_factory = lambda p, m: clients.pop(0)

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1"),
        fallbacks=[LlmProviderConfig(api_key="k2", base_url="http://p2")],
        model="gpt-4",
        max_retries_per_provider=1,  # 只重试一次就 fallback
    )

    chunks = [c async for c in router.chat_stream([], None, 0.7, 1024)]
    assert len(chunks) == 1
    assert chunks[0].delta.content == "ok"


async def test_router_raises_when_all_fail():
    global _fake_factory
    primary = _FakeLlmClient(fail_with=FakeHttpError("billing", 402))
    fallback = _FakeLlmClient(fail_with=FakeHttpError("also billing", 402))
    clients = [primary, fallback]
    _fake_factory = lambda p, m: clients.pop(0)

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1"),
        fallbacks=[LlmProviderConfig(api_key="k2", base_url="http://p2")],
        model="gpt-4",
    )

    with pytest.raises(Exception, match="billing"):
        async for _ in router.chat_stream([], None, 0.7, 1024):
            pass


async def test_router_context_overflow_raises_immediately():
    global _fake_factory
    primary = _FakeLlmClient(fail_with=FakeHttpError("context length exceeded"))
    clients = [primary]
    _fake_factory = lambda p, m: clients.pop(0)

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1"),
        fallbacks=[],
        model="gpt-4",
    )

    with pytest.raises(Exception, match="context length exceeded"):
        async for _ in router.chat_stream([], None, 0.7, 1024):
            pass


async def test_router_aclose_closes_current_client():
    global _fake_factory
    client = _FakeLlmClient(chunks=[])
    _fake_factory = lambda p, m: client

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1"),
        fallbacks=[],
        model="gpt-4",
    )
    # Manually set current client
    router._current_client = client
    await router.aclose()
    assert client.closed is True


# ── Credential Pool Tests ───────────────────────────────────────────────

from app.services.agent.runtime_backends.aiasys.llm_clients.credential_pool import (
    CredentialPool,
    PooledCredential,
)


def test_pool_from_single_key_returns_none():
    pool = CredentialPool.from_provider_config("p1", api_key="k1", api_keys=None)
    assert pool is None


def test_pool_from_multiple_keys():
    pool = CredentialPool.from_provider_config("p1", api_key="k1", api_keys=["k2", "k3"])
    assert pool is not None
    assert pool.size == 3
    assert pool.has_available is True


@pytest.mark.asyncio
async def test_pool_round_robin():
    pool = CredentialPool.from_provider_config("p1", api_key="k1", api_keys=["k2", "k3"])
    c1 = await pool.get_next()
    c2 = await pool.get_next()
    c3 = await pool.get_next()
    c4 = await pool.get_next()
    assert c1.api_key == "k1"
    assert c2.api_key == "k2"
    assert c3.api_key == "k3"
    assert c4.api_key == "k1"  # 循环


@pytest.mark.asyncio
async def test_pool_mark_exhausted():
    pool = CredentialPool.from_provider_config("p1", api_key="k1", api_keys=["k2"])
    c1 = await pool.get_next()
    next_cred = await pool.mark_exhausted(c1.id, reason="billing")
    assert next_cred is not None
    assert next_cred.api_key == "k2"
    assert c1.status == "exhausted"


@pytest.mark.asyncio
async def test_pool_all_exhausted():
    pool = CredentialPool.from_provider_config("p1", api_key="k1", api_keys=["k2"])
    c1 = await pool.get_next()
    await pool.mark_exhausted(c1.id, reason="billing")
    c2 = await pool.get_next()
    await pool.mark_exhausted(c2.id, reason="billing")
    assert pool.has_available is False
    assert await pool.get_next() is None


@pytest.mark.asyncio
async def test_pool_cooldown_recovery(monkeypatch):
    pool = CredentialPool.from_provider_config("p1", api_key="k1", api_keys=["k2"])
    assert pool is not None
    c1 = await pool.get_next()
    await pool.mark_exhausted(c1.id, reason="rate_limit")
    assert c1.is_available is False

    # 模拟时间前进超过冷却期
    import time as time_mod

    future = time_mod.time() + 4000
    monkeypatch.setattr(time_mod, "time", lambda: future)
    assert c1.is_available is True


@pytest.mark.asyncio
async def test_pool_random_strategy():
    pool = CredentialPool.from_provider_config(
        "p1",
        api_key="k1",
        api_keys=["k2", "k3", "k4"],
        strategy="random",
    )
    keys = {(await pool.get_next()).api_key for _ in range(20)}
    assert len(keys) > 1


@pytest.mark.asyncio
async def test_pool_least_used_strategy():
    pool = CredentialPool.from_provider_config(
        "p1",
        api_key="k1",
        api_keys=["k2", "k3"],
        strategy="least_used",
    )
    c1 = await pool.get_next()
    c1.request_count += 5  # 手动增加使用次数
    c2 = await pool.get_next()
    assert c2.api_key != c1.api_key  # 应该选择使用次数更少的


# ── ProviderRouter + CredentialPool Integration Tests ───────────────────


class _FakeKeyTrackingClient:
    """记录传入的 api_key_override 的 fake client。"""

    def __init__(self, chunks: list[LlmChunk] | None = None, fail_with: Exception | None = None):
        self.chunks = chunks or []
        self.fail_with = fail_with
        self.closed = False
        self.used_api_keys: list[str | None] = []

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        if self.fail_with is not None:
            raise self.fail_with
        self.used_api_keys.append(None)  # 由 factory 注入实际 key
        for chunk in self.chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _FakeKeyTrackingFactory:
    def __init__(self, clients: list[_FakeKeyTrackingClient]):
        self.clients = list(clients)
        self.index = 0
        self.passed_api_keys: list[str | None] = []

    def __call__(self, provider, model, **kwargs):
        client = self.clients[self.index]
        self.index += 1
        self.passed_api_keys.append(kwargs.get("api_key_override"))
        return client


async def test_router_rotates_credentials_within_provider(monkeypatch):
    """同一 provider 配置了多个 key，第一个 key billing 耗尽后应切换到第二个 key。"""
    import app.services.agent.runtime_backends.aiasys.provider_router as pr_mod
    import app.services.agent.runtime_backends.aiasys.llm_clients as lc_mod

    _orig_pr = pr_mod.create_llm_client
    _orig_lc = lc_mod.create_llm_client

    client1 = _FakeKeyTrackingClient(fail_with=FakeHttpError("insufficient credits", 402))
    client2 = _FakeKeyTrackingClient(chunks=[LlmChunk(delta=LlmDelta(content="ok"))])
    factory = _FakeKeyTrackingFactory([client1, client2])

    monkeypatch.setattr(pr_mod, "create_llm_client", factory)
    monkeypatch.setattr(lc_mod, "create_llm_client", factory)

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="key-a", base_url="http://p1", api_keys=["key-b"]),
        fallbacks=[],
        model="gpt-4",
    )

    chunks = [c async for c in router.chat_stream([], None, 0.7, 1024)]
    assert len(chunks) == 1
    assert chunks[0].delta.content == "ok"
    assert factory.passed_api_keys == ["key-a", "key-b"]

    monkeypatch.setattr(pr_mod, "create_llm_client", _orig_pr)
    monkeypatch.setattr(lc_mod, "create_llm_client", _orig_lc)


async def test_router_fallback_when_all_credentials_exhausted(monkeypatch):
    """同一 provider 所有 key 耗尽后应 fallback 到下一个 provider。"""
    import app.services.agent.runtime_backends.aiasys.provider_router as pr_mod
    import app.services.agent.runtime_backends.aiasys.llm_clients as lc_mod

    _orig_pr = pr_mod.create_llm_client
    _orig_lc = lc_mod.create_llm_client

    primary_client = _FakeKeyTrackingClient(fail_with=FakeHttpError("billing", 402))
    fallback_client = _FakeKeyTrackingClient(chunks=[LlmChunk(delta=LlmDelta(content="fallback"))])
    factory = _FakeKeyTrackingFactory([primary_client, primary_client, fallback_client])

    monkeypatch.setattr(pr_mod, "create_llm_client", factory)
    monkeypatch.setattr(lc_mod, "create_llm_client", factory)

    router = ProviderRouter(
        primary=LlmProviderConfig(api_key="k1", base_url="http://p1", api_keys=["k2"]),
        fallbacks=[LlmProviderConfig(api_key="k3", base_url="http://p2")],
        model="gpt-4",
    )

    chunks = [c async for c in router.chat_stream([], None, 0.7, 1024)]
    assert len(chunks) == 1
    assert chunks[0].delta.content == "fallback"

    monkeypatch.setattr(pr_mod, "create_llm_client", _orig_pr)
    monkeypatch.setattr(lc_mod, "create_llm_client", _orig_lc)


def _multimodal_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,ZmFrZQ==",
                        "detail": "auto",
                    },
                    "source_path": "/workspace/chart.png",
                },
            ],
        }
    ]


def _assistant_tool_call_messages() -> list[dict[str, Any]]:
    return [
        {
            "role": "system",
            "content": "你是第一个系统提示",
        },
        {
            "role": "system",
            "content": "你是第二个系统提示",
        },
        {
            "role": "assistant",
            "content": "先调用天气工具",
            "tool_calls": [
                {
                    "id": "call_weather",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city":"杭州"}',
                    },
                }
            ],
            "reasoning_content": "内部推理不应直接下传给 provider",
        },
        {
            "role": "tool",
            "tool_call_id": "call_weather",
            "content": "杭州 22 度，多云",
        },
    ]


def test_openai_client_converts_multimodal_messages() -> None:
    client = OpenAIChatClient.__new__(OpenAIChatClient)

    converted = client._convert_messages(_multimodal_messages())

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": "data:image/png;base64,ZmFrZQ==",
                        "detail": "auto",
                    },
                },
            ],
        }
    ]


def test_openai_client_passes_reasoning_content_in_tool_call_messages() -> None:
    client = OpenAIChatClient.__new__(OpenAIChatClient)

    converted = client._convert_messages(_assistant_tool_call_messages())

    assert converted == [
        {
            "role": "system",
            "content": "你是第一个系统提示",
        },
        {
            "role": "system",
            "content": "你是第二个系统提示",
        },
        {
            "role": "assistant",
            "content": "先调用天气工具",
            "tool_calls": [
                {
                    "id": "call_weather",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"city":"杭州"}',
                    },
                }
            ],
            "reasoning_content": "内部推理不应直接下传给 provider",
        },
        {
            "role": "tool",
            "tool_call_id": "call_weather",
            "content": "杭州 22 度，多云",
        },
    ]


def test_anthropic_client_converts_multimodal_messages() -> None:
    client = AnthropicChatClient.__new__(AnthropicChatClient)

    system_msg, converted = client._convert_messages(_multimodal_messages())

    assert system_msg is None
    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看这张图"},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": "ZmFrZQ==",
                    },
                },
            ],
        }
    ]


def test_anthropic_client_converts_internal_tool_messages() -> None:
    client = AnthropicChatClient.__new__(AnthropicChatClient)

    system_msg, converted = client._convert_messages(_assistant_tool_call_messages())

    assert system_msg == "你是第一个系统提示\n\n你是第二个系统提示"
    assert converted == [
        {
            "role": "assistant",
            "content": [
                {
                    "type": "thinking",
                    "thinking": "内部推理不应直接下传给 provider",
                    "signature": "",
                },
                {"type": "text", "text": "先调用天气工具"},
                {
                    "type": "tool_use",
                    "id": "call_weather",
                    "name": "get_weather",
                    "input": {"city": "杭州"},
                },
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call_weather",
                    "content": "杭州 22 度，多云",
                }
            ],
        },
    ]


class _FakeAnthropicStream:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def get_final_message(self):
        return SimpleNamespace(usage=None)


class _FakeAnthropicMessages:
    def __init__(self) -> None:
        self.last_kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeAnthropicStream()


async def test_anthropic_client_sends_thinking_options_for_thinking_request() -> None:
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "kimi-for-coding"
    client._base_url = "https://api.kimi.com/coding/v1"
    client._tool_use_blocks = {}
    fake_messages = _FakeAnthropicMessages()
    client._client = SimpleNamespace(messages=fake_messages)

    chunks = [
        chunk
        async for chunk in client.chat_stream(
            messages=[{"role": "user", "content": "hello"}],
            tools=None,
            temperature=None,
            max_tokens=2048,
            request_options=LlmRequestOptions(
                thinking_enabled=True,
                thinking_effort="medium",
                thinking_budget_tokens=4096,
            ),
        )
    ]

    assert chunks == []
    assert fake_messages.last_kwargs is not None
    assert fake_messages.last_kwargs["thinking"] == {
        "type": "enabled",
        "budget_tokens": 4096,
    }
    assert fake_messages.last_kwargs["max_tokens"] == 6144
    assert "temperature" not in fake_messages.last_kwargs


def test_anthropic_client_normalizes_tool_use_stream_events() -> None:
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client._tool_use_blocks = {}

    start_chunk = client._normalize_event(
        SimpleNamespace(
            type="content_block_start",
            index=0,
            content_block=SimpleNamespace(
                type="tool_use",
                id="toolu_123",
                name="CallExternalAgent",
                input={},
            ),
        )
    )
    assert start_chunk is not None
    assert start_chunk.delta.tool_calls == [
        {
            "index": 0,
            "id": "toolu_123",
            "type": "function",
            "function": {
                "name": "CallExternalAgent",
                "arguments": "",
            },
        }
    ]

    delta_chunk = client._normalize_event(
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(
                type="input_json_delta",
                partial_json='{"agent_command":"codex"}',
            ),
        )
    )
    assert delta_chunk is not None
    assert delta_chunk.delta.tool_calls == [
        {
            "index": 0,
            "id": "toolu_123",
            "type": "function",
            "function": {
                "name": "CallExternalAgent",
                "arguments": '{"agent_command":"codex"}',
            },
        }
    ]

    finish_chunk = client._normalize_event(
        SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="tool_use"),
        )
    )
    assert finish_chunk is not None
    assert finish_chunk.finish_reason == "tool_calls"


def test_codex_client_converts_multimodal_messages() -> None:
    client = CodexChatClient.__new__(CodexChatClient)

    converted = client._convert_messages(_multimodal_messages())

    assert converted == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "看看这张图"},
                {"type": "input_image", "image_url": "data:image/png;base64,ZmFrZQ=="},
            ],
        }
    ]


def test_create_llm_client_returns_openai_client_for_chat_completions_protocol():
    provider = LlmProviderConfig(
        api_key="test-key",
        base_url="https://api.openai.com/v1",
        type="openai_chat_completions",
    )

    client = create_llm_client(provider, "gpt-4o")

    assert isinstance(client, OpenAIChatClient)
    asyncio.run(client.aclose())


# ── OpenAIChatClient thinking 优化测试 ──────────────────────────────────


def test_openai_client_adds_reasoning_effort_when_thinking_enabled() -> None:
    client = OpenAIChatClient.__new__(OpenAIChatClient)
    client.model = "o3-mini"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="high",
    )
    kwargs = client._build_chat_kwargs(
        messages=[{"role": "user", "content": "Hello"}],
        tools=None,
        temperature=0.7,
        max_tokens=1024,
        request_options=request_options,
    )

    assert kwargs["reasoning_effort"] == "high"
    assert kwargs["temperature"] == 0.7
    assert kwargs["max_tokens"] == 1024


def test_openai_client_does_not_add_reasoning_effort_when_thinking_disabled() -> None:
    client = OpenAIChatClient.__new__(OpenAIChatClient)
    client.model = "gpt-4o"

    kwargs = client._build_chat_kwargs(
        messages=[{"role": "user", "content": "Hello"}],
        tools=None,
        temperature=None,
        max_tokens=None,
        request_options=None,
    )

    assert "reasoning_effort" not in kwargs


# ── AnthropicChatClient adaptive thinking 优化测试 ─────────────────────


def test_anthropic_client_uses_adaptive_thinking_for_opus_46() -> None:
    """Opus 4.6+ 应使用 adaptive thinking + output_config.effort"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-opus-4-6-20251022"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="high",
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options, max_tokens=8192)

    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kwargs["output_config"] == {"effort": "high"}
    assert kwargs["max_tokens"] == 8192  # adaptive 模式下不强制增加 max_tokens


def test_anthropic_client_uses_adaptive_thinking_for_mythos() -> None:
    """Mythos 模型应使用 adaptive thinking"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-mythos-preview"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="max",
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options)

    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kwargs["output_config"] == {"effort": "max"}


def test_anthropic_client_clamps_xhigh_to_high_for_non_opus_47() -> None:
    """xhigh 在 non-Opus-4.7 模型上应 clamp 到 high"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-sonnet-4-6-20251022"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="xhigh",
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options)

    assert kwargs["output_config"] == {"effort": "high"}


def test_anthropic_client_uses_legacy_thinking_for_claude_35() -> None:
    """Claude 3.5 应使用 legacy budget-based thinking"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-3-5-sonnet-20241022"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="medium",
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options, max_tokens=4096)

    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 4096}
    assert kwargs["max_tokens"] >= 4096 + 2048
    assert kwargs["temperature"] == 1  # legacy thinking 强制 temperature=1
    assert "output_config" not in kwargs  # Claude 3.5 不支持 effort 参数


def test_anthropic_client_legacy_thinking_respects_explicit_budget() -> None:
    """Legacy thinking 应优先使用用户显式指定的 budget_tokens"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-3-5-sonnet-20241022"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="low",
        thinking_budget_tokens=8192,
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options)

    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 8192}


def test_anthropic_client_legacy_thinking_for_opus_45_with_effort() -> None:
    """Opus 4.5 是 legacy 模型但支持 output_config.effort"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-opus-4-5-20251022"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="high",
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options)

    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 32000}
    assert kwargs["output_config"] == {"effort": "high"}


def test_anthropic_client_does_not_force_temperature_for_adaptive() -> None:
    """Adaptive thinking 模式下不应强制 temperature=1"""
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-opus-4-7-20251022"

    request_options = LlmRequestOptions(
        thinking_enabled=True,
        thinking_effort="high",
    )
    kwargs = _extract_anthropic_kwargs(client, request_options=request_options, temperature=0.5)

    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kwargs["temperature"] == 0.5


# 辅助函数：提取 AnthropicChatClient 的 kwargs（不实际发起请求）
def _extract_anthropic_kwargs(
    client: AnthropicChatClient,
    *,
    request_options: LlmRequestOptions | None = None,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> dict[str, Any]:
    """通过反射提取 chat_stream 中构造的 kwargs，用于测试参数构造逻辑。"""
    system_msg, anthropic_messages = client._convert_messages(
        [
            {"role": "user", "content": "Hello"},
        ]
    )
    kwargs: dict[str, Any] = {
        "model": client.model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens if max_tokens is not None else 8192,
    }
    if system_msg:
        kwargs["system"] = system_msg
    if temperature is not None:
        kwargs["temperature"] = temperature
    if request_options and request_options.thinking_enabled:
        raw_effort = (request_options.thinking_effort or "medium").strip().lower()
        # 直接调用模块级函数
        from app.services.agent.runtime_backends.aiasys.llm_clients.anthropic_client import (
            _clamp_effort,
            _effort_to_budget,
            _supports_adaptive_thinking,
            _supports_effort_param,
        )

        effort = _clamp_effort(raw_effort, client.model)
        if _supports_adaptive_thinking(client.model):
            kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
            kwargs["output_config"] = {"effort": effort}
        else:
            budget = max(
                int(request_options.thinking_budget_tokens or _effort_to_budget(effort)),
                1024,
            )
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs["max_tokens"] = max(
                int(kwargs.get("max_tokens") or 8192),
                budget + 2048,
            )
            # 模拟原生 Anthropic 端点（测试中统一视为原生端点）
            kwargs["temperature"] = 1
            if _supports_effort_param(client.model):
                kwargs["output_config"] = {"effort": effort}
    return kwargs
