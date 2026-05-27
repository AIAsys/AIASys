"""MCPTool 单元测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.aiasys.tools.mcp_tool import MCPTool


class _FakeMCPClient:
    def __init__(self):
        self.call_tool = AsyncMock()


@pytest.mark.asyncio
async def test_mcp_tool_invokes_mcp_client():
    client = _FakeMCPClient()
    client.call_tool.return_value = MagicMCPResult(content=["hello"], isError=False)

    tool = MCPTool(
        server_name="test-server",
        tool_name="greet",
        description="Say hello",
        input_schema={"type": "object", "properties": {"name": {"type": "string"}}},
        mcp_client=client,
    )

    result = await tool.invoke(name="world")

    client.call_tool.assert_awaited_once_with("greet", {"name": "world"})
    assert isinstance(result, ToolResult)
    assert result.content == "hello"
    assert result.is_error is False


@pytest.mark.asyncio
async def test_mcp_tool_error_returns_is_error():
    client = _FakeMCPClient()
    client.call_tool.return_value = MagicMCPResult(content=["boom"], isError=True)

    tool = MCPTool(
        server_name="test-server",
        tool_name="fail",
        description="Always fail",
        input_schema={"type": "object"},
        mcp_client=client,
    )

    result = await tool.invoke()
    assert result.is_error is True


@pytest.mark.asyncio
async def test_mcp_tool_exception_returns_error_result():
    client = _FakeMCPClient()
    client.call_tool.side_effect = RuntimeError("connection lost")

    tool = MCPTool(
        server_name="test-server",
        tool_name="unreachable",
        description="",
        input_schema={"type": "object"},
        mcp_client=client,
    )

    result = await tool.invoke()
    assert result.is_error is True
    assert "connection lost" in result.content


@pytest.mark.asyncio
async def test_mcp_tool_is_mcp_attribute():
    client = _FakeMCPClient()
    tool = MCPTool(
        server_name="s",
        tool_name="t",
        description="",
        input_schema={},
        mcp_client=client,
    )
    assert getattr(tool, "is_mcp", False) is True


@pytest.mark.asyncio
async def test_mcp_tool_instance_attributes_override_classvar():
    client = _FakeMCPClient()
    tool = MCPTool(
        server_name="s",
        tool_name="MyTool",
        description="A test tool",
        input_schema={"type": "object", "properties": {"x": {"type": "number"}}},
        mcp_client=client,
    )
    assert tool.name == "MyTool"
    assert tool.description == "A test tool"
    assert tool.parameters == {"type": "object", "properties": {"x": {"type": "number"}}}


@pytest.mark.asyncio
async def test_mcp_tool_invoke_stream_yields_single_result():
    client = _FakeMCPClient()
    client.call_tool.return_value = MagicMCPResult(content=["streamed"], isError=False)

    tool = MCPTool(
        server_name="s",
        tool_name="t",
        description="",
        input_schema={},
        mcp_client=client,
    )

    results = [r async for r in tool.invoke_stream()]
    assert len(results) == 1
    assert results[0].content == "streamed"


class MagicMCPResult:
    """最小 mock 对象，模拟 CallToolResult 的 content + isError。"""

    def __init__(self, content: list[Any], isError: bool = False):
        self.content = content
        self.isError = isError
