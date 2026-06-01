"""
Tests for AIASys context compaction mechanism.
"""

from __future__ import annotations

import pytest
from typing import Any

from app.services.agent.compaction import (
    CompactionResult,
    SimpleCompaction,
    estimate_text_tokens,
    filter_messages_for_compaction,
    should_auto_compact,
    snip_messages_for_compaction,
)
from app.services.agent.runtime_backends.aiasys.llm_clients.base import (
    BaseLlmClient,
    LlmChunk,
    LlmDelta,
)
from app.services.agent.runtime_backends.aiasys.session_compaction import (
    SessionCompactionMixin,
)


class FakeLlmClient(BaseLlmClient):
    """Mock LLM client that yields predefined chunks."""

    def __init__(self, response_text: str = "Summary text.") -> None:
        self.response_text = response_text
        self.last_messages: list[dict[str, Any]] | None = None
        self.last_max_tokens: int | None = None

    async def chat_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        temperature: float | None,
        max_tokens: int | None,
        request_options=None,
    ):
        del request_options
        self.last_messages = messages
        self.last_max_tokens = max_tokens
        # Yield the response in one chunk
        yield LlmChunk(delta=LlmDelta(content=self.response_text))
        yield LlmChunk(delta=LlmDelta(), finish_reason="stop")

    async def aclose(self) -> None:
        pass


class FakeFailingLlmClient(BaseLlmClient):
    """Mock LLM client that always raises inside the async generator."""

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        # Need at least one yield to be recognized as async generator
        if False:
            yield LlmChunk(delta=LlmDelta())
        raise RuntimeError("LLM call failed")

    async def aclose(self) -> None:
        pass


class FakeUsageLlmClient(BaseLlmClient):
    """Mock LLM client that returns usage info."""

    def __init__(self, response_text: str = "Summary.", usage: dict[str, Any] | None = None) -> None:
        self.response_text = response_text
        self.usage = usage

    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        yield LlmChunk(delta=LlmDelta(content=self.response_text), usage=self.usage)
        yield LlmChunk(delta=LlmDelta(), finish_reason="stop")

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# estimate_text_tokens
# ---------------------------------------------------------------------------


class TestEstimateTextTokens:
    def test_simple_text(self):
        messages = [{"role": "user", "content": "Hello world"}]
        # 11 chars // 4 = 2
        assert estimate_text_tokens(messages) == 2

    def test_multimodal_text_only(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Hello"},
                    {"type": "image_url", "image_url": {"url": "data:..."}},
                ],
            }
        ]
        # Only text part counted: 5 // 4 = 1
        assert estimate_text_tokens(messages) == 1

    def test_reasoning_content_excluded(self):
        """reasoning_content 不计入压缩估算。"""
        messages = [
            {
                "role": "assistant",
                "content": "Answer",
                "reasoning_content": "Let me think...",
            }
        ]
        # Only content counted: 6 // 4 = 1
        assert estimate_text_tokens(messages) == 1

    def test_empty_messages(self):
        assert estimate_text_tokens([]) == 0

    def test_all_non_text_parts_yield_zero(self):
        messages = [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]},
        ]
        assert estimate_text_tokens(messages) == 0


# ---------------------------------------------------------------------------
# should_auto_compact
# ---------------------------------------------------------------------------


class TestShouldAutoCompact:
    def test_ratio_trigger(self):
        assert should_auto_compact(90, 100, trigger_ratio=0.85) is True
        assert should_auto_compact(80, 100, trigger_ratio=0.85) is False

    def test_reserved_trigger(self):
        assert should_auto_compact(60, 100, reserved_context_size=50) is True
        assert should_auto_compact(40, 100, reserved_context_size=50) is False

    def test_zero_max_context(self):
        assert should_auto_compact(100, 0) is False

    def test_no_reserved(self):
        assert should_auto_compact(90, 100, trigger_ratio=0.85, reserved_context_size=0) is True

    def test_200k_model_triggers_by_reserved(self):
        """200K model: reserved (50K) fires first at 150K."""
        assert should_auto_compact(
            150_000, 200_000, trigger_ratio=0.85, reserved_context_size=50_000
        )

    def test_1m_model_triggers_by_ratio(self):
        """1M model: ratio (85%) fires first at 850K."""
        assert should_auto_compact(
            850_000, 1_000_000, trigger_ratio=0.85, reserved_context_size=50_000
        )


