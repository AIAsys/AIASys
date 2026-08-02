"""中立 IR 收敛测试：finish_reason 归一化 + thinking signature 三态透传。

对应设计文档《Message 中立 IR 与多协议投影设计》P0 两项：
- 3.1 thinking signature 透传三态（signed / unsigned+兼容后端 / unsigned+Claude 官方）
- 3.2 finish_reason 归一化枚举 + raw 逃生舱

其中两个可复现故障：
1. Anthropic 流：message_delta 给出 stop_reason=tool_use 后，message_stop 与
   末尾 usage chunk 无条件发 "stop"，把 tool_calls 覆盖掉，导致 ReAct 循环
   在工具执行后直接 break（多步工具调用断裂）。
2. Responses 流：从不产出 tool_calls 语义，response.completed 一律 "stop"，
   同样导致多步工具调用断裂。
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.services.agent.runtime_backends.aiasys.llm_clients.anthropic_client import (
    AnthropicChatClient,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.base import (
    FinishReason,
    normalize_openai_finish_reason,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.codex_client import (
    CodexChatClient,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.message_protocol import (
    normalize_internal_message,
    to_anthropic_messages,
)

# ── 测试脚手架 ──────────────────────────────────────────────────────────


class _ScriptedAnthropicStream:
    """按给定事件列表回放 Anthropic 流，并可选返回 final usage。"""

    def __init__(self, events: list[Any], final_usage: Any = None) -> None:
        self._events = list(events)
        self._final_usage = final_usage

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        self._iter = iter(self._events)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None

    async def get_final_message(self):
        return SimpleNamespace(usage=self._final_usage)


class _ScriptedAnthropicMessages:
    def __init__(self, events: list[Any], final_usage: Any = None) -> None:
        self._events = events
        self._final_usage = final_usage
        self.last_kwargs: dict[str, Any] | None = None

    def stream(self, **kwargs):
        self.last_kwargs = kwargs
        return _ScriptedAnthropicStream(self._events, self._final_usage)


def _make_anthropic_client(events: list[Any], final_usage: Any = None) -> AnthropicChatClient:
    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client.model = "claude-sonnet-4"
    client._base_url = "https://api.anthropic.com"
    client._tool_use_blocks = {}
    client._client = SimpleNamespace(messages=_ScriptedAnthropicMessages(events, final_usage))
    return client


def _anthropic_tool_use_events() -> list[Any]:
    """模拟真实 Anthropic 事件顺序：tool_use 块 → message_delta → message_stop。"""
    return [
        SimpleNamespace(
            type="content_block_start",
            index=0,
            content_block=SimpleNamespace(
                type="tool_use",
                id="toolu_abc",
                name="ReadFile",
                input={},
            ),
        ),
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="input_json_delta", partial_json='{"path":"a.py"}'),
        ),
        SimpleNamespace(
            type="message_delta",
            delta=SimpleNamespace(stop_reason="tool_use"),
        ),
        SimpleNamespace(type="message_stop"),
    ]


class _ScriptedResponsesStream:
    def __init__(self, events: list[Any]) -> None:
        self._events = list(events)

    def __aiter__(self):
        self._iter = iter(self._events)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration from None


def _make_codex_client(events: list[Any]) -> CodexChatClient:
    client = CodexChatClient.__new__(CodexChatClient)
    client.model = "gpt-5-codex"

    async def _create(**_kwargs):
        return _ScriptedResponsesStream(events)

    client._client = SimpleNamespace(responses=SimpleNamespace(create=_create))
    return client


async def _collect_finish_reasons(client, **overrides) -> list[str]:
    kwargs: dict[str, Any] = {
        "messages": [{"role": "user", "content": "hi"}],
        "tools": None,
        "temperature": None,
        "max_tokens": 1024,
    }
    kwargs.update(overrides)
    return [
        chunk.finish_reason
        async for chunk in client.chat_stream(**kwargs)
        if chunk.finish_reason is not None
    ]


# ── 故障 1：Anthropic tool_calls 被 stop 覆盖 ───────────────────────────


async def test_anthropic_tool_use_finish_reason_survives_message_stop() -> None:
    """message_stop / 末尾 usage chunk 不得把 tool_calls 覆盖成 completed。"""
    client = _make_anthropic_client(
        _anthropic_tool_use_events(),
        final_usage=SimpleNamespace(input_tokens=10, output_tokens=5),
    )

    reasons = await _collect_finish_reasons(client)

    assert reasons, "至少应产出一个 finish_reason"
    # ReAct 循环取的是「最后一个非空 finish_reason」，它决定是否继续下一轮
    assert reasons[-1] == "tool_calls"
    assert all(reason == "tool_calls" for reason in reasons)


async def test_anthropic_plain_answer_finish_reason_is_completed() -> None:
    events = [
        SimpleNamespace(
            type="content_block_delta",
            index=0,
            delta=SimpleNamespace(type="text_delta", text="答案"),
        ),
        SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="end_turn")),
        SimpleNamespace(type="message_stop"),
    ]
    client = _make_anthropic_client(events)

    reasons = await _collect_finish_reasons(client)

    assert reasons[-1] == "completed"


async def test_anthropic_max_tokens_maps_to_truncated() -> None:
    events = [
        SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="max_tokens")),
        SimpleNamespace(type="message_stop"),
    ]
    client = _make_anthropic_client(events)

    reasons = await _collect_finish_reasons(client)

    assert reasons[-1] == "truncated"


async def test_anthropic_unknown_stop_reason_falls_back_to_other_with_raw() -> None:
    events = [
        SimpleNamespace(type="message_delta", delta=SimpleNamespace(stop_reason="pause_turn")),
    ]
    client = _make_anthropic_client(events)

    chunks = [
        chunk
        async for chunk in client.chat_stream(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            temperature=None,
            max_tokens=1024,
        )
        if chunk.finish_reason is not None
    ]

    assert chunks[-1].finish_reason == "paused"
    assert chunks[-1].raw_finish_reason == "pause_turn"


# ── 故障 2：Responses 协议从不产出 tool_calls ───────────────────────────


async def test_responses_completed_with_tool_call_maps_to_tool_calls() -> None:
    """Responses 在工具调用场景只报 completed，需按是否出现 tool_call 修正。"""
    events = [
        SimpleNamespace(
            type="response.output_item.added",
            item=SimpleNamespace(type="function_call", call_id="call_1", name="ReadFile", arguments="{}"),
        ),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(
                usage=SimpleNamespace(input_tokens=8, output_tokens=3),
            ),
        ),
    ]
    client = _make_codex_client(events)

    reasons = await _collect_finish_reasons(client)

    assert reasons[-1] == "tool_calls"


async def test_responses_completed_without_tool_call_maps_to_completed() -> None:
    events = [
        SimpleNamespace(type="response.output_text.delta", delta="答案"),
        SimpleNamespace(
            type="response.completed",
            response=SimpleNamespace(usage=SimpleNamespace(input_tokens=8, output_tokens=3)),
        ),
    ]
    client = _make_codex_client(events)

    reasons = await _collect_finish_reasons(client)

    assert reasons[-1] == "completed"


# ── OpenAI Chat 归一化映射 ─────────────────────────────────────────────


def test_openai_finish_reason_normalization_table() -> None:
    assert normalize_openai_finish_reason("stop") == "completed"
    assert normalize_openai_finish_reason("length") == "truncated"
    assert normalize_openai_finish_reason("tool_calls") == "tool_calls"
    assert normalize_openai_finish_reason("function_call") == "tool_calls"
    assert normalize_openai_finish_reason("content_filter") == "filtered"
    assert normalize_openai_finish_reason(None) is None
    assert normalize_openai_finish_reason("brand_new_value") == "other"


def test_finish_reason_literal_covers_normalized_values() -> None:
    assert set(FinishReason.__args__) == {
        "completed",
        "tool_calls",
        "truncated",
        "filtered",
        "paused",
        "other",
    }


# ── thinking signature 三态投影 ────────────────────────────────────────


def _assistant_with_reasoning(**extra: Any) -> list[dict[str, Any]]:
    message: dict[str, Any] = {
        "role": "assistant",
        "content": "先调用工具",
        "reasoning_content": "我需要先读文件",
    }
    message.update(extra)
    return [message]


def test_signed_thinking_keeps_real_signature() -> None:
    _, converted = to_anthropic_messages(
        _assistant_with_reasoning(reasoning_signature="sig-abc123"),
        is_native_anthropic=True,
    )

    assert converted[0]["content"][0] == {
        "type": "thinking",
        "thinking": "我需要先读文件",
        "signature": "sig-abc123",
    }


def test_unsigned_thinking_dropped_for_native_claude() -> None:
    """Claude 官方拒绝无签名 thinking，只能丢弃，绝不伪造空签名。"""
    _, converted = to_anthropic_messages(
        _assistant_with_reasoning(),
        is_native_anthropic=True,
    )

    blocks = converted[0]["content"]
    assert all(block.get("type") != "thinking" for block in blocks)
    assert blocks == [{"type": "text", "text": "先调用工具"}]


def test_unsigned_thinking_kept_without_signature_key_for_compatible_backend() -> None:
    """Anthropic 兼容后端（Kimi 等）保留 thinking，但不能带空 signature。"""
    _, converted = to_anthropic_messages(
        _assistant_with_reasoning(),
        is_native_anthropic=False,
    )

    thinking_blocks = [
        block for block in converted[0]["content"] if block.get("type") == "thinking"
    ]
    assert thinking_blocks == [{"type": "thinking", "thinking": "我需要先读文件"}]
    assert "signature" not in thinking_blocks[0]


def test_signed_thinking_in_tool_call_message_keeps_signature() -> None:
    """带 tool_calls 的 assistant 走 _build_anthropic_assistant_blocks 分支。"""
    messages = _assistant_with_reasoning(
        reasoning_signature="sig-xyz",
        tool_calls=[
            {
                "id": "toolu_1",
                "type": "function",
                "function": {"name": "ReadFile", "arguments": '{"path":"a.py"}'},
            }
        ],
    )

    _, converted = to_anthropic_messages(messages, is_native_anthropic=True)

    blocks = converted[0]["content"]
    assert blocks[0] == {
        "type": "thinking",
        "thinking": "我需要先读文件",
        "signature": "sig-xyz",
    }
    assert blocks[-1]["type"] == "tool_use"


def test_unsigned_thinking_dropped_in_tool_call_message_for_native_claude() -> None:
    messages = _assistant_with_reasoning(
        tool_calls=[
            {
                "id": "toolu_1",
                "type": "function",
                "function": {"name": "ReadFile", "arguments": "{}"},
            }
        ],
    )

    _, converted = to_anthropic_messages(messages, is_native_anthropic=True)

    blocks = converted[0]["content"]
    assert all(block.get("type") != "thinking" for block in blocks)
    assert blocks[-1]["type"] == "tool_use"


def test_no_empty_signature_ever_emitted() -> None:
    """回归护栏：任何投影路径都不得产出 signature="" 。"""
    for native in (True, False):
        for extra in ({}, {"reasoning_signature": ""}):
            _, converted = to_anthropic_messages(
                _assistant_with_reasoning(**extra),
                is_native_anthropic=native,
            )
            for message in converted:
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for block in content:
                    assert block.get("signature") != "", f"native={native} extra={extra}"


# ── 中立 IR 契约 ───────────────────────────────────────────────────────


def test_normalize_internal_message_preserves_reasoning_signature() -> None:
    normalized = normalize_internal_message(
        {
            "role": "assistant",
            "content": "答案",
            "reasoning_content": "推理",
            "reasoning_signature": "sig-1",
        }
    )

    assert normalized["reasoning_signature"] == "sig-1"


def test_normalize_internal_message_omits_blank_reasoning_signature() -> None:
    normalized = normalize_internal_message(
        {
            "role": "assistant",
            "content": "答案",
            "reasoning_signature": "   ",
        }
    )

    assert "reasoning_signature" not in normalized


# ── redacted_thinking 独立块往返 ────────────────────────────────────────
#
# redacted_thinking 的 data 与 thinking 的 signature 是两种不同语义，必须分字段
# 承载：前者回灌为独立的 {"type":"redacted_thinking","data":...} 块，后者是
# thinking 块的属性。曾因共用 reasoning_signature 一个字段导致两类缺陷——
# 只有 redacted 无可读 thinking 时 data 被整块丢弃；两者并存时 data 覆盖真签名
# 并以错误的块类型发出。实证见 aiasys-labs/redacted-thinking-roundtrip/。


def test_redacted_thinking_alone_emits_independent_block() -> None:
    """只有加密块、无可读 thinking：仍须发出 redacted_thinking 块。"""
    normalized = normalize_internal_message(
        {
            "role": "assistant",
            "content": "结论如上。",
            "reasoning_redacted_data": "redacted-data-1",
        }
    )

    _, converted = to_anthropic_messages([dict(normalized)], is_native_anthropic=True)
    blocks = converted[0]["content"]

    redacted = [b for b in blocks if b.get("type") == "redacted_thinking"]
    assert len(redacted) == 1
    assert redacted[0]["data"] == "redacted-data-1"
    # 不应凭空造出 thinking 块
    assert not [b for b in blocks if b.get("type") == "thinking"]


def test_redacted_thinking_coexists_with_signed_thinking() -> None:
    """两类块并存：各自投影，加密 data 不得覆盖真签名。"""
    normalized = normalize_internal_message(
        {
            "role": "assistant",
            "content": "结论如上。",
            "reasoning_content": "可读推理",
            "reasoning_signature": "real-sig",
            "reasoning_redacted_data": "redacted-data-2",
        }
    )

    _, converted = to_anthropic_messages([dict(normalized)], is_native_anthropic=True)
    blocks = converted[0]["content"]

    thinking = [b for b in blocks if b.get("type") == "thinking"]
    redacted = [b for b in blocks if b.get("type") == "redacted_thinking"]

    assert len(thinking) == 1
    assert thinking[0]["signature"] == "real-sig"
    assert len(redacted) == 1
    assert redacted[0]["data"] == "redacted-data-2"


def test_redacted_thinking_survives_compatible_backend() -> None:
    """兼容后端同样要回灌加密块（该块与签名策略无关）。"""
    normalized = normalize_internal_message(
        {
            "role": "assistant",
            "content": "结论。",
            "reasoning_redacted_data": "redacted-data-3",
        }
    )

    _, converted = to_anthropic_messages([dict(normalized)], is_native_anthropic=False)
    blocks = converted[0]["content"]

    redacted = [b for b in blocks if b.get("type") == "redacted_thinking"]
    assert len(redacted) == 1
    assert redacted[0]["data"] == "redacted-data-3"


def test_normalize_internal_message_omits_blank_redacted_data() -> None:
    normalized = normalize_internal_message(
        {
            "role": "assistant",
            "content": "答案",
            "reasoning_redacted_data": "   ",
        }
    )

    assert "reasoning_redacted_data" not in normalized


def test_anthropic_client_maps_redacted_block_to_dedicated_field() -> None:
    """client 侧：redacted_thinking 事件必须写入独立字段，不得混入 signature。"""
    from types import SimpleNamespace

    from app.services.agent.runtime_backends.aiasys.llm_clients.anthropic_client import (
        AnthropicChatClient,
    )

    client = AnthropicChatClient.__new__(AnthropicChatClient)
    client._tool_use_blocks = {}
    client._finish_reason = None
    client._raw_finish_reason = None
    client._base_url = ""

    event = SimpleNamespace(
        type="content_block_start",
        index=0,
        content_block=SimpleNamespace(type="redacted_thinking", data="enc-payload"),
    )
    chunk = AnthropicChatClient._normalize_event(client, event)

    assert chunk is not None
    assert chunk.delta.reasoning_redacted_data == "enc-payload"
    assert chunk.delta.reasoning_signature is None
