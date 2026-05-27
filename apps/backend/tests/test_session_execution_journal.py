from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.agents.tools import local_ipython_box as local_ipython_box_module
from app.agents.tools.local_ipython_box import LocalIPythonBox, LocalIPythonBoxParams
from app.models.runtime_environment import WorkspaceRuntimeEnv
from app.services.history import SessionExecutionJournal
from app.services.history import (
    current_env_id,
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)
from app.services.session import SessionManager


def test_create_session_initializes_execution_layout_and_preserves_workspace_files(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "journal-session"
    session_dir = tmp_path / user_id / session_id
    active_state_dir = session_dir / ".aiasys" / "session" / "_active"

    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "file_snapshots.json").write_text(
        json.dumps([{"files": ["a.csv"]}], ensure_ascii=False),
        encoding="utf-8",
    )
    (session_dir / "analysis.md").write_text("# keep me\n", encoding="utf-8")

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Journal Init",
    )

    assert (session_dir / "analysis.md").exists()
    active_history = json.loads(
        (active_state_dir / "history.json").read_text(encoding="utf-8")
    )
    assert active_history["_schema_version"] == 1
    assert active_history["messages"] == []
    assert not (session_dir / "file_snapshots.json").exists()

    execution_dir = session_dir / ".aiasys" / "session" / "execution"
    assert execution_dir.exists()
    assert (execution_dir / "records-index.json").exists()
    assert (execution_dir / "recovery.json").exists()

    recovery = json.loads((execution_dir / "recovery.json").read_text(encoding="utf-8"))
    assert recovery["recovery_policy"] == "journal_only"


def test_append_record_preserves_explicit_recovery_policy(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "journal-policy-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Journal Policy",
        sandbox_mode="local",
        recovery_policy="manual_replay",
    )

    session_dir = tmp_path / user_id / session_id
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('policy')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        stdout="policy\n",
        result_preview_text="policy",
    )

    recovery = json.loads(
        (session_dir / ".aiasys" / "session" / "execution" / "recovery.json").read_text(
            encoding="utf-8"
        )
    )
    assert recovery["recovery_policy"] == "manual_replay"
    assert recovery["idempotency_policy"] == "assume_non_idempotent"
    assert recovery["requires_confirmation_for_replay"] is True
    assert recovery["last_runtime_state"] == "available"


def test_append_record_persists_agent_config_snapshot_to_record_and_summary(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "journal-user" / "journal-agent-config-session"
    journal = SessionExecutionJournal(session_dir, "journal-agent-config-session")

    record = journal.append_record(
        code="print('snapshot')",
        started_at="2026-04-01T10:00:00",
        finished_at="2026-04-01T10:00:01",
        status="completed",
        stdout="snapshot\n",
        result_preview_text="snapshot",
        agent_config_snapshot={
            "effect": "next_run_only",
            "version": "session:analysis:2026-04-01T10:00:00:abc123def456",
            "mode": "analysis",
            "prompt_source": "session_override",
            "tool_source": "user_override",
            "effective_scope": "session",
            "session_id": "journal-agent-config-session",
            "effective_updated_at": "2026-04-01T10:00:00",
            "enabled_tools_count": 6,
            "disabled_tools_count": 2,
        },
    )

    assert record.agent_config_snapshot is not None
    assert record.agent_config_snapshot["version"].endswith("abc123def456")

    persisted_record = journal.list_records(limit=1)[0]
    assert persisted_record.agent_config_snapshot is not None
    assert (
        persisted_record.agent_config_snapshot["prompt_source"]
        == "session_override"
    )

    summary = journal.get_summary()
    assert summary["last_execution_record_id"] == record.record_id
    assert summary["execution_record_count"] == 1


def test_append_replay_run_does_not_change_execution_record_count(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "journal-replay-audit-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Replay Audit",
        sandbox_mode="local",
        recovery_policy="manual_replay",
    )

    session_dir = tmp_path / user_id / session_id
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('base')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        stdout="base\n",
        result_preview_text="base",
    )

    replay_run = journal.append_replay_run(
        started_at="2026-03-19T00:00:10",
        finished_at="2026-03-19T00:00:12",
        source_sequences=[1],
        recovery_policy="manual_replay",
        sandbox_mode="local",
        env_id="python-data-analysis",
        restart_runtime=True,
        include_failed=False,
        risk_acknowledged=True,
        upto_sequence=None,
        selected_sequences=[1],
        replayed_sequences=[1],
        remaining_sequences=[],
        rebuild_status="completed",
        completed=True,
        failed_sequence=None,
        error=None,
    )

    summary = journal.get_summary()
    assert summary["execution_record_count"] == 1
    assert replay_run["replay_run_id"].startswith("replay_")

    replay_lines = (
        session_dir / ".aiasys" / "session" / "execution" / "replay-runs.jsonl"
    ).read_text(encoding="utf-8").splitlines()
    assert len(replay_lines) == 1
    payload = json.loads(replay_lines[0])
    assert payload["source_sequences"] == [1]
    assert payload["selected_sequences"] == [1]
    assert payload["risk_acknowledged"] is True
    assert payload["replayed_sequences"] == [1]
    assert payload["remaining_sequences"] == []
    assert payload["rebuild_status"] == "completed"
    assert payload["completed"] is True


