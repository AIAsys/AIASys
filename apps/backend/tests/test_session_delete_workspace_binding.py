from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import BackgroundTasks

from app.api.routes import sessions_branches as session_route
from app.api.routes import workspaces_core as workspace_route
from app.api.routes.sessions_branches import delete_session
from app.api.routes.workspaces_core import delete_workspace
from app.agents.tools.local_ipython_box import LocalIPythonBox
from app.models.user import UserInfo
import app.services.agent as agent_module
import app.services.auto_tasks.engine as auto_task_engine
from app.services.auto_tasks.engine import AutoTaskStore
from app.services.auto_tasks.models import AutoTask, AutoTaskTriggerType, TaskStatus
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    manager = SessionManager(tmp_path)
    return WorkspaceRegistryService(tmp_path, session_manager=manager)


@pytest.mark.asyncio
async def test_delete_session_removes_workspace_binding_and_updates_current_conversation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(session_route, "session_manager", service.session_manager)
    monkeypatch.setattr(session_route, "get_workspace_registry_service", lambda: service)

    async def _fake_stop_session(user_id: str, session_id: str) -> None:
        return None

    monkeypatch.setattr(session_route.agent_service, "stop_session", _fake_stop_session)
    monkeypatch.setattr(
        LocalIPythonBox, "shutdown_kernel", staticmethod(lambda *_args, **_kwargs: None)
    )

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-delete-binding",
        title="删除会话测试工作区",
        initial_conversation_title="首会话",
    )
    first = detail.current_conversation
    assert first is not None

    second = service.create_conversation(
        user_id="local_default",
        workspace_id="workspace-delete-binding",
        title="待删除会话",
    )

    response = await delete_session(
        user_id="local_default",
        session_id=second.session_id,
        background_tasks=BackgroundTasks(),
        current_user=_build_user(),
    )

    updated = service.get_workspace(
        "local_default",
        "workspace-delete-binding",
        include_conversations=True,
    )

    assert response == {"success": True}
    assert updated.current_conversation_id == first.session_id
    assert {item.session_id for item in updated.conversations} == {first.session_id}
    assert not (tmp_path / "local_default" / second.session_id).exists()


@pytest.mark.asyncio
async def test_delete_session_cleans_ghost_workspace_binding_when_session_dir_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(session_route, "session_manager", service.session_manager)
    monkeypatch.setattr(session_route, "get_workspace_registry_service", lambda: service)

    async def _fake_stop_session(user_id: str, session_id: str) -> None:
        return None

    monkeypatch.setattr(session_route.agent_service, "stop_session", _fake_stop_session)
    monkeypatch.setattr(
        LocalIPythonBox, "shutdown_kernel", staticmethod(lambda *_args, **_kwargs: None)
    )

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-ghost-binding",
        title="幽灵会话测试工作区",
        initial_conversation_title="首会话",
    )
    first = detail.current_conversation
    assert first is not None

    ghost = service.create_conversation(
        user_id="local_default",
        workspace_id="workspace-ghost-binding",
        title="幽灵会话",
    )

    detached = service.session_manager.detach_session_for_deletion(
        ghost.session_id, "local_default"
    )
    assert detached is not None
    service.session_manager.purge_detached_session(detached)

    response = await delete_session(
        user_id="local_default",
        session_id=ghost.session_id,
        background_tasks=BackgroundTasks(),
        current_user=_build_user(),
    )

    updated = service.get_workspace(
        "local_default",
        "workspace-ghost-binding",
        include_conversations=True,
    )

    assert response == {"success": True}
    assert updated.current_conversation_id == first.session_id
    assert {item.session_id for item in updated.conversations} == {first.session_id}


def test_delete_workspace_clears_auto_task_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", tmp_path)
    service = _build_service(tmp_path)
    service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-delete-auto-task",
        title="删除工作区清理自动任务",
        initial_conversation_title="首会话",
    )
    task = AutoTask(
        task_id="task-delete-auto-task-001",
        workspace_id="workspace-delete-auto-task",
        user_id="local_default",
        prompt="写入 cleanup.txt",
        trigger_type=AutoTaskTriggerType.interval,
        trigger_value="300",
        status=TaskStatus.active,
        title="待清理自动任务",
    )
    AutoTaskStore.put_task("local_default", "workspace-delete-auto-task", task)

    tasks_path = (
        tmp_path
        / "local_default"
        / "workspace-delete-auto-task"
        / ".aiasys"
        / "workspace"
        / "auto_tasks"
        / "tasks.json"
    )
    assert tasks_path.exists()

    service.delete_workspace("local_default", "workspace-delete-auto-task")

    assert not tasks_path.exists()


@pytest.mark.asyncio
async def test_delete_workspace_route_stops_all_workspace_sessions_before_delete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(workspace_route, "get_workspace_registry_service", lambda: service)

    calls: list[tuple[str, str]] = []

    async def _fake_stop_session(user_id: str, session_id: str) -> None:
        calls.append(("stop", session_id))

    async def _fake_wait_for_session_stop(
        user_id: str,
        session_id: str,
        *,
        timeout_s: float = 5.0,
    ) -> bool:
        _ = user_id
        _ = timeout_s
        calls.append(("wait", session_id))
        return True

    monkeypatch.setattr(agent_module.agent_service, "stop_session", _fake_stop_session)
    monkeypatch.setattr(workspace_route, "_wait_for_session_stop", _fake_wait_for_session_stop)
    monkeypatch.setattr(
        LocalIPythonBox,
        "shutdown_kernel",
        staticmethod(lambda session_id, user_id="default": calls.append(("shutdown", session_id))),
    )

    detail = service.create_workspace(
        user_id="local_default",
        workspace_id="workspace-delete-route-stop",
        title="删除工作区前先停会话",
        initial_conversation_title="首会话",
    )
    first = detail.current_conversation
    assert first is not None

    second = service.create_conversation(
        user_id="local_default",
        workspace_id="workspace-delete-route-stop",
        title="第二会话",
    )

    response = await delete_workspace(
        workspace_id="workspace-delete-route-stop",
        current_user=_build_user(),
    )

    expected_session_ids = {first.session_id, second.session_id}
    assert response.success is True
    assert response.workspace_id == "workspace-delete-route-stop"
    assert {session_id for action, session_id in calls if action == "stop"} == expected_session_ids
    assert {session_id for action, session_id in calls if action == "wait"} == expected_session_ids
    assert {
        session_id for action, session_id in calls if action == "shutdown"
    } == expected_session_ids
    assert not (tmp_path / "local_default" / "workspace-delete-route-stop").exists()
