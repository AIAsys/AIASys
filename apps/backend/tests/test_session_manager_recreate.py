from __future__ import annotations

from pathlib import Path

from app.models.task_profile import ExecutionPolicyMode, TaskExecutionPolicy
from app.services.session import SessionManager


def test_create_session_preserves_existing_task_profile_on_recreate(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    manager.create_session(
        session_id="session-auto-explore",
        user_id="user-auto-explore",
        execution_policy=TaskExecutionPolicy(mode=ExecutionPolicyMode.AUTO_EXPLORE),
        source="automation",
        automation_continuation_id="cont-auto-001",
        automation_continuation_target_kind="refresh_roadmap",
    )

    manager.create_session(
        session_id="session-auto-explore",
        user_id="user-auto-explore",
        title="runtime rebuild",
    )

    metadata = manager.get_session("session-auto-explore", "user-auto-explore")
    assert metadata is not None
    assert metadata.execution_policy.mode == ExecutionPolicyMode.AUTO_EXPLORE
    assert metadata.execution_policy.auto_continue is True
    assert metadata.source == "automation"
    assert metadata.automation_continuation_id == "cont-auto-001"
    assert metadata.automation_continuation_target_kind == "refresh_roadmap"


def test_create_session_preserves_existing_preferred_model_id_on_recreate(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    manager.create_session(
        session_id="session-model-override",
        user_id="user-model-override",
        preferred_model_id="model-session",
    )

    manager.create_session(
        session_id="session-model-override",
        user_id="user-model-override",
        title="runtime rebuild",
    )

    metadata = manager.get_session("session-model-override", "user-model-override")
    assert metadata is not None
    assert metadata.preferred_model_id == "model-session"


def test_create_session_preserves_existing_enabled_expert_role_ids_on_recreate(
    tmp_path: Path,
) -> None:
    manager = SessionManager(tmp_path)
    manager.create_session(
        session_id="session-expert-policy",
        user_id="user-expert-policy",
        enabled_expert_role_ids=["reviewer", "coder"],
    )

    manager.create_session(
        session_id="session-expert-policy",
        user_id="user-expert-policy",
        title="runtime rebuild",
    )

    metadata = manager.get_session("session-expert-policy", "user-expert-policy")
    assert metadata is not None
    assert metadata.enabled_expert_role_ids == ["reviewer", "coder"]
