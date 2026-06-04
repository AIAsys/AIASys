from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.api.routes import mcp_session as mcp_session_route
from app.models.mcp import MCPServerConfig


class _FakeSessionService:
    def __init__(self, servers: list[MCPServerConfig]):
        self._servers = servers

    def get_session_mcp_servers(self, user_id: str, session_id: str) -> list[MCPServerConfig]:
        return self._servers


@pytest.mark.asyncio
async def test_session_mcp_test_route_returns_404_when_server_missing() -> None:
    service = _FakeSessionService([])

    with pytest.raises(HTTPException) as exc_info:
        await mcp_session_route.test_mcp_connection(
            session_id="session-1",
            server_name="missing",
            user_id="user-1",
            service=service,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_session_mcp_test_route_uses_real_helper_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = MCPServerConfig(
        name="test-server",
        type="streamable-http",
        url="http://localhost:13004/mcp",
        enabled=True,
    )
    service = _FakeSessionService([server])

    async def _fake_test_connection(server_config: MCPServerConfig):
        assert server_config.name == "test-server"
        return mcp_session_route.TestConnectionResponse(
            status="connected",
            tools_count=7,
            message="连接成功",
        )

    monkeypatch.setattr(
        mcp_session_route,
        "_test_session_server_connection",
        _fake_test_connection,
    )

    response = await mcp_session_route.test_mcp_connection(
        session_id="session-1",
        server_name="test-server",
        user_id="user-1",
        service=service,
    )

    assert response.status == "connected"
    assert response.tools_count == 7
    assert response.message == "连接成功"
