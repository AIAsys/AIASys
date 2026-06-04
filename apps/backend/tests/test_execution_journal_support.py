from __future__ import annotations

from pathlib import Path

from app.services.session.core import SessionManager
from app.services.runtime.execution_support import (
    ExecutionJournalContext,
    append_execution_record_if_possible,
)


def test_append_execution_record_persists_agent_config_snapshot(tmp_path: Path) -> None:
    session_dir = tmp_path / "workspace"
    session_dir.mkdir(parents=True, exist_ok=True)

    written = append_execution_record_if_possible(
        enabled=True,
        context=ExecutionJournalContext(
            workspace=session_dir,
            session_id="session-1",
            sandbox_mode="local",
            env_id=None,
            origin_source="local_ipython_box",
            tool_name="LocalIPythonBox",
            agent_config_snapshot={
                "version": "cfg-v1",
                "model": "kimi-k2",
            },
        ),
        code="print(123)",
        started_at="2026-04-05T00:00:00",
        status="completed",
        stdout="123\n",
        result_preview_text="123\n",
    )

    assert written is True

    records_path = session_dir / ".aiasys" / "session" / "execution" / "records.jsonl"
    assert records_path.exists()

    payload = records_path.read_text(encoding="utf-8").strip()
    assert '"agent_config_snapshot": {"version": "cfg-v1", "model": "kimi-k2"}' in payload


def test_create_session_accepts_none_title(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)

    metadata = manager.create_session(
        session_id="session-2",
        user_id="local_default",
        title=None,
    )

    assert metadata.title == "新会话"