def test_append_record_redacts_database_secrets_from_persisted_output(
    tmp_path: Path,
) -> None:
    session_dir = tmp_path / "journal-user" / "journal-redact-session"
    journal = SessionExecutionJournal(session_dir, "journal-redact-session")

    record = journal.append_record(
        code="print('db')",
        started_at="2026-03-20T16:00:00",
        finished_at="2026-03-20T16:00:01",
        status="completed",
        stdout="postgresql://postgres:secret-pass@localhost:5434/user_demo?connect_timeout=3",
        stderr="password: secret-pass",
        error='{"password":"secret-pass"}',
        result_preview_text="postgresql://postgres:secret-pass@localhost:5434/user_demo",
    )

    stdout_path = session_dir / (record.stdout_ref or "")
    stderr_path = session_dir / (record.stderr_ref or "")

    stdout_text = stdout_path.read_text(encoding="utf-8")
    stderr_text = stderr_path.read_text(encoding="utf-8")

    assert "secret-pass" not in stdout_text
    assert "secret-pass" not in stderr_text
    assert "[REDACTED_SECRET]" in stdout_text
    assert "[REDACTED_SECRET]" in stderr_text
    assert record.error is not None
    assert "[REDACTED_SECRET]" in record.error
    assert "[REDACTED_SECRET]" in record.result_preview.text


