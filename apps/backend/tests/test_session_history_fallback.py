from __future__ import annotations

import json

import pytest

from app.models.session import StructuredMessage
import app.services.agent as agent_service_module
from app.services.agent import agent_service
from app.services.session import SessionManager


@pytest.mark.asyncio
async def test_get_session_history_reads_context_jsonl_only(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_session_history 只读 context.jsonl，不 fallback 到 session manager。"""
    user_id = "history-fallback-user"
    session_id = "history-fallback-session"

    session_manager = SessionManager(tmp_path)
    session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="历史回退测试",
    )
    session_manager.add_message(
        session_id=session_id,
        user_id=user_id,
        message=StructuredMessage(role="user", content="legacy hello"),
    )

    monkeypatch.setattr(agent_service_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(agent_service, "_session_manager", session_manager)

    history = await agent_service.get_session_history(user_id, session_id)

    # 无 context.jsonl 时返回空列表，不 fallback 到 session manager
    assert len(history) == 0


@pytest.mark.asyncio
async def test_get_session_history_backfills_reasoning_content_from_host_wire(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = "history-wire-user"
    session_id = "history-wire-session"

    session_manager = SessionManager(tmp_path)
    session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="历史推理回填测试",
    )

    session_dir = session_manager._get_session_dir(session_id, user_id)
    wire_dir = session_dir / ".aiasys" / "session" / session_id
    wire_dir.mkdir(parents=True, exist_ok=True)

    # context.jsonl 用于 get_session_history 读取
    (wire_dir / "context.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"role": "user", "content": "hello"}),
                json.dumps({"role": "assistant", "content": "最终答案。"}),
            ]
        ),
        encoding="utf-8",
    )

    # wire.jsonl 用于 reasoning_content 回填
    (wire_dir / "wire.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {"type": "turn_begin", "timestamp": 1777309203.0},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "type": "content",
                        "content_type": "think",
                        "think": "思考过程。",
                        "timestamp": 1777309204.0,
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"type": "turn_end", "timestamp": 1777309207.5},
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(agent_service_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(agent_service, "_session_manager", session_manager)

    history = await agent_service.get_session_history(user_id, session_id)

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "最终答案。"
    assert history[1]["reasoning_content"] == "思考过程。"
