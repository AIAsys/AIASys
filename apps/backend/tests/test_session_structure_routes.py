from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

import app.api.routes.agent as agent_module
import app.api.routes.agent_config as agent_config_route
import app.api.routes.sessions as sessions_module
import app.api.routes.sessions_branches as sessions_branches_module
import app.api.routes.sessions_execution as sessions_execution_module
import app.agents.tools.local_ipython_box as local_ipython_box_module
import app.services.agent as agent_service_module
import app.services.session.config_projection as config_projection_module
from app.models.session import StructuredMessage
from app.models.user import UserInfo
from app.services.agent_config import AgentMode, AgentConfigService
from app.services.history import SessionExecutionJournal
from app.services.session import SessionManager


CURRENT_USER = UserInfo(user_id="session-structure-user", role="user", auth_provider="none")


@pytest.fixture
def isolated_session_manager(tmp_path, monkeypatch: pytest.MonkeyPatch) -> SessionManager:
    manager = SessionManager(tmp_path)
    monkeypatch.setattr(sessions_module, "session_manager", manager)
    monkeypatch.setattr(sessions_branches_module, "session_manager", manager)
    monkeypatch.setattr(sessions_execution_module, "session_manager", manager)
    monkeypatch.setattr(
        sessions_module.agent_service,
        "stop_session",
        AsyncMock(return_value=None),
    )
    return manager


@pytest.mark.asyncio
async def test_get_session_status_includes_execution_journal_summary(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "status-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="状态测试",
        sandbox_mode="local",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('status')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        sandbox_mode="local",
        env_id="python-data-analysis",
        stdout="status\n",
        result_preview_text="status",
    )

    payload = await sessions_branches_module.get_session_status(
        session_id,
        current_user=CURRENT_USER,
    )

    assert payload["has_execution_journal"] is True
    assert payload["execution_record_count"] == 1
    assert payload["recovery_policy"] == "journal_only"
    assert payload["last_execution_status"] == "completed"
    assert payload["agent_config_effect"] == "next_run_only"
    assert payload["can_edit_agent_config_now"] is True
    assert payload["applied_agent_config_version"] is None
    assert payload["pending_agent_config_version"] == payload["current_agent_config_version"]
    assert len(payload["pending_agent_config_version"]) == 16
    assert "current_memory_snapshot_version" in payload
    assert "memory_snapshot_preview" in payload
    assert payload["can_change_recovery_policy"] is False
    assert "只能在空白草稿中修改" in (payload["recovery_policy_lock_reason"] or "")


@pytest.mark.asyncio
async def test_get_session_status_exposes_pending_agent_config_version(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "pending-agent-config-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="待生效 Agent 配置",
        sandbox_mode="local",
    )

    config_service = AgentConfigService(workspace_root=isolated_session_manager.base_dir)
    monkeypatch.setattr(
        config_projection_module,
        "get_agent_config_service",
        lambda: config_service,
    )
    await config_service.save_prompt_override(
        mode=AgentMode.ANALYSIS,
        user_id=user_id,
        content="# 当前任务待生效版本",
        session_id=session_id,
    )

    payload = await sessions_branches_module.get_session_status(
        session_id,
        current_user=CURRENT_USER,
    )

    assert payload["agent_config_effect"] == "next_run_only"
    assert payload["can_edit_agent_config_now"] is True
    assert payload["applied_agent_config_version"] is None
    assert payload["pending_agent_config_version"] == payload["current_agent_config_version"]
    assert len(payload["pending_agent_config_version"]) == 16
    assert payload["config_sync_state"] == "pending"
    assert "agent_config_updated" in payload["rebuild_required_reasons"]


