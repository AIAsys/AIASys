"""测试 ToolRegistry.invoke_stream 和流式工具基础设施。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry
from app.services.agent.runtime_backends.base import AgentRuntimeEvent
from app.services.agent.runtime_backends.aiasys.tools.task_tool import (
    _annotate_subagent_runtime_event,
    _streaming_event,
)


class EchoTool(AiasysTool):
    """简单的非流式工具。"""

    name = "Echo"
    description = "Echo tool"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}}

    async def invoke(self, ctx, **kwargs):
        return ToolResult(content=kwargs.get("text", ""))


class StreamingEchoTool(AiasysTool):
    """流式工具，产生中间事件和最终结果。"""

    name = "StreamingEcho"
    description = "Streaming echo tool"
    parameters = {"type": "object", "properties": {"text": {"type": "string"}}}

    async def invoke(self, ctx, **kwargs):
        # 默认同步实现（流式工具主要用 invoke_stream）
        return ToolResult(content=kwargs.get("text", ""))

    async def invoke_stream(self, ctx, **kwargs):
        text = kwargs.get("text", "")
        # yield 中间事件
        event = AgentRuntimeEvent(
            kind="content",
            content_type="text",
            text=f"streaming: {text}",
        )
        yield ToolResult(
            content="",
            is_error=False,
            artifacts=[{"_streaming_event": event}],
        )
        # yield 最终结果
        yield ToolResult(content=f"done: {text}")


@pytest.mark.asyncio
async def test_non_streaming_tool_via_invoke_stream():
    registry = ToolRegistry()
    registry.register(EchoTool())

    results = []
    async for ev in registry.invoke_stream("Echo", {"text": "hello"}):
        results.append(ev)

    assert len(results) == 1
    assert results[0].kind == "result"
    assert results[0].tool_result.content == "hello"


@pytest.mark.asyncio
async def test_streaming_tool_yields_events_and_result():
    registry = ToolRegistry()
    registry.register(StreamingEchoTool())

    events = []
    async for ev in registry.invoke_stream("StreamingEcho", {"text": "world"}):
        events.append(ev)

    assert len(events) == 2
    # 第一个是中间事件
    assert events[0].kind == "event"
    assert events[0].runtime_event is not None
    assert events[0].runtime_event.text == "streaming: world"
    # 第二个是最终结果
    assert events[1].kind == "result"
    assert events[1].tool_result.content == "done: world"


@pytest.mark.asyncio
async def test_streaming_tool_via_alias():
    registry = ToolRegistry()
    registry.register(StreamingEchoTool())

    events = []
    async for ev in registry.invoke_stream("streaming_echo", {"text": "alias"}):
        events.append(ev)

    assert len(events) == 2


@pytest.mark.asyncio
async def test_invoke_stream_unknown_tool():
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        async for _ in registry.invoke_stream("Unknown", {}):
            pass


def test_streaming_event_serializes_slots_dataclass() -> None:
    result = _streaming_event(
        AgentRuntimeEvent(kind="content", content_type="text", text="hello")
    )

    assert result.artifacts is not None
    payload = result.artifacts[0]["_streaming_event"]
    assert payload["kind"] == "content"
    assert payload["content_type"] == "text"
    assert payload["text"] == "hello"


def test_annotate_subagent_runtime_event_backfills_identity_fields() -> None:
    event = AgentRuntimeEvent(kind="content", content_type="text", text="hello")

    enriched = _annotate_subagent_runtime_event(
        event,
        agent_id="worker_123",
        subagent_name="worker",
    )

    assert enriched.agent_id == "worker_123"
    assert enriched.subagent_type == "worker"
    assert enriched.subagent_name == "worker"


def test_annotate_subagent_runtime_event_preserves_existing_identity_fields() -> None:
    event = AgentRuntimeEvent(
        kind="tool_call",
        tool_name="Echo",
        agent_id="existing-agent",
        subagent_type="reviewer",
        subagent_name="代码审查节点",
    )

    enriched = _annotate_subagent_runtime_event(
        event,
        agent_id="worker_123",
        subagent_name="worker",
    )

    assert enriched.agent_id == "existing-agent"
    assert enriched.subagent_type == "reviewer"
    assert enriched.subagent_name == "代码审查节点"