# ---------------------------------------------------------------------------
# filter_messages_for_compaction
# ---------------------------------------------------------------------------


class TestFilterMessagesForCompaction:
    def test_filters_tool_messages(self):
        """Tool messages are now preserved (after snip) to keep tool pairs intact."""
        messages = [
            {"role": "user", "content": "Run cmd"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "output", "tool_call_id": "1"},
        ]
        filtered = filter_messages_for_compaction(messages)
        roles = [m["role"] for m in filtered]
        assert "tool" in roles
        assert "user" in roles
        assert "assistant" in roles

    def test_filters_images(self):
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this"},
                    {"type": "image_url", "image_url": {"url": "data:base64"}},
                ],
            }
        ]
        filtered = filter_messages_for_compaction(messages)
        assert filtered[0]["content"] == "Describe this"

    def test_all_non_text_becomes_placeholder(self):
        messages = [
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]},
        ]
        filtered = filter_messages_for_compaction(messages)
        assert "non-text content" in filtered[0]["content"]

    def test_drops_reasoning_content(self):
        """Think blocks / reasoning_content are dropped from compaction input."""
        messages = [
            {"role": "assistant", "content": "Answer", "reasoning_content": "Thinking..."},
        ]
        filtered = filter_messages_for_compaction(messages)
        assert "reasoning_content" not in filtered[0]
        assert filtered[0]["content"] == "Answer"

    def test_assistant_tool_calls_without_content(self):
        """Assistant messages with only tool_calls get a placeholder."""
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [{"id": "1"}]},
        ]
        filtered = filter_messages_for_compaction(messages)
        assert "tool calls" in filtered[0]["content"]


# ---------------------------------------------------------------------------
# snip_messages_for_compaction
# ---------------------------------------------------------------------------


class TestSnipMessagesForCompaction:
    def test_short_text_unchanged(self):
        messages = [{"role": "tool", "content": "short"}]
        result = snip_messages_for_compaction(messages)
        assert result[0]["content"] == "short"

    def test_long_text_snipped(self):
        long_text = "a" * 3000
        messages = [{"role": "tool", "content": long_text}]
        result = snip_messages_for_compaction(messages)
        assert "snipped" in result[0]["content"]
        assert len(result[0]["content"]) < len(long_text)

    def test_multimodal_text_snipped(self):
        long_text = "a" * 3000
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": long_text},
                    {"type": "image_url", "image_url": {"url": "x"}},
                ],
            }
        ]
        result = snip_messages_for_compaction(messages)
        assert "snipped" in result[0]["content"][0]["text"]

    def test_snip_preserves_head_and_tail(self):
        text = "HEAD" + "x" * 3000 + "TAIL"
        messages = [{"role": "tool", "content": text}]
        result = snip_messages_for_compaction(messages)
        snipped = result[0]["content"]
        assert snipped.startswith("HEAD")
        assert snipped.endswith("TAIL")


# ---------------------------------------------------------------------------
# SimpleCompaction._select_preserved (with tool pair protection)
# ---------------------------------------------------------------------------


