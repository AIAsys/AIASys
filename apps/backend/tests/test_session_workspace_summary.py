from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes import sessions_branches as sessions_route
from app.models.user import UserInfo
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    session_manager = SessionManager(tmp_path)
    return WorkspaceRegistryService(tmp_path, session_manager=session_manager)


def _patch_session_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    service: WorkspaceRegistryService,
) -> None:
    monkeypatch.setattr(sessions_route, "session_manager", service.session_manager)
    monkeypatch.setattr(sessions_route, "get_workspace_registry_service", lambda: service)


@pytest.mark.asyncio
async def test_session_workspace_summary_returns_real_workspace_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _patch_session_dependencies(monkeypatch, service)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-summary",
        title="摘要任务",
        initial_conversation_id="branch-summary",
        initial_conversation_title="摘要会话",
    )

    summary = await sessions_route.get_session_workspace_summary(
        "branch-summary",
        current_user=_build_user(),
    )

    assert summary["workspace_id"] == "task-summary"
    assert summary["workspace_id_source"] == "workspace_registry"
    assert summary["workspace_title"] == "摘要任务"
    assert summary["workspace_current_conversation_id"] == "branch-summary"
    assert summary["session_id"] == "branch-summary"


@pytest.mark.asyncio
async def test_session_workspace_summary_marks_unbound_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _patch_session_dependencies(monkeypatch, service)
    service.session_manager.create_session(
        session_id="loose-session",
        user_id="local_default",
        title="未绑定会话",
        env_id="python-data-analysis",
        sandbox_mode="local",
    )

    summary = await sessions_route.get_session_workspace_summary(
        "loose-session",
        current_user=_build_user(),
    )

    assert summary["workspace_id"] is None
    assert summary["workspace_id_source"] == "unbound_session"
    assert summary["workspace_title"] is None
    assert summary["session_id"] == "loose-session"
