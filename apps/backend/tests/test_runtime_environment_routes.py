from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.api.routes import runtime_envs as runtime_envs_route
from app.models.runtime_environment import (
    BindWorkspaceRuntimeEnvRequest,
    EnsureWorkspaceUvEnvRequest,
    InstallWorkspacePackagesRequest,
    RegisterWorkspacePythonEnvRequest,
    RuntimeEnvCommandResult,
)
from app.models.workspace import WorkspaceRuntimeBinding
from app.models.user import UserInfo
from app.services.runtime_environment import RuntimeEnvironmentService
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> RuntimeEnvironmentService:
    workspace_registry = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    return RuntimeEnvironmentService(tmp_path, workspace_registry=workspace_registry)


def _create_workspace(service: RuntimeEnvironmentService, workspace_id: str = "task-env") -> None:
    service.workspace_registry.create_workspace(
        user_id="local_default",
        workspace_id=workspace_id,
        title="环境验证",
        initial_conversation_title="默认对话",
    )
    workspace_dir = service.workspace_registry.get_workspace_root(
        "local_default",
        workspace_id,
    )
    shutil.rmtree(workspace_dir / ".env", ignore_errors=True)


@pytest.mark.asyncio
async def test_runtime_env_route_ensures_uv_env_without_mutating_backend_venv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)
    monkeypatch.setattr(service, "is_uv_available", lambda: True)

    response = await runtime_envs_route.ensure_workspace_uv_env(
        "task-env",
        EnsureWorkspaceUvEnvRequest(
            display_name="任务 UV",
            python_version="3.11",
            create_venv=False,
            sync=False,
        ),
        current_user=_build_user(),
    )

    workspace_dir = tmp_path / "local_default" / "task-env"
    assert response.env.kind == "uv"
    assert response.env.env_id == "workspace-default"
    assert response.env.display_name == "任务 UV"
    assert response.env.material_path == str(workspace_dir / ".env")
    assert 'requires-python = ">=3.11"' in (
        workspace_dir / ".env" / "pyproject.toml"
    ).read_text(encoding="utf-8")
    assert (workspace_dir / ".env" / ".python-version").read_text(encoding="utf-8") == "3.11\n"
    assert not (workspace_dir / ".env" / ".venv").exists()
    assert "apps/backend/.venv" not in (response.env.python_executable or "")

    registry = await runtime_envs_route.list_workspace_runtime_envs(
        "task-env",
        inspect=True,
        current_user=_build_user(),
    )
    assert registry.total == 1
    assert registry.default_env_id == "workspace-default"
    assert registry.envs[0].package_count == 0


@pytest.mark.asyncio
async def test_runtime_env_route_installs_uv_packages_via_uv_cli(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)
    monkeypatch.setattr(service, "is_uv_available", lambda: True)
    commands: list[list[str]] = []

    def fake_run_uv(command: list[str], *, cwd: Path) -> RuntimeEnvCommandResult:
        commands.append(command)
        return RuntimeEnvCommandResult(
            ok=True,
            command=command,
            cwd=str(cwd),
            returncode=0,
            stdout="ok",
        )

    monkeypatch.setattr(service, "_run_uv", fake_run_uv)

    response = await runtime_envs_route.install_workspace_uv_packages(
        "task-env",
        "workspace-default",
        InstallWorkspacePackagesRequest(
            packages=["pandas==2.2.0", "numpy"],
            sync=False,
        ),
        current_user=_build_user(),
    )

    assert response.env.env_id == "workspace-default"
    assert response.command_result is not None
    assert response.command_result.ok is True
    assert response.env.display_name == "Workspace UV"
    assert commands == [["uv", "add", "--no-sync", "pandas==2.2.0", "numpy"]]


@pytest.mark.asyncio
async def test_runtime_env_route_keeps_uv_display_name_when_installing_packages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)
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

    await runtime_envs_route.ensure_workspace_uv_env(
        "task-env",
        EnsureWorkspaceUvEnvRequest(display_name="任务 UV"),
        current_user=_build_user(),
    )
    response = await runtime_envs_route.install_workspace_uv_packages(
        "task-env",
        "workspace-default",
        InstallWorkspacePackagesRequest(packages=["scipy"], sync=False),
        current_user=_build_user(),
    )

    assert response.env.display_name == "任务 UV"


# Docker helper classes removed; Docker routes dismantled.

