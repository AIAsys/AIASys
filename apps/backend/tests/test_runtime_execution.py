from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.models.runtime_environment import WorkspaceRuntimeEnv
from app.services.history import (
    current_runtime_execution_plan,
    current_workspace,
)
from app.services.runtime import runtime_execution
from app.services.runtime.runtime_execution import (
    RuntimeExecutionPlan,
    build_runtime_shell_env,
    ensure_registered_python_kernel_spec,
    ensure_uv_kernel_spec,
    kernel_name_for_runtime,
    plan_for_python_execution,
    resolve_runtime_execution_plan,
    wrap_shell_command_for_runtime,
)


class _FakeBinding:
    def __init__(self, *, env_id: str | None, sandbox_mode: str | None = None) -> None:
        self.env_id = env_id
        self.sandbox_mode = sandbox_mode


class _FakeWorkspace:
    def __init__(self, *, env_id: str | None, sandbox_mode: str | None = None) -> None:
        self.runtime_binding = _FakeBinding(env_id=env_id, sandbox_mode=sandbox_mode)


class _FakeRegistry:
    def __init__(self, workspace: _FakeWorkspace) -> None:
        self.workspace = workspace
        self.requests: list[tuple[str, str]] = []

    def get_workspace(
        self,
        user_id: str,
        workspace_id: str,
        *,
        include_conversations: bool = False,
    ) -> _FakeWorkspace:
        del include_conversations
        self.requests.append((user_id, workspace_id))
        return self.workspace


class _FakeRuntimeEnvService:
    def __init__(self, env: WorkspaceRuntimeEnv | None) -> None:
        self.env = env
        self.requests: list[tuple[str, str, str]] = []

    def inspect_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> WorkspaceRuntimeEnv:
        self.requests.append((user_id, workspace_id, env_id))
        if self.env is None:
            raise FileNotFoundError(env_id)
        return self.env


def test_resolve_runtime_plan_accepts_string_workspace_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = _FakeRegistry(_FakeWorkspace(env_id="workspace-default", sandbox_mode="local"))
    env_service = _FakeRuntimeEnvService(
        WorkspaceRuntimeEnv(
            env_id="workspace-default",
            kind="uv",
            display_name="Workspace UV",
            material_path=str(tmp_path / "env"),
        )
    )
    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service", lambda: registry
    )
    monkeypatch.setattr(
        "app.services.runtime_environment.get_runtime_environment_service", lambda: env_service
    )
    token = current_workspace.set(str(tmp_path))

    try:
        plan = resolve_runtime_execution_plan()
    finally:
        current_workspace.reset(token)

    assert plan.workspace == tmp_path
    assert plan.env_id == "workspace-default"
    assert plan.kind == "uv"
    assert registry.requests == [("local_default", tmp_path.name)]


def test_resolve_runtime_plan_without_python_binding_uses_plain_shell(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = _FakeRegistry(_FakeWorkspace(env_id=None, sandbox_mode=None))
    env_service = _FakeRuntimeEnvService(None)
    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service", lambda: registry
    )
    monkeypatch.setattr(
        "app.services.runtime_environment.get_runtime_environment_service", lambda: env_service
    )

    plan = resolve_runtime_execution_plan(workspace=tmp_path)
    command, cwd = wrap_shell_command_for_runtime("python -V", plan=plan)

    assert plan.workspace == tmp_path
    assert plan.env_id is None
    assert plan.kind == "plain_shell"
    assert plan.sandbox_mode == "plain_shell"
    assert plan.env is None
    assert plan.display_name == "未绑定 Python"
    assert command == "python -V"
    assert cwd == tmp_path
    assert env_service.requests == []
    shell_env = build_runtime_shell_env({}, plan=plan)
    assert shell_env["AIASYS_RUNTIME_SANDBOX_MODE"] == "plain_shell"
    assert "AIASYS_RUNTIME_ENV_ID" not in shell_env


