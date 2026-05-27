from __future__ import annotations

import asyncio

import pytest

from app.services.agent import agent_service


@pytest.mark.asyncio
async def test_stop_subagent_execution_cancels_host_session_for_foreground_subagent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_key = "user-1/session-1"
    original_active_sessions = dict(agent_service._active_sessions)
    stop_calls: list[tuple[str, str]] = []

    async def fake_stop_session(user_id: str, session_id: str) -> None:
        stop_calls.append((user_id, session_id))

    monkeypatch.setattr(agent_service, "stop_session", fake_stop_session)
    agent_service._active_sessions.clear()
    agent_service._active_sessions[session_key] = object()

    try:
        result = await agent_service.stop_subagent_execution(
            "user-1",
            "session-1",
            "agent-1",
            subagent_status="running_foreground",
        )
    finally:
        agent_service._active_sessions.clear()
        agent_service._active_sessions.update(original_active_sessions)

    assert result["status"] == "accepted"
    assert result["mode"] == "host_session_cancelled"
    assert stop_calls == [("user-1", "session-1")]


@pytest.mark.asyncio
async def test_retry_subagent_execution_queues_host_recovery_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_active_sessions = dict(agent_service._active_sessions)
    executed_prompts: list[tuple[str, str, str]] = []

    async def fake_execute(
        *,
        prompt: str,
        user_id: str,
        session_id: str,
        model: str | None = None,
        model_id: str | None = None,
        sandbox_mode: str | None = None,
        mode: str | None = None,
        attachments: list[str] | None = None,
    ) -> str:
        _ = (model, model_id, sandbox_mode, mode, attachments)
        executed_prompts.append((user_id, session_id, prompt))
        return "ok"

    monkeypatch.setattr(agent_service, "execute", fake_execute)
    agent_service._active_sessions.clear()

    try:
        result = await agent_service.retry_subagent_execution(
            "user-2",
            "session-2",
            "agent-2",
            description="读取论文并整理实验结论",
            subagent_status="failed",
            prompt_excerpt="请先核对 baseline，再补充对照实验。",
            output_excerpt="上次执行在对照实验阶段失败，未生成最终结论。",
        )
        await asyncio.sleep(0)
    finally:
        agent_service._active_sessions.clear()
        agent_service._active_sessions.update(original_active_sessions)

    assert result["status"] == "accepted"
    assert result["mode"] == "host_recovery_turn_queued"
    assert executed_prompts
    _, _, prompt = executed_prompts[0]
    assert "主控负责兜底" in prompt
    assert "读取论文并整理实验结论" in prompt
    assert "请先核对 baseline" in prompt
    assert "未生成最终结论" in prompt


@pytest.mark.asyncio
async def test_retry_subagent_execution_rejects_non_terminal_status() -> None:
    with pytest.raises(RuntimeError, match="只有失败、取消或已杀掉的协作节点才能重试"):
        await agent_service.retry_subagent_execution(
            "user-3",
            "session-3",
            "agent-3",
            description="still running",
            subagent_status="running",
        )
