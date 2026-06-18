"""MCPClient 单元测试。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.runtime_backends.aiasys.mcp_client import MCPClient


class _FakeReadStream:
    pass


class _FakeWriteStream:
    pass


@pytest.fixture
def mock_stdio_client():
    """Mock stdio_client async context manager。"""
    with patch("app.services.agent.runtime_backends.aiasys.mcp_client.stdio_client") as mock:
        mock.return_value.__aenter__ = AsyncMock(
            return_value=(_FakeReadStream(), _FakeWriteStream())
        )
        mock.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock


@pytest.fixture
def mock_client_session():
    """Mock ClientSession async context manager。"""
    with patch("app.services.agent.runtime_backends.aiasys.mcp_client.ClientSession") as mock_cls:
        session = AsyncMock()
        session.initialize = AsyncMock()
        session.list_tools = AsyncMock()
        session.call_tool = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=session)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        yield mock_cls, session


class _FakeHttpTransportContext:
    async def __aenter__(self):
        return (_FakeReadStream(), _FakeWriteStream(), lambda: "session-id")

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_mcp_client_connects_stdio(mock_stdio_client, mock_client_session):
    client = MCPClient("test-server", {"command": "echo", "args": ["hello"]})
    await client.connect()

    mock_stdio_client.assert_called_once()
    mock_client_session[0].assert_called_once()
    mock_client_session[1].initialize.assert_awaited_once()

    assert client._session is not None


@pytest.mark.asyncio
async def test_mcp_client_accepts_streamable_http_session_callback(
    mock_client_session,
):
    with patch(
        "app.services.agent.runtime_backends.aiasys.mcp_client._import_streamablehttp_client"
    ) as mock_import:
        mock_streamablehttp_client = MagicMock(return_value=_FakeHttpTransportContext())
        mock_import.return_value = mock_streamablehttp_client

        client = MCPClient(
            "test-http",
            {
                "transport": "streamable-http",
                "url": "https://mcp.example.com/mcp",
                "headers": {"Authorization": "Bearer test-key"},
            },
        )
        await client.connect()

        mock_streamablehttp_client.assert_called_once_with(
            "https://mcp.example.com/mcp",
            headers={"Authorization": "Bearer test-key"},
            timeout=None,
        )
        mock_client_session[0].assert_called_once()
        mock_client_session[1].initialize.assert_awaited_once()
        assert client._session is not None


@pytest.mark.asyncio
async def test_mcp_client_converts_sdk_cancel_scope_error(
    mock_stdio_client,
    mock_client_session,
):
    mock_client_session[1].initialize = AsyncMock(
        side_effect=asyncio.CancelledError("Cancelled via cancel scope test")
    )

    client = MCPClient("cancelled-server", {"command": "test-cmd"})

    with pytest.raises(RuntimeError, match="cancelled-server.*cancel scope"):
        await client.connect()
    assert client._session is None


@pytest.mark.asyncio
async def test_mcp_client_list_tools_returns_tools(mock_stdio_client, mock_client_session):
    from mcp.types import Tool

    session = mock_client_session[1]
    session.list_tools.return_value = MagicMock(
        tools=[
            Tool(name="get_time", description="Get current time", inputSchema={"type": "object"}),
            Tool(name="get_date", description="Get current date", inputSchema={"type": "object"}),
        ]
    )

    client = MCPClient("test-server", {"command": "test-cmd"})
    await client.connect()
    tools = await client.list_tools()

    assert len(tools) == 2
    assert tools[0].name == "get_time"
    assert tools[1].name == "get_date"


@pytest.mark.asyncio
async def test_mcp_client_call_tool_forwards_arguments(mock_stdio_client, mock_client_session):
    from mcp.types import CallToolResult, TextContent

    session = mock_client_session[1]
    session.call_tool.return_value = CallToolResult(
        content=[TextContent(type="text", text="result")],
        isError=False,
    )

    client = MCPClient("test-server", {"command": "test-cmd"})
    await client.connect()
    result = await client.call_tool("do_something", {"arg1": "value1"})

    session.call_tool.assert_awaited_once_with("do_something", {"arg1": "value1"})
    assert result.isError is False
    assert len(result.content) == 1


@pytest.mark.asyncio
async def test_mcp_client_close_cleans_up(mock_stdio_client, mock_client_session):
    client = MCPClient("test-server", {"command": "test-cmd"})
    await client.connect()
    assert client._session is not None

    await client.close()
    assert client._session is None


@pytest.mark.asyncio
async def test_mcp_client_close_swallows_sdk_cancel_scope_error():
    client = MCPClient("cancel-close-server", {"command": "test-cmd"})
    client._session = MagicMock()
    client._exit_stack.aclose = AsyncMock(
        side_effect=asyncio.CancelledError("Attempted to exit a cancel scope")
    )

    await client.close()

    assert client._session is None


@pytest.mark.asyncio
async def test_mcp_client_missing_command_raises():
    client = MCPClient("bad-server", {})
    with pytest.raises(ValueError, match="缺少 command"):
        await client.connect()


@pytest.mark.asyncio
async def test_mcp_client_list_tools_without_connect_raises(mock_stdio_client, mock_client_session):
    client = MCPClient("test-server", {"command": "test-cmd"})
    with pytest.raises(RuntimeError, match="未连接"):
        await client.list_tools()