def test_python_execution_requires_enabled_python_environment(tmp_path: Path) -> None:
    plan = RuntimeExecutionPlan(
        sandbox_mode="plain_shell",
        env_id=None,
        display_name="未绑定 Python",
        workspace=tmp_path,
        env=None,
    )

    with pytest.raises(RuntimeError, match="未启用 Python 环境"):
        plan_for_python_execution(plan)


def test_python_execution_rejects_missing_bound_python_environment(tmp_path: Path) -> None:
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="workspace-default",
        display_name="workspace-default (未找到)",
        workspace=tmp_path,
        env=None,
    )

    with pytest.raises(RuntimeError, match="绑定的 Python 环境不可用"):
        plan_for_python_execution(plan)


def test_wrap_uv_shell_command_uses_uv_project_and_workspace_directory(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    project_dir = tmp_path / "workspace" / "env"
    project_dir.mkdir(parents=True)
    (project_dir / "pyproject.toml").write_text("[project]\nname = \"test\"\n", encoding="utf-8")
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="uv-env",
        display_name="Workspace UV",
        workspace=workspace,
        env=WorkspaceRuntimeEnv(
            env_id="uv-env",
            kind="uv",
            display_name="Workspace UV",
            material_path=str(project_dir),
        ),
    )

    command, cwd = wrap_shell_command_for_runtime(
        "python -c 'print(1)'",
        plan=plan,
    )

    assert cwd == workspace
    assert f"uv run --project {project_dir}" in command
    assert f"--directory {workspace}" in command
    assert "sh -lc" in command
    assert "python -c" in command