@pytest.mark.asyncio
async def test_update_prompt_rejects_session_scope_edit_while_session_running(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "locked-agent-config-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="运行中 Agent 配置",
        sandbox_mode="local",
    )
    sessions_module.agent_service._active_sessions[f"{user_id}/{session_id}"] = object()

    try:
        with pytest.raises(agent_config_route.HTTPException) as exc:
            await agent_config_route.update_prompt(
                mode=AgentMode.ANALYSIS,
                request=agent_config_route.PromptUpdateRequest(content="# locked"),
                session_id=session_id,
                current_user=CURRENT_USER,
            )
    finally:
        sessions_module.agent_service._active_sessions.pop(
            f"{user_id}/{session_id}",
            None,
        )

    assert exc.value.status_code == 409
    assert "正在执行中" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_get_session_status_marks_local_runtime_missing_when_kernel_reclaimed(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "missing-runtime-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="运行态回收测试",
        sandbox_mode="local",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('runtime')",
        started_at="2026-03-21T00:00:00",
        finished_at="2026-03-21T00:00:01",
        status="completed",
        sandbox_mode="local",
        env_id="python-data-analysis",
        stdout="runtime\n",
        result_preview_text="runtime",
    )

    monkeypatch.setattr(
        local_ipython_box_module.LocalIPythonBox,
        "has_kernel",
        classmethod(lambda cls, session_id=None, user_id="default", env_id=None: False),
    )

    payload = await sessions_branches_module.get_session_status(
        session_id,
        current_user=CURRENT_USER,
    )

    assert payload["execution_record_count"] == 1
    assert payload["last_runtime_state"] == "missing"


@pytest.mark.asyncio
async def test_get_session_status_normalizes_docker_request_to_local_runtime(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "missing-docker-runtime-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="Docker 运行态回收测试",
        sandbox_mode="docker",
        env_id="python-data-analysis",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('docker-runtime')",
        started_at="2026-03-21T00:00:00",
        finished_at="2026-03-21T00:00:01",
        status="completed",
        sandbox_mode="docker",
        env_id="python-data-analysis",
        stdout="docker-runtime\n",
        result_preview_text="docker-runtime",
    )

    payload = await sessions_branches_module.get_session_status(
        session_id,
        current_user=CURRENT_USER,
    )

    assert payload["execution_record_count"] == 1
    assert payload["last_runtime_state"] == "available"


@pytest.mark.asyncio
async def test_get_session_execution_records_returns_latest_first(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "records-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="记录测试",
        sandbox_mode="local",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('one')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        stdout="one\n",
        result_preview_text="one",
    )
    journal.append_record(
        code="print('two')",
        started_at="2026-03-19T00:00:02",
        finished_at="2026-03-19T00:00:03",
        status="completed",
        stdout="two\n",
        result_preview_text="two",
    )

    payload = await sessions_execution_module.get_session_execution_records(
        user_id,
        session_id,
        limit=10,
        current_user=CURRENT_USER,
    )

    assert payload["summary"]["execution_record_count"] == 2
    assert [item["code"] for item in payload["records"]] == [
        "print('two')",
        "print('one')",
    ]
    assert payload["records"][0]["replay_risk"]["level"] == "low"


