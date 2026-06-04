from __future__ import annotations

import types

import pytest

from app.api.routes import mcp as mcp_route
from app.api.routes import mcp_session as mcp_session_route
from app.models.mcp import MCPServerConfig
from app.models.user import UserInfo


class _FakeTool:
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description


class _FakeTools:
    tools = [
        _FakeTool(name="tool_a", description="Tool A"),
        _FakeTool(name="tool_b", description="Tool B"),
    ]


class _FakeClientSession:
    def __init__(self, read, write):
        self.read = read
        self.write = write

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def initialize(self):
        return None

    async def list_tools(self):
        return _FakeTools()


class _FakeTransportContext:
    async def __aenter__(self):
        return ("read", "write", None)

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_session_connection_helper_passes_headers_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_streamablehttp_client(url, *, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeTransportContext()

    monkeypatch.setattr("mcp.ClientSession", _FakeClientSession)
    monkeypatch.setattr(
        "mcp.client.streamable_http.streamablehttp_client",
        _fake_streamablehttp_client,
    )

    server = MCPServerConfig(
        name="test_server",
        type="streamable-http",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer test-key"},
        timeout_ms=4200,
    )

    response = await mcp_session_route._test_session_server_connection(server)

    assert response.status == "connected"
    assert response.tools_count == 2
    assert captured == {
        "url": "https://mcp.example.com/mcp",
        "headers": {"Authorization": "Bearer test-key"},
        "timeout": 4.2,
    }


class _FakeMCPConfigService:
    def __init__(self, server: MCPServerConfig):
        self.server = server

    def get_server_config(self, user_id: str, server_name: str) -> MCPServerConfig | None:
        if server_name == self.server.name:
            return self.server
        return None


@pytest.mark.asyncio
async def test_global_connection_route_passes_headers_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def _fake_streamablehttp_client(url, *, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _FakeTransportContext()

    monkeypatch.setattr("mcp.ClientSession", _FakeClientSession)
    monkeypatch.setattr(
        "mcp.client.streamable_http.streamablehttp_client",
        _fake_streamablehttp_client,
    )

    server = MCPServerConfig(
        name="test_server",
        type="streamable-http",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer test-key"},
        timeout_ms=5300,
    )

    monkeypatch.setattr(
        mcp_route,
        "get_mcp_config_service",
        lambda: _FakeMCPConfigService(server),
    )

    response = await mcp_route.test_mcp_store_connection(
        "test_server",
        current_user=UserInfo(user_id="test-user"),
    )

    assert response.status == "connected"
    assert response.tools_count == 2
    assert captured == {
        "url": "https://mcp.example.com/mcp",
        "headers": {"Authorization": "Bearer test-key"},
        "timeout": 5.3,
    }
