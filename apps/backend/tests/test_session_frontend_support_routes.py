from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes import sessions_branches as sessions_branches_route
from app.models.expert import ExpertRoleSummary, SessionExpertPolicyResponse
from app.models.user import UserInfo
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.session import SessionManager

from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    session_manager = SessionManager(tmp_path)
    return WorkspaceRegistryService(tmp_path, session_manager=session_manager)


class _FakeModelSelectionService:
    def get_session_selection(self, *, user_id: str, session_id: str):
        assert user_id == "local_default"
        assert session_id == "branch-support"

        class _Selection:
            def model_dump(self, mode: str = "json"):
                assert mode == "json"
                return {
                    "session_id": session_id,
                    "workspace_id": "task-support",
                    "effective": {"model_id": "model-demo"},
                }

        return _Selection()


def _fake_expert_policy(*, user_id: str, session_id: str) -> SessionExpertPolicyResponse:
    assert user_id == "local_default"
    assert session_id == "branch-support"
    return SessionExpertPolicyResponse(
        session_id=session_id,
        profile_name="analysis-default",
        effective_enabled_role_ids=["researcher"],
        effective_role_tool_ids={"researcher": []},
        available_roles=[
            ExpertRoleSummary(
                role_id="researcher",
                display_name="研究员",
                description="研究问题",
                agent_file="researcher.md",
            )
        ],
    )


@pytest.mark.asyncio
async def test_session_settings_artifacts_and_references_support_frontend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(sessions_branches_route, "session_manager", service.session_manager)
    monkeypatch.setattr(sessions_branches_route, "get_workspace_registry_service", lambda: service)
    monkeypatch.setattr(
        sessions_branches_route,
        "get_model_selection_service",
        lambda: _FakeModelSelectionService(),
    )
    monkeypatch.setattr(sessions_branches_route, "get_session_expert_policy", _fake_expert_policy)

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="task-support",
        title="前端支撑任务",
        initial_conversation_id="branch-support",
        initial_conversation_title="当前会话",
    )
    conversation = detail.current_conversation
    assert conversation is not None

    workspace_dir = tmp_path / "local_default" / "task-support"
    (workspace_dir / "root-report.md").write_text("root", encoding="utf-8")


    session_dir = tmp_path / "local_default" / "branch-support"
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "branch-private.ipynb").write_text("{}", encoding="utf-8")
    journal = SessionExecutionJournal(session_dir, "branch-support")
    journal.append_record(
        code="print('support')",
        started_at="2026-04-24T11:00:00",
        finished_at="2026-04-24T11:00:01",
        status="completed",
        sandbox_mode="local",
        env_id="python-data-analysis",
        stdout="support",
        stderr="",
        result_preview_text="support",
        artifact_refs=["workspace/chart.png"],
    )

    settings = await sessions_branches_route.get_session_settings_summary(
        "local_default",
        "branch-support",
        current_user=_build_user(),
    )
    assert settings.workspace_id == "task-support"
    assert settings.agent_config["effect"] == "next_run_only"
    assert settings.model_selection["effective"]["model_id"] == "model-demo"
    assert settings.expert_policy["effective_enabled_role_ids"] == ["researcher"]
    assert "enabled_builtin_packs" not in settings.capabilities["summary"]

    reference_search = await sessions_branches_route.search_session_references(
        "local_default",
        "branch-support",
        query="root-report.md",
        current_user=_build_user(),
    )
    assert reference_search.workspace_id == "task-support"
    assert [item.reference_id for item in reference_search.items] == [
        "file:root-report.md"
    ]

    expert_search = await sessions_branches_route.search_session_references(
        "local_default",
        "branch-support",
        query="研究员",
        current_user=_build_user(),
    )
    assert [item.reference_id for item in expert_search.items] == ["expert:researcher"]

    resolved = await sessions_branches_route.resolve_session_references(
        "local_default",
        "branch-support",
        sessions_branches_route.SessionReferenceResolveRequest(
            reference_ids=["file:root-report.md", "missing:item"],
        ),
        current_user=_build_user(),
    )
    assert [item.reference_id for item in resolved.resolved] == [
        "file:root-report.md"
    ]
    assert resolved.unresolved_reference_ids == ["missing:item"]
    assert resolved.task_resource_context["direct_reference_object_count"] >= 1
