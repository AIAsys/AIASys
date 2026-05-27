from __future__ import annotations

from pathlib import Path

from app.services.session import SessionManager
from app.services.session.config_projection import build_workspace_capability_summary


def test_session_manager_persists_task_profile_and_projection(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    user_id = "local_default"
    session_id = "task-profile-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="任务配置测试",
        sandbox_mode="local",
    )

    updated = manager.update_task_profile(
        session_id=session_id,
        user_id=user_id,
        execution_policy={
            "mode": "auto_explore",
            "checkpoint_policy": "stage_boundary",
            "max_parallel_sessions": 2,
            "max_continuations": 5,
            "max_runtime_minutes": 45,
        },
    )

    assert updated is not None
    assert updated.execution_policy.mode.value == "auto_explore"
    assert updated.execution_policy.auto_continue is True

    metadata = manager.get_session(session_id, user_id)
    assert metadata is not None
    assert metadata.execution_policy.mode.value == "auto_explore"
    assert metadata.execution_policy.auto_continue is True

    session_dir = tmp_path / user_id / session_id
    capability_summary = build_workspace_capability_summary(session_dir)
    assert "enabled_builtin_packs" not in capability_summary
    assert capability_summary["execution_policy"]["mode"] == "auto_explore"
    assert capability_summary["execution_policy"]["auto_continue"] is True


def test_session_manager_task_profile_update_keeps_existing_mode(tmp_path: Path) -> None:
    manager = SessionManager(tmp_path)
    user_id = "local_default"
    session_id = "task-profile-reset-session"

    manager.create_session(
        session_id=session_id,
        user_id=user_id,
        title="任务配置重置测试",
        sandbox_mode="local",
    )
    manager.update_task_profile(
        session_id=session_id,
        user_id=user_id,
        execution_policy={"mode": "auto_explore"},
    )

    updated = manager.update_task_profile(
        session_id=session_id,
        user_id=user_id,
        execution_policy={"mode": "chat_assist"},
    )

    assert updated is not None
    assert updated.execution_policy.mode.value == "chat_assist"
    assert updated.execution_policy.auto_continue is False
