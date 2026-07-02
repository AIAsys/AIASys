"""BC-015 / 懒创建会话回归测试

覆盖 execute_stream 路由在 session 不存在时的懒创建行为：
- 提供 workspace_id 时，自动创建 workspace conversation
- 未提供 workspace_id 时，保持原有行为（不创建）
- session 已存在时，不重复创建
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import agent as agent_route
from app.models.user import UserInfo
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_client(monkeypatch, tmp_path):
    app = FastAPI()
    app.include_router(agent_route.router)
    app.dependency_overrides[agent_route.require_auth()] = _build_user

    # 使用独立的 workspace registry
    registry = WorkspaceRegistryService(tmp_path)
    monkeypatch.setattr(
        agent_route, "get_workspace_registry_service", lambda: registry
    )

    async def _fake_stream(*args, **kwargs):
        # 空的 SSE 流
        return
        yield  # pragma: no cover - 让函数成为 async generator

    mock_agent_service = AsyncMock()
    mock_agent_service.execute_stream = _fake_stream
    mock_agent_service._session_manager = registry.session_manager

    monkeypatch.setattr(agent_route, "agent_service", mock_agent_service)

    return TestClient(app), registry, mock_agent_service


def test_execute_stream_creates_conversation_when_session_missing_and_workspace_provided(
    monkeypatch, tmp_path
):
    """session 不存在且提供了 workspace_id 时，应懒创建 workspace conversation。"""
    client, registry, mock_agent_service = _build_client(monkeypatch, tmp_path)

    # 先创建工作区
    registry.create_workspace(user_id="local_default", title="Test WS", workspace_id="ws-lazy-001")

    response = client.post(
        "/agent/execute/stream",
        json={
            "prompt": "hello",
            "session_id": "missing-session-001",
            "workspace_id": "ws-lazy-001",
        },
    )

    assert response.status_code == 200
    # 消费 SSE 流，确保 generator 正常结束
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
    # 验证 create_conversation 被调用（懒创建）
    conversations = registry._read_conversation_payloads("local_default", "ws-lazy-001")
    assert any(
        c.get("conversation_id") == "missing-session-001" for c in conversations
    ), "懒创建 conversation 失败"


def test_execute_stream_skips_creation_when_session_exists(
    monkeypatch, tmp_path
):
    """session 已存在时，不应重复创建 conversation。"""
    client, registry, mock_agent_service = _build_client(monkeypatch, tmp_path)

    # 先创建工作区和会话
    registry.create_workspace(
        user_id="local_default",
        title="Test WS",
        workspace_id="ws-lazy-002",
        initial_conversation_id="existing-session-002",
    )

    response = client.post(
        "/agent/execute/stream",
        json={
            "prompt": "hello",
            "session_id": "existing-session-002",
            "workspace_id": "ws-lazy-002",
        },
    )

    assert response.status_code == 200
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
    conversations = registry._read_conversation_payloads("local_default", "ws-lazy-002")
    assert len(conversations) == 1, "不应重复创建 conversation"


def test_execute_stream_skips_creation_when_no_workspace_id(
    monkeypatch, tmp_path
):
    """session 不存在且未提供 workspace_id 时，保持原有行为（不创建）。"""
    client, registry, mock_agent_service = _build_client(monkeypatch, tmp_path)

    response = client.post(
        "/agent/execute/stream",
        json={
            "prompt": "hello",
            "session_id": "missing-no-ws-003",
        },
    )

    assert response.status_code == 200
    for line in response.iter_lines():
        if not line.startswith("data: "):
            continue
        payload = line[6:]
        if payload == "[DONE]":
            break
    # 验证没有创建任何 conversation
    # registry 没有 workspaces，所以 conversations 应为空
    all_conversations = registry._read_conversation_payloads("local_default", "missing-no-ws-003")
    assert all_conversations == [], "未提供 workspace_id 时不应创建 conversation"
