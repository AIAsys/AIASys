from __future__ import annotations

import pytest

from app.api.routes import sessions_execution as sessions_execution_module


class _FakeUser:
    def can_access_user_data(self, user_id: str) -> bool:
        return True


class _FakeAgentService:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self._events = events

    async def get_session_execution_events(
        self,
        user_id: str,
        session_id: str,
    ) -> list[dict[str, object]]:
        return list(self._events)


@pytest.mark.asyncio
async def test_get_host_events_filters_subagent_internal_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_events = [
        {"type": "turn_begin"},
        {"type": "step_begin", "step_n": 1},
        {"type": "tool_call", "tool_call_id": "task-1", "tool_name": "Task"},
        {
            "type": "subagent_content",
            "task_tool_call_id": "task-1",
            "text": "worker says hi",
        },
        {
            "type": "subagent_tool_call",
            "task_tool_call_id": "task-1",
            "tool_name": "ReadFile",
        },
        {
            "type": "worker.lifecycle.changed",
            "scope": "subagent",
            "status": "finished",
            "reason": "task_tool_result_completed",
            "task_tool_call_id": "task-1",
        },
        {"type": "turn_end"},
    ]

    import app.services.agent as agent_service_module

    monkeypatch.setattr(
        agent_service_module,
        "agent_service",
        _FakeAgentService(fake_events),
    )
    monkeypatch.setattr(
        sessions_execution_module,
        "_get_session_owner_from_metadata",
        lambda *args, **kwargs: "local_default",
    )

    result = await sessions_execution_module.get_host_events(
        "local_default",
        "session-host-events-1",
        current_user=_FakeUser(),
    )

    assert [event["type"] for event in result["events"]] == [
        "turn_begin",
        "step_begin",
        "tool_call",
        "turn_end",
    ]
    assert result["total"] == 4