@pytest.mark.skipif(os.name != "nt", reason="Windows Path 与文件系统行为只能在 Windows 真机验证")
def test_wrap_uv_shell_command_uses_powershell_on_windows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows 上没有 sh，uv 包装改用 PowerShell。"""
    monkeypatch.setattr(runtime_execution.os, "name", "nt")
    workspace = tmp_path / "workspace"
    project_dir = tmp_path / "workspace" / "env"
    project_dir.mkdir(parents=True)
    (project_dir / "pyproject.toml").write_text("[project]\nname = \"test\"\n", encoding="utf-8")
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="uv-env",
        display_name="Workspace UV",
        workspace=workspace,
        env=WorkspaceRuntimeEnv(
            env_id="uv-env",
            kind="uv",
            display_name="Workspace UV",
            material_path=str(project_dir),
        ),
    )

    command, cwd = wrap_shell_command_for_runtime(
        "python -V",
        plan=plan,
    )

    assert cwd == workspace
    assert "uv run --project" in command
    assert "workspace/env" in command.replace("\\", "/")
    assert "--directory" in command
    assert "workspace" in command.replace("\\", "/")
    assert "powershell -NoProfile -Command" in command
    assert "sh -lc" not in command
    assert "cmd /c" not in command
    assert "python -V" in command


def test_uv_kernel_spec_is_created_in_dynamic_kernel_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    kernel_root = tmp_path / "kernels"
    monkeypatch.setattr(runtime_execution, "_DYNAMIC_KERNEL_ROOT", kernel_root)
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="uv-env",
        display_name="Workspace UV",
        workspace=tmp_path / "workspace",
        env=WorkspaceRuntimeEnv(
            env_id="uv-env",
            kind="uv",
            display_name="Workspace UV",
            material_path=str(tmp_path / "workspace" / "env"),
        ),
    )

    kernel_name = kernel_name_for_runtime("python3", plan=plan)
    spec_path = kernel_root / kernel_name / "kernel.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    assert kernel_name == "aiasys-uv-uv-env"
    assert spec["argv"][:5] == [
        "uv",
        "run",
        "--project",
        str(tmp_path / "workspace" / "env"),
        "--with",
    ]
    assert "ipykernel" in spec["argv"]
    assert ensure_uv_kernel_spec(plan) == kernel_name


def test_registered_python_kernel_spec_is_created_in_dynamic_kernel_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    kernel_root = tmp_path / "kernels"
    python_bin = tmp_path / "python"
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(runtime_execution, "_DYNAMIC_KERNEL_ROOT", kernel_root)
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="python-existing",
        display_name="Existing Python",
        workspace=tmp_path / "workspace",
        env=WorkspaceRuntimeEnv(
            env_id="python-existing",
            kind="registered_python",
            display_name="Existing Python",
            python_executable=str(python_bin),
        ),
    )

    kernel_name = kernel_name_for_runtime("python3", plan=plan)
    spec_path = kernel_root / kernel_name / "kernel.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    assert kernel_name == "aiasys-python-python-existing"
    assert spec["argv"][:3] == [str(python_bin), "-m", "ipykernel_launcher"]
    assert spec["metadata"]["aiasys"]["kind"] == "registered_python"
    assert ensure_registered_python_kernel_spec(plan) == kernel_name


def test_wrap_registered_python_shell_command_uses_bound_interpreter(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    python_bin = tmp_path / "python"
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="python-existing",
        display_name="Existing Python",
        workspace=workspace,
        env=WorkspaceRuntimeEnv(
            env_id="python-existing",
            kind="registered_python",
            display_name="Existing Python",
            python_executable=str(python_bin),
        ),
    )

    command, cwd = wrap_shell_command_for_runtime("python -V", plan=plan)
    shell_env = build_runtime_shell_env({"PATH": "/usr/bin"}, plan=plan)

    assert cwd == workspace
    assert command == "python -V"
    assert shell_env["AIASYS_RUNTIME_ENV_KIND"] == "registered_python"
    assert shell_env["AIASYS_RUNTIME_PYTHON_EXECUTABLE"] == str(python_bin)
    assert shell_env["PATH"].startswith(str(tmp_path))


def test_build_runtime_shell_env_injects_uv_to_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """build_runtime_shell_env 应把 uv 可执行文件所在目录追加到 PATH，避免子进程找不到 uv。"""
    fake_uv = tmp_path / "bin" / "uv"
    fake_uv.parent.mkdir(parents=True)
    fake_uv.write_text("#!/bin/sh\necho fake uv", encoding="utf-8")
    fake_uv.chmod(0o755)
    monkeypatch.setattr(runtime_execution.shutil, "which", lambda _name: str(fake_uv))

    workspace = tmp_path / "workspace"
    project_dir = tmp_path / "workspace" / "env"
    plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="uv-env",
        display_name="Workspace UV",
        workspace=workspace,
        env=WorkspaceRuntimeEnv(
            env_id="uv-env",
            kind="uv",
            display_name="Workspace UV",
            material_path=str(project_dir),
        ),
    )

    shell_env = build_runtime_shell_env({"PATH": "/usr/bin"}, plan=plan)
    assert str(fake_uv.parent) in shell_env["PATH"]


def test_resolve_runtime_plan_prefers_frozen_execution_plan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    registry = _FakeRegistry(
        _FakeWorkspace(env_id="workspace-default", sandbox_mode="local"),
    )
    env_service = _FakeRuntimeEnvService(None)
    frozen_plan = RuntimeExecutionPlan(
        sandbox_mode="local",
        env_id="uv-env",
        display_name="Frozen UV",
        workspace=tmp_path,
        env=WorkspaceRuntimeEnv(
            env_id="uv-env",
            kind="uv",
            display_name="Frozen UV",
            material_path=str(tmp_path / "env"),
        ),
        env_vars={"TOKEN": "frozen"},
        frozen=True,
    )
    monkeypatch.setattr(
        "app.services.workspace_registry.get_workspace_registry_service", lambda: registry
    )
    monkeypatch.setattr(
        "app.services.runtime_environment.get_runtime_environment_service", lambda: env_service
    )
    workspace_token = current_workspace.set(tmp_path / "workspaces" / "alice" / "task-alpha")
    plan_token = current_runtime_execution_plan.set(frozen_plan)

    try:
        plan = resolve_runtime_execution_plan()
    finally:
        current_runtime_execution_plan.reset(plan_token)
        current_workspace.reset(workspace_token)

    assert plan is frozen_plan
    assert plan.env_id == "uv-env"
    assert plan.kind == "uv"
    assert plan.env_vars == {"TOKEN": "frozen"}
    assert plan.frozen is True
    assert registry.requests == []
    assert env_service.requests == []