class TestSelectPreserved:
    def test_preserve_last_n_user_assistant(self):
        compactor = SimpleCompaction(max_preserved_messages=2)
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]
        to_compact, to_preserve = compactor._select_preserved(messages)
        # Last 2 user/assistant: u2, a2 (indices 3,4)
        assert len(to_compact) == 3  # system, u1, a1
        assert len(to_preserve) == 2  # u2, a2
        assert to_preserve[0]["role"] == "user"
        assert to_preserve[1]["role"] == "assistant"

    def test_not_enough_messages(self):
        compactor = SimpleCompaction(max_preserved_messages=5)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        to_compact, to_preserve = compactor._select_preserved(messages)
        assert len(to_compact) == 0
        assert len(to_preserve) == 2

    def test_zero_preserve(self):
        compactor = SimpleCompaction(max_preserved_messages=0)
        messages = [{"role": "user", "content": "u1"}]
        to_compact, to_preserve = compactor._select_preserved(messages)
        assert len(to_compact) == 1
        assert len(to_preserve) == 0

    def test_tool_pair_stays_together_in_compact(self):
        """Assistant tool_calls and its tool response should not be split."""
        compactor = SimpleCompaction(max_preserved_messages=1)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "t1", "tool_call_id": "1"},
            {"role": "user", "content": "u2"},
        ]
        to_compact, to_preserve = compactor._select_preserved(messages)
        # Last user/assistant is u2, so to_preserve = [u2]
        # to_compact should contain the full tool pair
        roles = [m["role"] for m in to_compact]
        assert roles == ["user", "assistant", "tool"]

    def test_tool_pair_stays_together_in_preserve(self):
        """When boundary includes assistant(tc), its tool response follows."""
        compactor = SimpleCompaction(max_preserved_messages=2)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "t1", "tool_call_id": "1"},
            {"role": "user", "content": "u2"},
        ]
        to_compact, to_preserve = compactor._select_preserved(messages)
        # max_preserved=2: u2 + assistant(tc) -> boundary at index 1
        # to_preserve = [assistant(tc), tool, u2]
        roles_p = [m["role"] for m in to_preserve]
        assert roles_p == ["assistant", "tool", "user"]
        roles_c = [m["role"] for m in to_compact]
        assert roles_c == ["user"]


# ---------------------------------------------------------------------------
# SimpleCompaction.compact (async)
# ---------------------------------------------------------------------------


class TestCompactAsync:
    @pytest.mark.asyncio
    async def test_compact_success(self):
        compactor = SimpleCompaction(max_preserved_messages=2, max_summary_tokens=500)
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]
        client = FakeLlmClient(response_text="Earlier chat summary.")
        result = await compactor.compact(messages, client)

        assert result.compacted_count == 3  # system, u1, a1
        assert result.preserved_count == 2  # u2, a2
        assert result.summary == "Earlier chat summary."
        # 压缩摘要用 user 角色插回上下文，避免改变 system 基线。
        assert result.messages[0]["role"] == "user"
        assert "compacted" in result.messages[0]["content"].lower()
        assert "Earlier chat summary." in result.messages[0]["content"]
        # Preserved messages follow
        assert result.messages[1]["role"] == "user"
        assert result.messages[2]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_compact_strips_media_from_preserved(self):
        """Multimodal content in preserved messages should be stripped."""
        compactor = SimpleCompaction(max_preserved_messages=2, max_summary_tokens=500)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Look at this:"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,IMG"}},
                ],
            },
            {"role": "assistant", "content": "Nice pic!"},
        ]
        client = FakeLlmClient(response_text="Summary.")
        result = await compactor.compact(messages, client)

        # Preserved user message should have image stripped, text kept
        preserved_user = result.messages[1]
        assert preserved_user["role"] == "user"
        assert preserved_user["content"] == [{"type": "text", "text": "Look at this:"}]
        # Preserved assistant remains intact
        assert result.messages[2]["content"] == "Nice pic!"

    @pytest.mark.asyncio
    async def test_compact_no_action_when_too_few(self):
        compactor = SimpleCompaction(max_preserved_messages=5)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
        ]
        client = FakeLlmClient()
        result = await compactor.compact(messages, client)

        assert result.compacted_count == 0
        assert result.preserved_count == 2
        assert result.messages == messages
        # No LLM call should be made
        assert client.last_messages is None

    @pytest.mark.asyncio
    async def test_compact_uses_custom_instruction(self):
        compactor = SimpleCompaction(max_preserved_messages=1)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
        client = FakeLlmClient()
        await compactor.compact(messages, client, custom_instruction="Focus on code.")

        assert client.last_messages is not None
        last_user_msg = client.last_messages[-1]["content"]
        assert "Focus on code." in last_user_msg
        assert "User's Custom Compaction Instruction" in last_user_msg

    @pytest.mark.asyncio
    async def test_compact_graceful_on_llm_failure(self):
        compactor = SimpleCompaction(max_preserved_messages=1)
        messages = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
        client = FakeFailingLlmClient()
        result = await compactor.compact(messages, client)

        # Should return original messages unchanged
        assert result.compacted_count == 0
        assert result.preserved_count == 3
        assert result.messages == messages

    @pytest.mark.asyncio
    async def test_compact_preserves_tools_in_summary(self):
        """Tool output is now sent to LLM (after snip) to keep tool pairs intact."""
        compactor = SimpleCompaction(max_preserved_messages=1, max_summary_tokens=500)
        messages = [
            {"role": "user", "content": "Run ls"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "file.txt\n", "tool_call_id": "1"},
            {"role": "user", "content": "Next"},
        ]
        client = FakeLlmClient(response_text="User asked to run ls.")
        result = await compactor.compact(messages, client)

        # 3 compacted, 1 preserved (last user)
        assert result.compacted_count == 3
        assert result.preserved_count == 1
        # Check that tool output IS sent to LLM (short content not snipped)
        assert client.last_messages is not None
        summary_input = client.last_messages[-1]["content"]
        assert "file.txt" in summary_input