@pytest.mark.asyncio
async def test_local_ipythonbox_appends_execution_record_on_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "journal-session"
    env_id = "workspace-default"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Journal Test",
        sandbox_mode="local",
    )

    workspace_path = tmp_path / user_id / session_id
    executed: dict[str, str] = {}

    class FakeClient:
        def __init__(self) -> None:
            self._messages = iter(())

        def execute(self, code: str) -> str:
            executed["code"] = code
            msg_id = "msg-1"
            self._messages = iter(
                [
                    {
                        "msg_type": "stream",
                        "content": {"text": "hello\n"},
                        "parent_header": {"msg_id": msg_id},
                    },
                    {
                        "msg_type": "status",
                        "content": {"execution_state": "idle"},
                        "parent_header": {"msg_id": msg_id},
                    },
                ]
            )
            return msg_id

        def get_iopub_msg(self, timeout: int):
            return next(self._messages)

    def fake_get_or_create_kernel(
        cls,
        session_id: str,
        notebook_path: str | None = None,
        user_id: str = "default",
        cwd: str | None = None,
        kernel_name: str = "python3",
    ):
        _ = (notebook_path, kernel_name)
        executed["cwd"] = cwd or ""
        return object(), FakeClient()

    from app.services.runtime.runtime_execution import RuntimeExecutionPlan

    monkeypatch.setattr(local_ipython_box_module, "JUPYTER_AVAILABLE", True)
    monkeypatch.setattr(
        LocalIPythonBox,
        "_get_or_create_kernel",
        classmethod(fake_get_or_create_kernel),
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_init_kernel_env",
        classmethod(lambda cls, client, helper_env=None: None),
    )
    monkeypatch.setattr(
        local_ipython_box_module,
        "resolve_runtime_execution_plan",
        lambda **kwargs: RuntimeExecutionPlan(
            sandbox_mode="local",
            env_id="workspace-default",
            display_name="Workspace UV",
            workspace=workspace_path,
            env=WorkspaceRuntimeEnv(
                env_id="workspace-default",
                kind="uv",
                display_name="Workspace UV",
                material_path=str(workspace_path / "env"),
            ),
        ),
    )

    workspace_token = current_workspace.set(workspace_path)
    session_root_token = current_session_root.set(workspace_path)
    session_token = current_session_id.set(session_id)
    user_token = current_user_id.set(user_id)
    env_token = current_env_id.set(env_id)
    try:
        box = LocalIPythonBox()
        result = await box.invoke(
            **LocalIPythonBoxParams(code="print('hello')").model_dump()
        )
    finally:
        current_env_id.reset(env_token)
        current_user_id.reset(user_token)
        current_session_id.reset(session_token)
        current_session_root.reset(session_root_token)
        current_workspace.reset(workspace_token)

    assert result.is_error is False
    assert result.output == "hello\n"
    assert executed["cwd"] == str(workspace_path)
    assert executed["code"] == "print('hello')"

    records_path = workspace_path / ".aiasys" / "session" / "execution" / "records.jsonl"
    entries = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(entries) == 1

    record = entries[0]
    assert record["status"] == "completed"
    assert record["session_id"] == session_id
    assert record["runtime"]["sandbox_mode"] == "local"
    assert record["runtime"]["env_id"] == "workspace-default"
    assert record["code"] == "print('hello')"
    assert record["result_preview"]["text"] == "hello"
    assert record["artifact_refs"] == []

    stdout_ref = record["stdout_ref"]
    assert stdout_ref is not None
    stdout_path = workspace_path / stdout_ref
    assert stdout_path.read_text(encoding="utf-8") == "hello\n"


def test_backfills_execution_records_from_sdk_context_when_journal_is_empty(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "journal-backfill-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Journal Backfill",
        sandbox_mode="local",
    )

    session_dir = tmp_path / user_id / session_id
    legacy_sdk_dir = session_dir / ".aiasys" / "session" / session_id
    legacy_sdk_dir.mkdir(parents=True, exist_ok=True)
    (legacy_sdk_dir / "context.jsonl").write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": "call-local-1",
                                "type": "function",
                                "function": {
                                    "name": "LocalIPythonBox",
                                    "arguments": json.dumps(
                                        {"code": "value = 98\nvalue"},
                                        ensure_ascii=False,
                                    ),
                                },
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "role": "tool",
                        "content": "98",
                        "tool_call_id": "call-local-1",
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    summary = manager.get_execution_summary(session_id, user_id)
    assert summary["execution_record_count"] == 1
    assert summary["last_runtime_state"] == "missing"

    records = manager.get_execution_records(session_id, user_id, limit=10)
    assert len(records) == 1
    assert records[0]["origin"]["source"] == "sdk_context_backfill"
    assert records[0]["origin"]["tool_name"] == "LocalIPythonBox"
    assert records[0]["code"] == "value = 98\nvalue"

    stdout_ref = records[0]["stdout_ref"]
    assert stdout_ref is not None
    assert (session_dir / stdout_ref).read_text(encoding="utf-8") == "98"


def test_local_ipythonbox_resolves_execution_journal_from_contextvars(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "local-context-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Local Context",
        sandbox_mode="local",
    )

    workspace_path = tmp_path / user_id / session_id
    box = LocalIPythonBox()

    workspace_token = current_workspace.set(workspace_path)
    session_root_token = current_session_root.set(workspace_path)
    session_token = current_session_id.set(session_id)
    user_token = current_user_id.set(user_id)
    try:
        journal = box._resolve_execution_journal()
        assert journal is not None
        assert journal.session_dir == workspace_path
        assert journal.session_id == session_id
        assert box._resolve_user_id() == user_id
        assert box._resolve_session_id() == session_id
    finally:
        current_user_id.reset(user_token)
        current_session_id.reset(session_token)
        current_session_root.reset(session_root_token)
        current_workspace.reset(workspace_token)


