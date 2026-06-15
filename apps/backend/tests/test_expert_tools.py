"""测试专家管理 Agent 工具。"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.agents.tools.expert_tools import ConfigureExpert, InstallExpert, ListSystemExperts
from app.services import expert_roles as expert_roles_module
from app.services.history import current_user_id, current_workspace
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


@pytest.fixture
def setup_context(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    user_id = "local_default"
    workspace_id = "test-expert-tools"

    monkeypatch.setattr("app.services.agent.subagent_catalog.WORKSPACE_DIR", tmp_path)

    registry = WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: registry,
    )

    registry.create_workspace(
        user_id=user_id,
        workspace_id=workspace_id,
        title="Expert Tools Test",
    )
    workspace_dir = registry.get_workspace_root(user_id, workspace_id)

    current_user_id.set(user_id)
    current_workspace.set(workspace_dir)
    yield workspace_dir
    current_user_id.set(None)
    current_workspace.set(None)


@pytest.mark.asyncio
async def test_list_system_experts_returns_builtins(setup_context: Path) -> None:
    result = await ListSystemExperts().invoke()

    assert result.is_error is False
    assert "专家" in result.content
    artifacts = result.artifacts or []
    experts = []
    for artifact in artifacts:
        if isinstance(artifact, dict) and "experts" in artifact:
            experts = artifact["experts"]
            break

    role_ids = {e["role_id"] for e in experts}
    assert "data_analyst" in role_ids
    assert "coder" in role_ids


@pytest.mark.asyncio
async def test_install_expert_to_workspace(setup_context: Path) -> None:
    result = await InstallExpert().invoke(name="data_analyst", scope="workspace")

    assert result.is_error is False
    assert "data_analyst" in result.content
    assert "workspace" in result.content

    artifacts = result.artifacts or []
    assert any(
        isinstance(a, dict) and a.get("name") == "data_analyst" for a in artifacts
    )


@pytest.mark.asyncio
async def test_configure_expert_disable_installed(setup_context: Path) -> None:
    await InstallExpert().invoke(name="data_analyst", scope="workspace")

    result = await ConfigureExpert().invoke(
        name="data_analyst", scope="workspace", enabled=False
    )

    assert result.is_error is False
    assert "data_analyst" in result.content

    artifacts = result.artifacts or []
    config = next(
        (a for a in artifacts if isinstance(a, dict) and a.get("name") == "data_analyst"),
        None,
    )
    assert config is not None
    assert config["default_enabled"] is False


@pytest.mark.asyncio
async def test_configure_expert_rejects_not_installed(setup_context: Path) -> None:
    result = await ConfigureExpert().invoke(
        name="reviewer", scope="workspace", enabled=False
    )

    assert result.is_error is True
    assert "尚未安装" in result.content


@pytest.mark.asyncio
async def test_install_expert_by_display_name(setup_context: Path) -> None:
    result = await InstallExpert().invoke(name="数据分析专家", scope="workspace")

    assert result.is_error is False
    assert "data_analyst" in result.content
    assert "workspace" in result.content

    artifacts = result.artifacts or []
    assert any(
        isinstance(a, dict) and a.get("name") == "data_analyst" for a in artifacts
    )


@pytest.mark.asyncio
async def test_install_expert_rejects_unknown(setup_context: Path) -> None:
    result = await InstallExpert().invoke(name="unknown_role", scope="workspace")

    assert result.is_error is True
    assert "不是系统内置专家" in result.content