# ---------------------------------------------------------------------------
# CompactionResult.estimated_token_count
# ---------------------------------------------------------------------------


class TestEstimatedTokenCount:
    def test_with_usage_uses_exact_output_tokens(self):
        """When usage is available, summary uses exact output tokens."""
        result = CompactionResult(
            messages=[
                {"role": "user", "content": "compacted summary"},
                {"role": "user", "content": "a" * 80},  # 80 chars → 20 tokens
            ],
            summary="compacted summary",
            compacted_count=1,
            preserved_count=1,
            usage_output_tokens=150,
        )
        assert result.estimated_token_count() == 150 + 20

    def test_without_usage_estimates_all_from_text(self):
        messages = [
            {"role": "user", "content": "a" * 100},
            {"role": "assistant", "content": "b" * 200},
        ]
        result = CompactionResult(
            messages=messages,
            summary="summary",
            compacted_count=1,
            preserved_count=1,
        )
        assert result.estimated_token_count() == 300 // 4

    def test_empty_messages(self):
        result = CompactionResult(
            messages=[],
            summary="",
            compacted_count=0,
            preserved_count=0,
        )
        assert result.estimated_token_count() == 0


# ---------------------------------------------------------------------------
# SessionCompactionMixin._maybe_compact_context
# ---------------------------------------------------------------------------


class MockLoopControl:
    compaction_trigger_ratio = 0.01  # 极低阈值确保触发
    reserved_context_size = 0
    max_preserved_messages = 1
    max_summary_tokens = 500
    tool_snip_max_chars = 2000


class MockConfig:
    def __init__(self) -> None:
        self.loop_control = MockLoopControl()
        self.task_models: dict[str, Any] = {}
        self.models: dict[str, Any] = {}
        self.providers: dict[str, Any] = {}


class MockSpec:
    def __init__(self) -> None:
        self.config = MockConfig()
        self.work_dir = "/tmp/test"