@pytest.mark.asyncio
async def test_runtime_env_route_binds_uv_env_as_default_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    service.workspace_registry.update_workspace(
        user_id="local_default",
        workspace_id="task-env",
        runtime_binding=WorkspaceRuntimeBinding(
            sandbox_mode="local",
            env_id="python-data-analysis",
            env_vars={"TOKEN": "kept"},
        ),
    )
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)
    monkeypatch.setattr(service, "is_uv_available", lambda: True)

    await runtime_envs_route.ensure_workspace_uv_env(
        "task-env",
        EnsureWorkspaceUvEnvRequest(display_name="任务 UV"),
        current_user=_build_user(),
    )
    bind_response = await runtime_envs_route.bind_workspace_runtime_env(
        "task-env",
        BindWorkspaceRuntimeEnvRequest(env_id="workspace-default"),
        current_user=_build_user(),
    )

    workspace = service.workspace_registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )
    assert bind_response.refresh_required is True
    assert bind_response.env.active is True
    assert workspace.runtime_binding.sandbox_mode == "local"
    assert workspace.runtime_binding.env_id == "workspace-default"
    assert workspace.runtime_binding.env_vars == {"TOKEN": "kept"}


@pytest.mark.asyncio
async def test_runtime_env_route_registers_existing_python_and_binds_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    python_bin = tmp_path / "python-bin"
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)
    monkeypatch.setattr(service, "_detect_python_version", lambda path: "3.12.1")
    monkeypatch.setattr(service, "_list_python_packages", lambda path: [])

    response = await runtime_envs_route.register_workspace_python_env(
        "task-env",
        RegisterWorkspacePythonEnvRequest(
            env_id="python-existing",
            display_name="已有 Python",
            python_executable=str(python_bin),
            source_kernel_name="existing",
            activate=True,
        ),
        current_user=_build_user(),
    )
    workspace = service.workspace_registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )
    registry = await runtime_envs_route.list_workspace_runtime_envs(
        "task-env",
        inspect=False,
        current_user=_build_user(),
    )

    assert response.env.kind == "registered_python"
    assert response.env.env_id == "python-existing"
    assert response.env.active is True
    assert response.env.python_executable == str(python_bin)
    assert response.env.python_version == "3.12.1"
    assert response.refresh_required is True
    assert workspace.runtime_binding.sandbox_mode == "local"
    assert workspace.runtime_binding.env_id == "python-existing"
    assert registry.active_env_id == "python-existing"


@pytest.mark.asyncio
async def test_runtime_env_route_rejects_relative_python_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)

    with pytest.raises(runtime_envs_route.HTTPException) as exc_info:
        await runtime_envs_route.register_workspace_python_env(
            "task-env",
            RegisterWorkspacePythonEnvRequest(
                env_id="python-relative",
                python_executable="python",
                activate=True,
            ),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 400
    assert "完整绝对路径" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_runtime_env_route_unregisters_active_uv_and_preserves_env_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    service.workspace_registry.update_workspace(
        user_id="local_default",
        workspace_id="task-env",
        runtime_binding=WorkspaceRuntimeBinding(
            sandbox_mode="local",
            env_id="workspace-default",
            env_vars={"TOKEN": "kept"},
        ),
    )
    monkeypatch.setattr(runtime_envs_route, "_service", lambda: service)
    monkeypatch.setattr(service, "is_uv_available", lambda: True)

    await runtime_envs_route.ensure_workspace_uv_env(
        "task-env",
        EnsureWorkspaceUvEnvRequest(display_name="任务 UV"),
        current_user=_build_user(),
    )
    await runtime_envs_route.bind_workspace_runtime_env(
        "task-env",
        BindWorkspaceRuntimeEnvRequest(env_id="workspace-default"),
        current_user=_build_user(),
    )
    response = await runtime_envs_route.unregister_workspace_runtime_env(
        "task-env",
        "workspace-default",
        current_user=_build_user(),
    )
    registry = await runtime_envs_route.list_workspace_runtime_envs(
        "task-env",
        inspect=False,
        current_user=_build_user(),
    )
    workspace = service.workspace_registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )

    assert response.env.env_id == "workspace-default"
    assert response.env.active is False
    assert registry.active_env_id is None
    assert registry.envs == []
    assert workspace.runtime_binding.sandbox_mode is None
    assert workspace.runtime_binding.env_id is None
    assert workspace.runtime_binding.env_vars == {"TOKEN": "kept"}
