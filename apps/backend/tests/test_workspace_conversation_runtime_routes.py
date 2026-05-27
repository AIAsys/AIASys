from __future__ import annotations

from pathlib import Path

import pytest

from app.api.routes import workspaces_runtime as workspace_route
from app.agents.tools.local_ipython_box import LocalIPythonBox
from app.models.user import UserInfo
from app.services.runtime import session_runtime_state as runtime_state_module
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_workspace_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


@pytest.mark.asyncio
async def test_workspace_runtime_list_reports_branch_status_and_controls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        "app.services.runtime_environment.get_runtime_environment_service",
        lambda: RuntimeEnvironmentService(tmp_path, service),
    )

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-runtime-list",
        title="任务运行态列表",
        initial_conversation_id="branch-alpha",
        initial_conversation_title="Alpha",
    )
    service.create_conversation(
        user_id="local_default",
        workspace_id=workspace.workspace_id,
        conversation_id="branch-beta",
        title="Beta",
    )

    active_sessions = {"branch-alpha"}
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_local_kernel_active",
        lambda session_id, user_id: session_id in active_sessions,
    )
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_workspace_runtime_env",
        lambda **kwargs: ("task-runtime-list", {
            "kind": "uv",
            "status": "ready",
            "display_name": "Workspace UV",
        }),
    )
    import app.api.routes.workspaces_conversation_utils as conversation_utils_module

    monkeypatch.setattr(
        conversation_utils_module,
        "_is_runtime_busy",
        lambda user_id, session_id: session_id == "branch-beta",
    )

    response = await workspace_route.list_workspace_conversation_runtimes(
        "task-runtime-list",
        current_user=_build_user(),
    )

    assert response.total == 2
    assert response.current_conversation_id == "branch-beta"

    by_session_id = {
        item.session_id: item for item in response.conversation_runtimes
    }
    assert by_session_id["branch-alpha"].runtime_summary["status"] == "ready"
    assert by_session_id["branch-alpha"].can_stop_runtime is True
    assert by_session_id["branch-alpha"].can_start_runtime is False
    assert by_session_id["branch-alpha"].is_current is False

    assert by_session_id["branch-beta"].runtime_summary["status"] == "ready"
    assert by_session_id["branch-beta"].can_start_runtime is False
    assert by_session_id["branch-beta"].can_stop_runtime is False
    assert (
        by_session_id["branch-beta"].runtime_control_reason
        == "当前会话正在执行，暂时不能切换运行态。"
    )
    assert by_session_id["branch-beta"].is_current is True


@pytest.mark.asyncio
async def test_workspace_runtime_start_warms_branch_kernel_and_marks_available(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_workspace_runtime_env",
        lambda **kwargs: ("task-runtime-start", {
            "kind": "uv",
            "status": "ready",
            "display_name": "Workspace UV",
        }),
    )

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-runtime-start",
        title="任务运行态启动",
        env_id="workspace-default",
        initial_conversation_id="branch-start",
        initial_conversation_title="Start",
    )
    assert workspace.current_conversation is not None

    active_sessions: set[str] = set()
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_local_kernel_active",
        lambda session_id, user_id: session_id in active_sessions,
    )
    import app.api.routes.workspaces_conversation_utils as conversation_utils_module

    monkeypatch.setattr(
        conversation_utils_module,
        "_is_runtime_busy",
        lambda user_id, session_id: False,
    )

    start_calls: list[tuple[str, str, str | None, bool]] = []

    async def _fake_start_kernel(
        session_id: str,
        user_id: str = "default",
        cwd: str | None = None,
        helper_env: dict[str, str] | None = None,
    ) -> bool:
        start_calls.append((session_id, user_id, cwd, helper_env is not None))
        active_sessions.add(session_id)
        return True

    monkeypatch.setattr(LocalIPythonBox, "start_kernel", _fake_start_kernel)

    response = await workspace_route.start_workspace_conversation_runtime(
        "task-runtime-start",
        "branch-start",
        current_user=_build_user(),
    )

    assert response.success is True
    assert response.action == "start"
    assert response.runtime.runtime_summary["status"] == "ready"
    assert response.runtime.can_stop_runtime is True
    assert start_calls == [
        (
            "branch-start",
            "local_default",
            str(tmp_path / "local_default" / "task-runtime-start"),
            True,
        )
    ]

    execution_summary = service.session_manager.get_execution_summary(
        "branch-start",
        "local_default",
    )
    assert execution_summary["last_runtime_state"] == "available"


@pytest.mark.asyncio
async def test_workspace_runtime_stop_releases_branch_kernel_and_marks_discarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_workspace_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_workspace_runtime_env",
        lambda **kwargs: ("task-runtime-stop", {
            "kind": "uv",
            "status": "ready",
            "display_name": "Workspace UV",
        }),
    )

    workspace = service.create_workspace(
        user_id="local_default",
        workspace_id="task-runtime-stop",
        title="任务运行态关闭",
        initial_conversation_id="branch-stop",
        initial_conversation_title="Stop",
    )
    assert workspace.current_conversation is not None

    active_sessions = {"branch-stop"}
    monkeypatch.setattr(
        runtime_state_module,
        "_resolve_local_kernel_active",
        lambda session_id, user_id: session_id in active_sessions,
    )
    import app.api.routes.workspaces_conversation_utils as conversation_utils_module

    monkeypatch.setattr(
        conversation_utils_module,
        "_is_runtime_busy",
        lambda user_id, session_id: False,
    )

    shutdown_calls: list[tuple[str, str]] = []

    def _fake_shutdown_kernel(
        session_id: str,
        user_id: str = "default",
    ) -> None:
        shutdown_calls.append((session_id, user_id))
        active_sessions.discard(session_id)

    monkeypatch.setattr(LocalIPythonBox, "shutdown_kernel", _fake_shutdown_kernel)

    response = await workspace_route.stop_workspace_conversation_runtime(
        "task-runtime-stop",
        "branch-stop",
        current_user=_build_user(),
    )

    assert response.success is True
    assert response.action == "stop"
    # last_runtime_state 记录为 discarded；runtime_summary 中的 status 来自 workspace_env，仍为 ready
    assert response.runtime.last_runtime_state == "discarded"
    assert response.runtime.can_start_runtime is True
    assert shutdown_calls == [("branch-stop", "local_default")]

    execution_summary = service.session_manager.get_execution_summary(
        "branch-stop",
        "local_default",
    )
    assert execution_summary["last_runtime_state"] == "discarded"