class _TestSession(SessionCompactionMixin):
    def __init__(self, messages: list[dict[str, Any]], estimated: int) -> None:
        self._spec = MockSpec()
        self.messages = list(messages)
        self._estimated_token_count = estimated
        self._client = FakeLlmClient(response_text="Summary.")
        self._model_config = {"max_context_size": 10000}
        self.session_id = "test-session"

    def _invalidate_system_prompt_snapshot(self) -> None:
        pass


class TestSessionCompactionMixin:
    @pytest.mark.asyncio
    async def test_compaction_restores_system_token_count(self):
        """压缩后 _estimated_token_count 必须包含 system messages 的 token。

        Bug: 压缩前 _estimated_token_count 包含 system messages（通过 _append_message
        累加或 LLM usage 精确值），但压缩后 result.estimated_token_count() 只包含
        compacted_messages，导致 _estimated_token_count 语义不一致，后续触发判断低估。
        """
        system_msg = {"role": "system", "content": "x" * 400}  # 100 tokens
        chat_msgs = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
        ]
        all_msgs = [system_msg, *chat_msgs]
        # 估算: system 100 + chat ~small
        estimated_before = estimate_text_tokens(all_msgs)

        session = _TestSession(all_msgs, estimated_before)
        await session._maybe_compact_context()

        # 压缩后 messages 仍应包含 system message
        assert session.messages[0]["role"] == "system"
        assert session.messages[0]["content"] == system_msg["content"]

        # 关键断言: _estimated_token_count 必须包含 system messages
        system_tokens = estimate_text_tokens([system_msg])
        assert session._estimated_token_count >= system_tokens

        # 更严格的断言: 加上新消息后总估算不应丢失 system 部分
        estimated_after_manual = estimate_text_tokens(session.messages)
        # 允许 result.estimated_token_count() 使用精确 usage 值，所以用上限检查
        assert session._estimated_token_count >= estimated_after_manual - 50

    @pytest.mark.asyncio
    async def test_compaction_preserves_estimated_token_semantics(self):
        """压缩前后 _estimated_token_count 的语义应保持一致（都代表全部消息）。"""
        system_msg = {"role": "system", "content": "s" * 400}
        chat_msgs = [
            {"role": "user", "content": "u1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2"},
            {"role": "assistant", "content": "a2"},
        ]
        all_msgs = [system_msg, *chat_msgs]
        estimated_before = estimate_text_tokens(all_msgs)

        session = _TestSession(all_msgs, estimated_before)
        await session._maybe_compact_context()

        # 压缩后重新估算全部消息的 token
        full_estimate_after = estimate_text_tokens(session.messages)
        # _estimated_token_count 应至少和手动估算接近（允许 usage 精确值的差异）
        assert session._estimated_token_count >= full_estimate_after - 50
        # 但绝不能小于 system messages 的 token（这是原 bug 的表现）
        assert session._estimated_token_count >= estimate_text_tokens([system_msg])


# ---------------------------------------------------------------------------
# Integration: Session-level compaction logic
# ---------------------------------------------------------------------------


class TestSessionCompactionLogic:
    """Tests the decision logic used in session._maybe_compact_context."""

    def test_system_messages_excluded_from_estimation(self):
        """System prompt should not be counted toward compaction threshold."""
        system_msg = {"role": "system", "content": "x" * 400}  # 100 tokens
        chat_msgs = [{"role": "user", "content": "x" * 400}]  # 100 tokens
        all_msgs = [system_msg, *chat_msgs]

        chat_tokens = estimate_text_tokens(chat_msgs)
        all_tokens = estimate_text_tokens(all_msgs)

        assert chat_tokens == 100
        assert all_tokens == 200
        # The session logic splits them before estimating

    def test_trigger_with_only_system(self):
        """If there are only system messages, no compaction should occur."""
        messages = [
            {"role": "system", "content": "sys1"},
            {"role": "system", "content": "sys2"},
        ]
        chat_messages = [m for m in messages if m.get("role") != "system"]
        assert len(chat_messages) == 0
        assert not should_auto_compact(0, 100, trigger_ratio=0.85)
