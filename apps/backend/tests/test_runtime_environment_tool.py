from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.agents.tools.runtime_environment_tool import RuntimeEnvironment
from app.models.runtime_environment import RuntimeEnvCommandResult, RuntimeEnvPackage
from app.models.workspace import WorkspaceRuntimeBinding
from app.services import runtime_environment as runtime_environment_module
from app.agents.tools import runtime_environment_tool as runtime_environment_tool_module
from app.services.history import current_session_id, current_user_id, current_workspace
from app.services.runtime.runtime_execution import resolve_runtime_execution_plan
from app.services.runtime_environment import RuntimeEnvironmentService
from app.services.session import SessionManager
from app.services import workspace_registry as workspace_registry_module
from app.services.workspace_registry import WorkspaceRegistryService


def _build_service(tmp_path: Path) -> RuntimeEnvironmentService:
    workspace_registry = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    return RuntimeEnvironmentService(tmp_path, workspace_registry=workspace_registry)


def _create_workspace(
    service: RuntimeEnvironmentService,
    *,
    workspace_id: str = "task-env",
    session_id: str = "branch-alpha",
) -> Path:
    service.workspace_registry.create_workspace(
        user_id="local_default",
        workspace_id=workspace_id,
        title="环境验证",
        initial_conversation_id=session_id,
        initial_conversation_title="默认对话",
    )
    workspace_dir = service.workspace_registry.get_workspace_root("local_default", workspace_id)
    shutil.rmtree(workspace_dir / ".env", ignore_errors=True)
    return workspace_dir


def test_list_workspace_envs_does_not_materialize_empty_env_dir(tmp_path: Path) -> None:
    service = _build_service(tmp_path)
    workspace_dir = _create_workspace(service)

    registry = service.list_workspace_envs(
        "local_default",
        "task-env",
        inspect=True,
    )

    assert registry.active_env_id is None
    assert registry.envs == []
    assert not (workspace_dir / ".env").exists()


def test_runtime_env_package_listing_falls_back_without_pip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    python_bin = tmp_path / "python"
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    expected = [RuntimeEnvPackage(name="numpy", version="2.4.4")]
    monkeypatch.setattr(service, "_list_python_packages_with_pip", lambda path: [])
    monkeypatch.setattr(service, "_list_python_packages_with_metadata", lambda path: expected)

    assert service._list_python_packages(python_bin) == expected


@pytest.fixture
def runtime_tool_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    service = _build_service(tmp_path)
    workspace_dir = _create_workspace(service)
    monkeypatch.setattr(
        runtime_environment_module,
        "get_runtime_environment_service",
        lambda: service,
    )
    monkeypatch.setattr(
        runtime_environment_tool_module,
        "get_runtime_environment_service",
        lambda: service,
    )
    monkeypatch.setattr(
        workspace_registry_module,
        "get_workspace_registry_service",
        lambda: service.workspace_registry,
    )
    user_token = current_user_id.set("local_default")
    session_token = current_session_id.set("branch-alpha")
    workspace_token = current_workspace.set(workspace_dir)
    try:
        yield service, workspace_dir
    finally:
        current_workspace.reset(workspace_token)
        current_session_id.reset(session_token)
        current_user_id.reset(user_token)


@pytest.mark.asyncio
async def test_runtime_environment_tool_ensures_uv_and_binds_runtime_plan(
    runtime_tool_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, workspace_dir = runtime_tool_context
    monkeypatch.setattr(service, "is_uv_available", lambda: True)
    monkeypatch.setattr(
        service,
        "_run_uv",
        lambda command, *, cwd: RuntimeEnvCommandResult(
            ok=True,
            command=command,
            cwd=str(cwd),
            returncode=0,
            stdout="ok",
        ),
    )

    result = await RuntimeEnvironment().invoke(
        {},
        action="ensure_uv",
        display_name="Agent UV",
        python_version="3.11",
        packages=["pandas", "numpy"],
        sync=False,
        activate=True,
    )

    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["status"] == "success"
    assert payload["env"]["kind"] == "uv"
    assert payload["env"]["display_name"] == "Agent UV"
    assert payload["refresh_required"] is True
    assert 'requires-python = ">=3.11"' in (
        workspace_dir / ".env" / "pyproject.toml"
    ).read_text(encoding="utf-8")

    workspace = service.workspace_registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )
    assert workspace.runtime_binding.sandbox_mode == "local"
    assert workspace.runtime_binding.env_id == "workspace-default"

    plan = resolve_runtime_execution_plan()
    assert plan.kind == "uv"
    assert plan.env_id == "workspace-default"
    assert plan.display_name == "Agent UV"

@pytest.mark.asyncio
async def test_runtime_environment_tool_unregisters_active_uv_and_preserves_env_vars(
    runtime_tool_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _workspace_dir = runtime_tool_context
    monkeypatch.setattr(service, "is_uv_available", lambda: True)
    monkeypatch.setattr(
        service,
        "_run_uv",
        lambda command, *, cwd: RuntimeEnvCommandResult(
            ok=True,
            command=command,
            cwd=str(cwd),
            returncode=0,
        ),
    )
    service.workspace_registry.update_workspace(
        user_id="local_default",
        workspace_id="task-env",
        runtime_binding=WorkspaceRuntimeBinding(
            sandbox_mode="local",
            env_id="workspace-default",
            env_vars={"TOKEN": "kept"},
        ),
    )

    created = await RuntimeEnvironment().invoke(
        {},
        action="ensure_uv",
        display_name="Agent UV",
        activate=True,
    )
    assert not created.is_error

    result = await RuntimeEnvironment().invoke(
        {},
        action="unregister",
        env_id="workspace-default",
    )

    assert not result.is_error
    payload = json.loads(result.content)
    assert payload["status"] == "success"
    assert payload["env"]["env_id"] == "workspace-default"
    assert payload["env"]["active"] is False
    assert payload["refresh_required"] is True

    registry = service.list_workspace_envs(
        "local_default",
        "task-env",
        inspect=False,
    )
    workspace = service.workspace_registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )
    assert registry.active_env_id is None
    assert registry.envs == []
    assert workspace.runtime_binding.sandbox_mode is None
    assert workspace.runtime_binding.env_id is None
    assert workspace.runtime_binding.env_vars == {"TOKEN": "kept"}


def test_runtime_environment_tool_schema_is_registered() -> None:
    schema = RuntimeEnvironment.parameter_schema()

    assert schema["type"] == "object"
    assert "action" in schema["properties"]
    serialized = json.dumps(schema, ensure_ascii=False)
    assert "ensure_uv" in serialized
    assert "register_docker" not in serialized