@pytest.mark.asyncio
async def test_local_ipythonbox_rewrites_workspace_literals_for_local_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "local-workspace-path-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Local Workspace Path",
        sandbox_mode="local",
    )

    workspace_path = tmp_path / user_id / session_id
    executed: dict[str, str] = {}

    class FakeClient:
        def __init__(self) -> None:
            self._messages = iter(())

        def execute(self, code: str) -> str:
            executed["code"] = code
            msg_id = "msg-1"
            self._messages = iter(
                [
                    {
                        "msg_type": "stream",
                        "content": {
                            "text": f"{workspace_path}/sales_preview.csv\n"
                        },
                        "parent_header": {"msg_id": msg_id},
                    },
                    {
                        "msg_type": "status",
                        "content": {"execution_state": "idle"},
                        "parent_header": {"msg_id": msg_id},
                    },
                ]
            )
            return msg_id

        def get_iopub_msg(self, timeout: int):
            return next(self._messages)

    def fake_get_or_create_kernel(
        cls,
        session_id: str,
        notebook_path: str | None = None,
        user_id: str = "default",
        cwd: str | None = None,
        kernel_name: str = "python3",
    ):
        _ = (notebook_path, kernel_name)
        executed["cwd"] = cwd or ""
        return object(), FakeClient()

    from app.services.runtime.runtime_execution import RuntimeExecutionPlan

    monkeypatch.setattr(local_ipython_box_module, "JUPYTER_AVAILABLE", True)
    monkeypatch.setattr(
        LocalIPythonBox,
        "_get_or_create_kernel",
        classmethod(fake_get_or_create_kernel),
    )
    monkeypatch.setattr(
        LocalIPythonBox,
        "_init_kernel_env",
        classmethod(lambda cls, client, helper_env=None: None),
    )
    monkeypatch.setattr(
        local_ipython_box_module,
        "resolve_runtime_execution_plan",
        lambda **kwargs: RuntimeExecutionPlan(
            sandbox_mode="local",
            env_id="workspace-default",
            display_name="Workspace UV",
            workspace=workspace_path,
            env=WorkspaceRuntimeEnv(
                env_id="workspace-default",
                kind="uv",
                display_name="Workspace UV",
                material_path=str(workspace_path / "env"),
            ),
        ),
    )

    box = LocalIPythonBox()
    workspace_token = current_workspace.set(workspace_path)
    session_token = current_session_id.set(session_id)
    user_token = current_user_id.set(user_id)
    try:
        result = await box.invoke(
            **local_ipython_box_module.LocalIPythonBoxParams(
                code=(
                    "from pathlib import Path\n"
                    "Path('/workspace').mkdir(parents=True, exist_ok=True)\n"
                    "print('/workspace/sales_preview.csv')\n"
                ),
                timeout=5,
            ).model_dump()
        )
    finally:
        current_user_id.reset(user_token)
        current_session_id.reset(session_token)
        current_workspace.reset(workspace_token)

    assert executed["cwd"] == str(workspace_path)
    assert str(workspace_path) in executed["code"]
    assert "/workspace/sales_preview.csv" not in executed["code"]
    assert getattr(result, "output", "") == "/workspace/sales_preview.csv\n"


def test_local_ipythonbox_resolves_execution_journal_from_session_root_fallback(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    user_id = "journal-user"
    session_id = "docker-workspace-fallback-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Session Root Fallback",
        sandbox_mode="local",
    )

    workspace_path = tmp_path / user_id / session_id
    box = LocalIPythonBox()
    box.session_id = session_id

    session_root_token = current_session_root.set(workspace_path)
    try:
        journal = box._resolve_execution_journal()
        assert journal is not None
        assert journal.session_dir == workspace_path
        assert journal.session_id == session_id
    finally:
        current_session_root.reset(session_root_token)
