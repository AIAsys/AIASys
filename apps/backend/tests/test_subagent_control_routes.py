from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routes import sessions_execution as sessions_module
from app.models.user import UserInfo


CURRENT_USER = UserInfo(
    user_id="route-test-user",
    role="admin",
    auth_provider="none",
)


class _FakeTrackingService:
    def __init__(self, detail):
        self._detail = detail

    def get_subagent_detail(self, user_id: str, session_id: str, agent_id: str):
        _ = (user_id, session_id, agent_id)
        return self._detail


class _FakeSessionManager:
    def __init__(
        self,
        *,
        bound_host_session_id: str | None = None,
        conversation_type: str | None = None,
    ) -> None:
        self._metadata = SimpleNamespace(
            bound_host_session_id=bound_host_session_id,
            conversation_type=conversation_type,
        )

    def get_session(self, session_id: str, user_id: str):
        _ = (session_id, user_id)
        return self._metadata


@pytest.mark.asyncio
async def test_stop_subagent_route_delegates_to_agent_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = SimpleNamespace(
        id="agent-1",
        name="worker",
        description="读取数据",
        meta={"status": "running_foreground"},
    )
    calls: list[tuple[str, str, str, str | None]] = []

    async def fake_stop_subagent_execution(
        *,
        user_id: str,
        session_id: str,
        agent_id: str,
        subagent_status: str | None = None,
    ) -> dict[str, str]:
        calls.append((user_id, session_id, agent_id, subagent_status))
        return {"status": "accepted", "mode": "host_session_cancelled"}

    monkeypatch.setattr(
        sessions_module.agent_service,
        "stop_subagent_execution",
        fake_stop_subagent_execution,
    )

    result = await sessions_module.stop_subagent(
        user_id="route-test-user",
        session_id="session-1",
        agent_id="agent-1",
        current_user=CURRENT_USER,
        tracking_service=_FakeTrackingService(detail),
    )

    assert result["status"] == "accepted"
    assert calls == [("route-test-user", "session-1", "agent-1", "running_foreground")]


@pytest.mark.asyncio
async def test_retry_subagent_route_passes_prompt_and_output_excerpt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = SimpleNamespace(
        id="agent-2",
        name="worker",
        description="实验支线",
        meta={"status": "failed"},
    )
    calls: list[tuple[str, str, str, str, str | None, str | None, str | None]] = []

    async def fake_retry_subagent_execution(
        *,
        user_id: str,
        session_id: str,
        agent_id: str,
        description: str,
        subagent_status: str | None = None,
        prompt_excerpt: str | None = None,
        output_excerpt: str | None = None,
    ) -> dict[str, str]:
        calls.append(
            (
                user_id,
                session_id,
                agent_id,
                description,
                subagent_status,
                prompt_excerpt,
                output_excerpt,
            )
        )
        return {"status": "accepted", "mode": "host_recovery_turn_queued"}

    monkeypatch.setattr(
        sessions_module.agent_service,
        "retry_subagent_execution",
        fake_retry_subagent_execution,
    )
    monkeypatch.setattr(
        sessions_module,
        "_read_subagent_control_excerpt",
        lambda *args, **kwargs: "excerpt-prompt" if args[3] == "prompt.txt" else "excerpt-output",
    )

    result = await sessions_module.retry_subagent(
        user_id="route-test-user",
        session_id="session-2",
        agent_id="agent-2",
        current_user=CURRENT_USER,
        tracking_service=_FakeTrackingService(detail),
    )

    assert result["status"] == "accepted"
    assert calls == [
        (
            "route-test-user",
            "session-2",
            "agent-2",
            "实验支线",
            "failed",
            "excerpt-prompt",
            "excerpt-output",
        )
    ]


@pytest.mark.asyncio
async def test_get_subagent_detail_route_returns_ownership_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = SimpleNamespace(
        id="agent-3",
        name="补丁审查",
        status="running",
        description="补丁审查",
        ownership=SimpleNamespace(
            host_session_id="session-3",
            parent_tool_call_id="task-3",
            agent_id="agent-3",
            subagent_type="reviewer",
        ),
        duration_ms=1200,
        created_at="2026-04-16T12:00:00+08:00",
        updated_at="2026-04-16T12:01:00+08:00",
        meta={},
        events=[],
        context=[],
        output_files=[],
    )
    monkeypatch.setattr(
        sessions_module,
        "_get_subagent_route_context",
        lambda **kwargs: {
            "session_id": kwargs["session_id"],
            "workspace_id": "workspace-1",
            "control_state": None,
            "bound_host_session_id": None,
            "conversation_type": "chat",
        },
    )

    result = await sessions_module.get_subagent_detail(
        user_id="route-test-user",
        session_id="session-3",
        agent_id="agent-3",
        current_user=CURRENT_USER,
        tracking_service=_FakeTrackingService(detail),
    )

    assert result["id"] == "agent-3"
    assert result["agent_id"] == "agent-3"
    assert result["subagent_type"] == "reviewer"
    assert result["host_session_id"] == "session-3"
    assert result["parent_tool_call_id"] == "task-3"
    assert result["workspace_id"] == "workspace-1"
    assert result["node_role"] == "collaboration_node"
    assert result["hosting_controller"] is False
    assert result["ownership"] == {
        "host_session_id": "session-3",
        "parent_tool_call_id": "task-3",
        "agent_id": "agent-3",
        "subagent_type": "reviewer",
    }


@pytest.mark.asyncio
async def test_get_subagent_detail_route_marks_hosting_controller_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    detail = SimpleNamespace(
        id="agent-host-1",
        name="托管控制器",
        status="running",
        description="托管控制器",
        ownership=SimpleNamespace(
            host_session_id="session-hosting-1",
            parent_tool_call_id="task-host-1",
            agent_id="agent-host-1",
            subagent_type="reviewer",
        ),
        duration_ms=2400,
        created_at="2026-04-16T12:00:00+08:00",
        updated_at="2026-04-16T12:01:00+08:00",
        meta={},
        events=[],
        context=[],
        output_files=[],
    )
    control_state = SimpleNamespace(
        hosting_agent_id="agent-host-1",
        hosting_session_id="session-hosting-1",
    )
    monkeypatch.setattr(
        sessions_module,
        "_get_subagent_route_context",
        lambda **kwargs: {
            "session_id": kwargs["session_id"],
            "workspace_id": "workspace-2",
            "control_state": control_state,
            "bound_host_session_id": "session-main-1",
            "conversation_type": "hosting_agent",
        },
    )

    result = await sessions_module.get_subagent_detail(
        user_id="route-test-user",
        session_id="session-hosting-1",
        agent_id="agent-host-1",
        current_user=CURRENT_USER,
        tracking_service=_FakeTrackingService(detail),
    )

    assert result["workspace_id"] == "workspace-2"
    assert result["node_role"] == "hosting_controller"
    assert result["hosting_controller"] is True
    assert result["bound_host_session_id"] == "session-main-1"
    assert result["ownership"]["bound_host_session_id"] == "session-main-1"
