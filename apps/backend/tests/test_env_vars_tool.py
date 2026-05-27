from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.agents.tools import env_vars_tool as env_vars_tool_module
from app.agents.tools.env_vars_tool import DeleteEnvVar, ListEnvVars, SetEnvVar
from app.services.agent.system_presets import (
    DATA_ANALYSIS_BASELINE,
    LIST_ENV_VARS_TOOL_PATH,
    RUNTIME_ENVIRONMENT_TOOL_PATH,
    get_role_type_default_tools,
)
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry
from app.services.capability_catalog import resolve_tool_category_tool_names
from app.services.global_env_vars import set_global_env_vars
from app.services.history import current_runtime_env_vars, current_session_id, current_user_id, current_workspace
from app.services.runtime_tooling import probe_runtime_tool
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService
from app.services import workspace_registry as workspace_registry_module


@pytest.fixture
def runtime_env_vars():
    token = current_runtime_env_vars.set(
        {
            "AIASYS_TEST_SESSION_SECRET": "session-secret-value",
            "AIASYS_TEST_SESSION_FLAG": "enabled",
        }
    )
    yield
    current_runtime_env_vars.reset(token)


@pytest.mark.asyncio
async def test_list_env_vars_returns_names_without_values(
    monkeypatch: pytest.MonkeyPatch,
    runtime_env_vars,
) -> None:
    monkeypatch.setenv("AIASYS_TEST_HOST_NAME", "host-value")

    result = await ListEnvVars().invoke()

    assert not result.is_error
    payload = json.loads(result.content)
    env_vars = payload["env_vars"]

    assert payload["status"] == "success"
    assert payload["count"] == len(env_vars)
    assert "AIASYS_TEST_HOST_NAME" in env_vars
    assert "AIASYS_TEST_SESSION_SECRET" in env_vars
    assert "AIASYS_TEST_SESSION_FLAG" in env_vars
    assert "host-value" not in result.content
    assert "session-secret-value" not in result.content
    assert "enabled" not in result.content


def test_list_env_vars_tool_schema_is_registered() -> None:
    registry = ToolRegistry()
    registry.register(ListEnvVars())

    schema = registry.get_openai_schema()[0]["function"]

    assert schema["name"] == "ListEnvVars"
    assert schema["parameters"]["type"] == "object"


def test_list_env_vars_tool_is_discoverable_from_default_tool_sets() -> None:
    assert probe_runtime_tool(LIST_ENV_VARS_TOOL_PATH).available is True
    assert LIST_ENV_VARS_TOOL_PATH in DATA_ANALYSIS_BASELINE.tools
    assert LIST_ENV_VARS_TOOL_PATH in get_role_type_default_tools("coder")
    assert LIST_ENV_VARS_TOOL_PATH in resolve_tool_category_tool_names(["environment"])


def test_runtime_environment_tool_is_discoverable_from_default_tool_sets() -> None:
    assert probe_runtime_tool(RUNTIME_ENVIRONMENT_TOOL_PATH).available is True
    assert RUNTIME_ENVIRONMENT_TOOL_PATH in DATA_ANALYSIS_BASELINE.tools
    assert RUNTIME_ENVIRONMENT_TOOL_PATH not in get_role_type_default_tools("coder")
    assert RUNTIME_ENVIRONMENT_TOOL_PATH in resolve_tool_category_tool_names(["environment"])


@pytest.fixture
def workspace_env_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    registry = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    registry.create_workspace(
        user_id="local_default",
        workspace_id="task-env",
        title="环境变量测试",
        initial_conversation_id="session-alpha",
        initial_conversation_title="默认会话",
    )
    workspace_root = registry.get_workspace_root("local_default", "task-env")
    monkeypatch.setattr(
        workspace_registry_module,
        "get_workspace_registry_service",
        lambda: registry,
    )
    monkeypatch.setattr(
        env_vars_tool_module,
        "get_workspace_registry_service",
        lambda: registry,
    )
    user_token = current_user_id.set("local_default")
    session_token = current_session_id.set("session-alpha")
    workspace_token = current_workspace.set(workspace_root)
    env_token = current_runtime_env_vars.set(None)
    try:
        yield registry, workspace_root
    finally:
        current_runtime_env_vars.reset(env_token)
        current_workspace.reset(workspace_token)
        current_session_id.reset(session_token)
        current_user_id.reset(user_token)


@pytest.mark.asyncio
async def test_set_env_var_writes_workspace_registry(
    workspace_env_context,
) -> None:
    registry, workspace_root = workspace_env_context

    result = await SetEnvVar().invoke(name="AIASYS_TEST_TOKEN", value="workspace-secret")

    assert not result.is_error
    workspace = registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )
    assert workspace.runtime_binding.env_vars == {"AIASYS_TEST_TOKEN": "workspace-secret"}
    assert current_runtime_env_vars.get() == {"AIASYS_TEST_TOKEN": "workspace-secret"}
    assert not (workspace_root / "metadata.json").exists()


@pytest.mark.asyncio
async def test_delete_env_var_updates_workspace_registry_and_restores_global_value(
    workspace_env_context,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry, _workspace_root = workspace_env_context
    monkeypatch.setattr("app.core.config.WORKSPACE_DIR", registry.base_dir)
    set_global_env_vars("local_default", {"SHARED_KEY": "global-value"})
    registry.set_workspace_env_var(
        "local_default",
        "task-env",
        "SHARED_KEY",
        "workspace-value",
    )
    current_runtime_env_vars.set({"SHARED_KEY": "workspace-value"})

    result = await DeleteEnvVar().invoke(name="SHARED_KEY")

    assert not result.is_error
    workspace = registry.get_workspace(
        "local_default",
        "task-env",
        include_conversations=False,
    )
    assert workspace.runtime_binding.env_vars == {}
    assert current_runtime_env_vars.get() == {"SHARED_KEY": "global-value"}


def test_aiasys_env_skill_reads_and_writes_workspace_registry_file(tmp_path: Path) -> None:
    workspace_root = tmp_path / "local_default" / "task-env"
    meta_path = workspace_root / ".aiasys" / "workspace" / "workspace.json"
    meta_path.parent.mkdir(parents=True)
    meta_path.write_text(
        json.dumps(
            {
                "workspace_id": "task-env",
                "title": "环境变量测试",
                "runtime_binding": {
                    "sandbox_mode": "local",
                    "env_id": "workspace-default",
                    "env_vars": {},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    script = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "builtin"
        / "aiasys-platform-skill"
        / "scripts"
        / "env_vars.py"
    )
    env = {**os.environ, "AIASYS_WORKSPACE_ROOT": str(workspace_root)}

    set_result = subprocess.run(
        [sys.executable, str(script), "set", "--name", "AIASYS_SKILL_TOKEN", "--value", "secret-value"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    get_result = subprocess.run(
        [sys.executable, str(script), "get", "--name", "AIASYS_SKILL_TOKEN"],
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )

    payload = json.loads(get_result.stdout)
    saved = json.loads(meta_path.read_text(encoding="utf-8"))
    assert json.loads(set_result.stdout)["status"] == "success"
    assert saved["runtime_binding"]["env_vars"] == {"AIASYS_SKILL_TOKEN": "secret-value"}
    assert payload["masked"] is True
    assert payload["value"] == "secr****alue"
    assert not (workspace_root / "metadata.json").exists()