@pytest.mark.asyncio
async def test_get_session_execution_records_summary_prefers_session_metadata(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "records-summary-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="记录摘要策略测试",
        sandbox_mode="local",
        recovery_policy="journal_only",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('mode')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        stdout="mode\n",
        result_preview_text="mode",
    )

    metadata = isolated_session_manager.get_session(session_id, user_id)
    assert metadata is not None
    metadata.recovery_policy = "manual_replay"
    (session_dir / "metadata.json").write_text(
        json.dumps(metadata.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    payload = await sessions_execution_module.get_session_execution_records(
        user_id,
        session_id,
        limit=10,
        current_user=CURRENT_USER,
    )

    assert payload["summary"]["recovery_policy"] == "manual_replay"
    assert payload["summary"]["execution_record_count"] == 1


@pytest.mark.asyncio
async def test_reset_session_history_clears_messages_and_execution_records(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "reset-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="重置测试",
        sandbox_mode="local",
    )
    isolated_session_manager.add_message(
        session_id=session_id,
        user_id=user_id,
        message=StructuredMessage(role="user", content="legacy"),
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    isolated_session_manager._write_history_snapshot(
        session_dir,
        [{"role": "user", "content": "legacy transport"}],
    )
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('legacy')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        stdout="legacy\n",
        result_preview_text="legacy",
    )

    payload = await sessions_execution_module.reset_session_history(
        user_id,
        session_id,
        current_user=CURRENT_USER,
    )

    assert payload["success"] is True
    assert payload["session"]["message_count"] == 0
    assert payload["session"]["status"] == "draft"
    assert payload["session"]["execution_record_count"] == 0

    history = isolated_session_manager.get_history(session_id, user_id)
    assert history == []
    # context.jsonl 不再被清空（已废弃写入），history.json 应为空
    from app.services.session.constants import (
        ACTIVE_SESSION_STATE_DIR_NAME,
        HISTORY_SNAPSHOT_FILE_NAME,
    )

    snapshot_path = (
        session_dir
        / ".aiasys"
        / "session"
        / ACTIVE_SESSION_STATE_DIR_NAME
        / HISTORY_SNAPSHOT_FILE_NAME
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot.get("messages") == []

    records_path = session_dir / ".aiasys" / "session" / "execution" / "records.jsonl"
    assert not records_path.exists() or records_path.read_text(encoding="utf-8") == ""


@pytest.mark.asyncio
async def test_get_session_history_preserves_archived_context_and_execution_markers(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "clear-conversation-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="清空对话测试",
        sandbox_mode="local",
    )
    isolated_session_manager.add_message(
        session_id=session_id,
        user_id=user_id,
        message=StructuredMessage(role="user", content="legacy"),
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    isolated_session_manager._write_history_snapshot(
        session_dir,
        [{"role": "user", "content": "legacy transport"}],
    )
    legacy_sdk_dir = session_dir / ".aiasys" / "session" / session_id
    legacy_sdk_dir.mkdir(parents=True, exist_ok=True)
    (legacy_sdk_dir / "display_history.jsonl").write_text(
        json.dumps({"role": "user", "content": "legacy ui"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('legacy')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        stdout="legacy\n",
        result_preview_text="legacy",
    )

    history_snapshot = [
        {
            "role": "user",
            "content": "legacy transport",
            "display_content": "legacy ui",
            "timestamp": "2026-03-19T00:00:00",
        },
        {
            "role": "assistant",
            "content": "legacy answer",
            "timestamp": "2026-03-19T00:00:01",
        },
    ]
    isolated_session_manager.archive_cleared_context(
        session_id,
        user_id,
        history_snapshot,
    )
    isolated_session_manager.mark_context_cleared(session_id, user_id)

    payload = await sessions_execution_module.get_session_history(
        user_id,
        session_id,
        current_user=CURRENT_USER,
    )

    history = isolated_session_manager.get_history(session_id, user_id)
    assert history == []
    assert legacy_sdk_dir.exists()
    records_path = session_dir / ".aiasys" / "session" / "execution" / "records.jsonl"
    assert records_path.exists()
    assert "print('legacy')" in records_path.read_text(encoding="utf-8")
    archive_batches = isolated_session_manager.list_cleared_context_archives(
        session_id,
        user_id,
    )
    assert len(archive_batches) == 1
    assert archive_batches[0]["messages"][0]["display_content"] == "legacy ui"
    assert payload["archived_batches"][0]["messages"][0]["display_content"] == "legacy ui"
    assert payload["messages"][2]["content"] == sessions_module.CLEAR_CONTEXT_MARKER_TEXT

    records = isolated_session_manager.get_execution_records(
        session_id,
        user_id,
        limit=10,
    )
    assert len(records) == 1

    execution_payload = await sessions_execution_module.get_session_execution_records(
        user_id,
        session_id,
        limit=10,
        current_user=CURRENT_USER,
    )
    assert execution_payload["maintenance_markers"][0]["type"] == "context_cleared"
    assert execution_payload["maintenance_markers"][0]["label"] == "已清理当前上下文"


@pytest.mark.asyncio
async def test_rewrite_session_from_message_truncates_tail_and_archives(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "rewrite-message-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="编辑重发测试",
        sandbox_mode="local",
    )
    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    legacy_sdk_dir = session_dir / ".aiasys" / "session" / session_id
    legacy_sdk_dir.mkdir(parents=True, exist_ok=True)
    context_messages = [
        {"role": "user", "content": "first prompt", "timestamp": "2026-05-10T01:00:00"},
        {"role": "assistant", "content": "first answer", "timestamp": "2026-05-10T01:00:01"},
        {"role": "user", "content": "bad prompt", "timestamp": "2026-05-10T01:00:02"},
        {"role": "assistant", "content": "bad answer", "timestamp": "2026-05-10T01:00:03"},
    ]
    (legacy_sdk_dir / "display_history.jsonl").write_text(
        "".join(
            json.dumps(entry, ensure_ascii=False) + "\n"
            for entry in [
                {"role": "user", "content": "first prompt", "timestamp": "2026-05-10T01:00:00"},
                {"role": "user", "content": "bad prompt", "timestamp": "2026-05-10T01:00:02"},
            ]
        ),
        encoding="utf-8",
    )
    isolated_session_manager._write_history_snapshot(session_dir, context_messages)
    isolated_session_manager._update_message_count(session_id, user_id, len(context_messages))

    target_message_id = isolated_session_manager.assign_history_message_ids(
        session_id,
        context_messages,
    )[2]["id"]

    payload = await sessions_execution_module.rewrite_session_from_message(
        user_id,
        session_id,
        sessions_execution_module.RewriteMessageRequest(
            message_id=target_message_id,
            content="fixed prompt",
            confirm_drop_tail=True,
        ),
        current_user=CURRENT_USER,
    )

    assert payload["success"] is True
    assert payload["dropped_count"] == 1
    assert payload["messages"][-1]["content"] == "fixed prompt"
    assert payload["messages"][-1]["rewritten_from"] == target_message_id

    persisted_context = isolated_session_manager.get_history(session_id, user_id)
    assert [message["content"] for message in persisted_context] == [
        "first prompt",
        "first answer",
        "fixed prompt",
    ]
    assert not any("bad answer" in str(m) for m in persisted_context)

    archives = list(
        (session_dir / ".aiasys" / "session" / "ui-history-archives").glob(
            "*-message-rewritten.json"
        )
    )
    assert len(archives) == 1
    archive_payload = json.loads(archives[0].read_text(encoding="utf-8"))
    assert archive_payload["reason"] == "message_rewritten"
    assert archive_payload["messages"][0]["content"] == "bad answer"

    markers = isolated_session_manager.list_execution_maintenance_markers(
        session_id,
        user_id,
    )
    assert markers[0]["type"] == "message_rewritten"
    assert markers[0]["label"] == "已编辑并重发对话"

    recovery = SessionExecutionJournal(session_dir, session_id).get_recovery_config()
    assert recovery["last_runtime_state"] == "refresh_required"


@pytest.mark.asyncio
async def test_rewrite_session_from_message_requires_tail_confirmation(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "rewrite-confirm-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="编辑确认测试",
        sandbox_mode="local",
    )
    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    context_messages = [
        {"role": "user", "content": "old prompt"},
        {"role": "assistant", "content": "old answer"},
    ]
    isolated_session_manager._write_history_snapshot(session_dir, context_messages)
    target_message_id = isolated_session_manager.assign_history_message_ids(
        session_id,
        context_messages,
    )[0]["id"]

    with pytest.raises(sessions_module.HTTPException) as exc:
        await sessions_execution_module.rewrite_session_from_message(
            user_id,
            session_id,
            sessions_execution_module.RewriteMessageRequest(
                message_id=target_message_id,
                content="new prompt",
                confirm_drop_tail=False,
            ),
            current_user=CURRENT_USER,
        )

    assert exc.value.status_code == 400
    assert "需要确认" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_rewrite_session_from_message_uses_visible_history_message_ids(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "rewrite-visible-id-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="可见消息 id 编辑测试",
        sandbox_mode="local",
    )
    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    context_messages = [
        {
            "role": "user",
            "content": "<system-reminder>internal runtime note</system-reminder>",
        },
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！"},
    ]
    isolated_session_manager._write_history_snapshot(session_dir, context_messages)
    isolated_session_manager._update_message_count(session_id, user_id, len(context_messages))

    visible_messages = [
        message
        for message in context_messages
        if not (
            message.get("role") == "user"
            and str(message.get("content") or "").startswith("<system-reminder>")
        )
    ]
    target_message_id = isolated_session_manager.assign_history_message_ids(
        session_id,
        visible_messages,
    )[0]["id"]

    payload = await sessions_execution_module.rewrite_session_from_message(
        user_id,
        session_id,
        sessions_execution_module.RewriteMessageRequest(
            message_id=target_message_id,
            content="你好，改写后",
            confirm_drop_tail=True,
        ),
        current_user=CURRENT_USER,
    )

    assert payload["success"] is True
    assert payload["messages"][-1]["content"] == "你好，改写后"
    persisted_context = isolated_session_manager.get_history(session_id, user_id)
    assert persisted_context[0]["content"].startswith("<system-reminder>")
    assert persisted_context[1]["content"] == "你好，改写后"


def test_available_draft_skips_cleared_session_with_archives(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    reusable_session_id = "blank-draft-session"
    cleared_session_id = "cleared-draft-session"

    isolated_session_manager.create_session(
        session_id=reusable_session_id,
        user_id=user_id,
        title="空白草稿",
        sandbox_mode="local",
    )
    isolated_session_manager.create_session(
        session_id=cleared_session_id,
        user_id=user_id,
        title="已清理上下文",
        sandbox_mode="local",
    )

    cleared_session_dir = isolated_session_manager._get_session_dir(
        cleared_session_id,
        user_id,
    )
    journal = SessionExecutionJournal(cleared_session_dir, cleared_session_id)
    journal.append_record(
        code="print('kept evidence')",
        started_at="2026-03-20T00:00:00",
        finished_at="2026-03-20T00:00:01",
        status="completed",
        stdout="kept evidence\n",
        result_preview_text="kept evidence",
    )
    isolated_session_manager.archive_cleared_context(
        cleared_session_id,
        user_id,
        [
            {
                "role": "user",
                "content": "legacy request",
                "timestamp": "2026-03-20T00:00:00",
            }
        ],
    )
    isolated_session_manager.mark_context_cleared(cleared_session_id, user_id)

    payload = sessions_module._find_available_draft_for_user(CURRENT_USER)

    assert payload["available"] is True
    assert payload["session_id"] == reusable_session_id


def test_list_user_sessions_keeps_cleared_session_out_of_draft_filter(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    blank_session_id = "list-blank-session"
    cleared_session_id = "list-cleared-session"

    isolated_session_manager.create_session(
        session_id=blank_session_id,
        user_id=user_id,
        title="空白草稿",
        sandbox_mode="local",
    )
    isolated_session_manager.create_session(
        session_id=cleared_session_id,
        user_id=user_id,
        title="已清理会话",
        sandbox_mode="local",
    )
    isolated_session_manager.archive_cleared_context(
        cleared_session_id,
        user_id,
        [
            {
                "role": "assistant",
                "content": "kept visible history",
                "timestamp": "2026-03-20T00:00:00",
            }
        ],
    )
    isolated_session_manager.mark_context_cleared(cleared_session_id, user_id)

    sessions = isolated_session_manager.list_user_sessions(
        user_id,
        include_drafts=False,
    )

    returned_ids = {item["session_id"] for item in sessions}
    assert cleared_session_id in returned_ids
    assert blank_session_id not in returned_ids


def test_list_user_sessions_ignores_user_state_and_workspace_dirs(
    isolated_session_manager: SessionManager,
    caplog: pytest.LogCaptureFixture,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "visible-session"
    user_dir = isolated_session_manager.base_dir / user_id

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="正常会话",
        sandbox_mode="local",
    )
    (user_dir / ".memory").mkdir(parents=True)
    (user_dir / ".index").mkdir(parents=True)
    (user_dir / "workspace-only" / ".aiasys" / "workspace").mkdir(parents=True)

    caplog.clear()
    sessions = isolated_session_manager.list_user_sessions(
        user_id,
        include_drafts=True,
    )

    assert [item["session_id"] for item in sessions] == [session_id]
    assert "无效的session_id" not in caplog.text


@pytest.mark.asyncio
async def test_mark_draft_for_cleanup_rejects_cleared_session(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "reject-cleared-cleanup-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="已清理上下文",
        sandbox_mode="local",
    )
    isolated_session_manager.archive_cleared_context(
        session_id,
        user_id,
        [
            {
                "role": "user",
                "content": "legacy request",
                "timestamp": "2026-03-20T00:00:00",
            }
        ],
    )
    isolated_session_manager.mark_context_cleared(session_id, user_id)

    payload = await sessions_branches_module.mark_draft_for_cleanup(
        {"sessionId": session_id, "empty": True},
        current_user=CURRENT_USER,
    )

    assert payload == {"ok": False, "reason": "not_blank_draft"}


@pytest.mark.asyncio
async def test_get_execution_flow_prefers_execution_journal_for_local_ipython(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "local-flow-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="本地执行流测试",
        sandbox_mode="local",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('local-flow')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        sandbox_mode="local",
        stdout="local-flow\n",
        result_preview_text="local-flow",
        origin_source="local_ipython_box",
        tool_name="LocalIPythonBox",
    )

    monkeypatch.setattr(
        agent_service_module,
        "get_work_dir",
        lambda _user_id, _session_id: session_dir,
    )

    payload = await agent_module.get_execution_flow(
        user_id,
        session_id,
        current_user=CURRENT_USER,
    )

    assert len(payload["history"]) == 1
    assert payload["history"][0]["code"] == "print('local-flow')"
    assert payload["history"][0]["stdout"] == "local-flow\n"
    assert payload["history"][0]["success"] is True


@pytest.mark.asyncio
async def test_update_session_recovery_policy_updates_session_status(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "recovery-policy-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="恢复策略测试",
        sandbox_mode="local",
    )

    payload = await sessions_execution_module.update_session_recovery_policy(
        user_id,
        session_id,
        sessions_execution_module.UpdateRecoveryPolicyRequest(recovery_policy="manual_replay"),
        current_user=CURRENT_USER,
    )

    assert payload["success"] is True
    assert payload["session"]["recovery_policy"] == "manual_replay"
    assert payload["session"]["can_change_recovery_policy"] is True

    metadata = isolated_session_manager.get_session(session_id, user_id)
    assert metadata is not None
    assert metadata.recovery_policy == "manual_replay"


@pytest.mark.asyncio
async def test_get_session_recovery_policy_returns_effective_value(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "recovery-policy-read-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="恢复策略读取测试",
        sandbox_mode="local",
        recovery_policy="manual_replay",
    )

    payload = await sessions_execution_module.get_session_recovery_policy(
        user_id,
        session_id,
        current_user=CURRENT_USER,
    )

    assert payload["session_id"] == session_id
    assert payload["recovery_policy"] == "manual_replay"
    assert payload["can_change_recovery_policy"] is True
    assert payload["recovery_policy_lock_reason"] is None


@pytest.mark.asyncio
async def test_update_session_recovery_policy_rejects_started_session(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "recovery-policy-locked-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="恢复策略锁定测试",
        sandbox_mode="local",
    )
    isolated_session_manager.add_message(
        session_id=session_id,
        user_id=user_id,
        message=StructuredMessage(role="user", content="hello"),
    )

    with pytest.raises(sessions_module.HTTPException) as exc:
        await sessions_execution_module.update_session_recovery_policy(
            user_id,
            session_id,
            sessions_execution_module.UpdateRecoveryPolicyRequest(recovery_policy="manual_replay"),
            current_user=CURRENT_USER,
        )

    assert exc.value.status_code == 409
    assert "只能在空白草稿中修改" in str(exc.value.detail)

    metadata = isolated_session_manager.get_session(session_id, user_id)
    assert metadata is not None
    assert metadata.recovery_policy == "journal_only"


@pytest.mark.asyncio
async def test_manual_replay_requires_manual_replay_policy(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "manual-replay-reject-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="手动重放拒绝测试",
        sandbox_mode="local",
    )

    with pytest.raises(sessions_module.HTTPException) as exc:
        await sessions_execution_module.manual_replay_session_records(
            user_id,
            session_id,
            sessions_execution_module.ManualReplayRequest(),
            current_user=CURRENT_USER,
        )

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_manual_replay_replays_completed_records_and_returns_status(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "manual-replay-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="手动重放测试",
        sandbox_mode="local",
        env_id="workspace-default",
        recovery_policy="manual_replay",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('one')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        sandbox_mode="local",
        stdout="one\n",
        result_preview_text="one",
    )

    monkeypatch.setattr(
        sessions_execution_module,
        "_manual_replay_records",
        AsyncMock(
            return_value={
                "replayed_sequences": [1],
                "failed_sequence": None,
                "error": None,
                "completed": True,
            }
        ),
    )

    payload = await sessions_execution_module.manual_replay_session_records(
        user_id,
        session_id,
        sessions_execution_module.ManualReplayRequest(),
        current_user=CURRENT_USER,
    )

    assert payload["success"] is True
    assert payload["rebuild_status"] == "completed"
    assert payload["replayed_count"] == 1
    assert payload["replayed_sequences"] == [1]
    assert payload["remaining_sequences"] == []
    assert payload["replay_run_id"].startswith("replay_")
    assert payload["session"]["recovery_policy"] == "manual_replay"
    assert payload["session"]["rebuild_status"] == "completed"

    monkeypatch.setattr(
        local_ipython_box_module.LocalIPythonBox,
        "has_kernel",
        classmethod(lambda cls, session_id=None, user_id="default", env_id=None: True),
    )
    updated_summary = isolated_session_manager.get_execution_summary(session_id, user_id)
    assert updated_summary["execution_record_count"] == 1
    assert updated_summary["last_runtime_state"] == "available"
    assert updated_summary["rebuild_status"] == "completed"

    replay_runs_path = session_dir / ".aiasys" / "session" / "execution" / "replay-runs.jsonl"
    replay_runs = [
        json.loads(line)
        for line in replay_runs_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(replay_runs) == 1
    assert replay_runs[0]["source_sequences"] == [1]
    assert replay_runs[0]["replayed_sequences"] == [1]
    assert replay_runs[0]["remaining_sequences"] == []
    assert replay_runs[0]["rebuild_status"] == "completed"
    assert replay_runs[0]["completed"] is True


@pytest.mark.asyncio
async def test_manual_replay_selected_sequences_must_be_prefix(
    isolated_session_manager: SessionManager,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "manual-replay-prefix-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="手动重放前缀校验",
        sandbox_mode="local",
        recovery_policy="manual_replay",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('one')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        sandbox_mode="local",
        stdout="one\n",
        result_preview_text="one",
    )
    journal.append_record(
        code="print('two')",
        started_at="2026-03-19T00:00:02",
        finished_at="2026-03-19T00:00:03",
        status="completed",
        sandbox_mode="local",
        stdout="two\n",
        result_preview_text="two",
    )

    with pytest.raises(sessions_module.HTTPException) as exc:
        await sessions_execution_module.manual_replay_session_records(
            user_id,
            session_id,
            sessions_execution_module.ManualReplayRequest(selected_sequences=[2]),
            current_user=CURRENT_USER,
        )

    assert exc.value.status_code == 400
    assert "连续前缀" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_manual_replay_returns_partial_failed_status_and_remaining_sequences(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "manual-replay-partial-failed-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="手动重放部分失败测试",
        sandbox_mode="local",
        recovery_policy="manual_replay",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('one')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        sandbox_mode="local",
        stdout="one\n",
        result_preview_text="one",
    )
    journal.append_record(
        code="print('two')",
        started_at="2026-03-19T00:00:02",
        finished_at="2026-03-19T00:00:03",
        status="completed",
        sandbox_mode="local",
        stdout="two\n",
        result_preview_text="two",
    )

    monkeypatch.setattr(
        sessions_execution_module,
        "_manual_replay_records",
        AsyncMock(
            return_value={
                "replayed_sequences": [1],
                "failed_sequence": 2,
                "error": "step 2 failed",
                "completed": False,
            }
        ),
    )

    payload = await sessions_execution_module.manual_replay_session_records(
        user_id,
        session_id,
        sessions_execution_module.ManualReplayRequest(selected_sequences=[1, 2]),
        current_user=CURRENT_USER,
    )

    assert payload["success"] is False
    assert payload["rebuild_status"] == "partial_failed"
    assert payload["replayed_sequences"] == [1]
    assert payload["remaining_sequences"] == [2]
    assert payload["failed_sequence"] == 2
    assert payload["session"]["rebuild_status"] == "partial_failed"
    assert payload["session"]["last_failed_sequence"] == 2


@pytest.mark.asyncio
async def test_manual_replay_helper_disables_execution_record_append(
    isolated_session_manager: SessionManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = CURRENT_USER.user_id
    session_id = "manual-replay-helper-session"

    isolated_session_manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="手动重放 helper 测试",
        sandbox_mode="local",
        recovery_policy="manual_replay",
    )

    session_dir = isolated_session_manager._get_session_dir(session_id, user_id)
    journal = SessionExecutionJournal(session_dir, session_id)
    journal.append_record(
        code="print('one')",
        started_at="2026-03-19T00:00:00",
        finished_at="2026-03-19T00:00:01",
        status="completed",
        sandbox_mode="local",
        stdout="one\n",
        result_preview_text="one",
    )

    record_execution_flags: list[bool] = []

    class FakeLocalIPythonBox:
        def __init__(self):
            self.workspace = None
            self.session_id = None
            self.record_execution = True

        @classmethod
        def shutdown_kernel(
            cls,
            session_id: str | None = None,
            user_id: str = "default",
            env_id: str | None = None,
        ):
            _ = (session_id, user_id, env_id)
            return None

        async def invoke(self, **_kwargs):
            record_execution_flags.append(self.record_execution)
            return type("ReplayResult", (), {"is_error": False, "output": "one\n"})()

    monkeypatch.setattr(local_ipython_box_module, "LocalIPythonBox", FakeLocalIPythonBox)

    metadata = isolated_session_manager.get_session(session_id, user_id)
    assert metadata is not None

    replay_result = await sessions_execution_module._manual_replay_records(
        user_id=user_id,
        session_id=session_id,
        session_dir=session_dir,
        metadata=metadata,
        records=isolated_session_manager.get_execution_records(session_id, user_id, limit=10),
        restart_runtime=True,
    )

    assert replay_result["completed"] is True
    assert record_execution_flags == [False]

    updated_summary = isolated_session_manager.get_execution_summary(session_id, user_id)
    assert updated_summary["execution_record_count"] == 1
