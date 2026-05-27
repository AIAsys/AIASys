from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes import sessions as sessions_module
from app.api.routes import sessions_execution as sessions_execution_module
from app.api.routes import workspaces_core as workspaces_core_module
from app.api.routes.sessions_branches import get_session_metadata
from app.api.routes.workspaces_core import (
    get_global_expert_policy,
    get_global_experts,
    get_workspace_expert_policy,
    get_workspace_experts,
    update_global_expert_policy,
    update_global_expert_visibility,
    update_workspace_expert_policy,
    update_workspace_expert_visibility,
)
from app.models.expert import (
    UpdateSubAgentVisibilityRequest,
    UpdateWorkspaceCollaborationPolicyRequest,
)
from app.models.user import UserInfo
from app.services import expert_roles as expert_roles_module
from app.services.agent import subagent_catalog
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService

SYSTEM_ROLE_IDS = {"data_analyst", "coder", "researcher", "reviewer"}


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def test_build_expert_catalog_uses_preset_store_for_local_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agents"
        / "local_sandbox_agent_config"
        / "data_analysis.preset"
    )

    def _fail_read_config(_: Path):
        raise AssertionError("local preset catalog should not read checked-in config body")

    monkeypatch.setattr(expert_roles_module, "_read_config", _fail_read_config)

    roles = expert_roles_module.build_expert_catalog_from_profile(profile_path)

    assert SYSTEM_ROLE_IDS == {
        role.role_id for role in roles
    }


def test_preset_expert_catalog_exposes_notebook_read_only_tools() -> None:
    profile_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agents"
        / "local_sandbox_agent_config"
        / "data_analysis.preset"
    )

    roles = expert_roles_module.build_expert_catalog_from_profile(profile_path)
    assert roles

    for role in roles:
        assert "app.agents.tools.notebook_session_tool:ListSessionNotebooks" in role.tool_ids
        assert "app.agents.tools.notebook_file_tool:ReadNotebook" in role.tool_ids
        assert "app.agents.tools.notebook_session_tool:ReadNotebookOutputs" in role.tool_ids
        if role.role_id != "data_analyst":
            assert "app.agents.tools.notebook_tool:ManageNotebook" not in role.tool_ids
            assert "app.agents.tools.notebook_file_tool:EditNotebookFile" not in role.tool_ids
            assert "ManageNotebook" not in role.tool_names
            assert "EditNotebookFile" not in role.tool_names


@pytest.mark.asyncio
async def test_workspace_experts_route_returns_catalog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts",
        title="协作角色工作区",
        initial_conversation_title="协作角色会话",
    )

    response = await get_workspace_experts(
        "task-experts",
        current_user=_build_user(),
    )

    role_ids = {role.role_id for role in response.roles}
    assert response.workspace_id == "task-experts"
    assert response.profile_name == "preset://local/data_analysis"
    assert SYSTEM_ROLE_IDS.issubset(role_ids)
    role_map = {role.role_id: role for role in response.roles}
    assert role_map["data_analyst"].installed_to_global is True
    assert role_map["researcher"].installed_to_global is True
    assert role_map["reviewer"].installed_to_global is True
    assert role_map["coder"].installed_to_global is False


@pytest.mark.asyncio
async def test_workspace_expert_visibility_route_writes_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts-visibility",
        title="专家可见性工作区",
        initial_conversation_title="协作角色会话",
    )

    response = await update_workspace_expert_visibility(
        "task-experts-visibility",
        "coder",
        UpdateSubAgentVisibilityRequest(
            host_selectable=False,
            default_enabled=False,
        ),
        current_user=_build_user(),
    )

    assert response.role_id == "coder"
    assert response.scope == "workspace"
    assert response.host_selectable is False
    assert response.default_enabled is False

    catalog = await get_workspace_experts(
        "task-experts-visibility",
        current_user=_build_user(),
    )
    coder = next(role for role in catalog.roles if role.role_id == "coder")
    assert coder.host_selectable is False
    assert coder.default_enabled is False
    assert coder.visibility_source == "workspace"


@pytest.mark.asyncio
async def test_global_expert_visibility_route_writes_user_default_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    response = await update_global_expert_visibility(
        "coder",
        UpdateSubAgentVisibilityRequest(
            host_selectable=False,
            default_enabled=False,
        ),
        current_user=_build_user(),
    )

    assert response.role_id == "coder"
    assert response.scope == "global"
    assert response.workspace_id is None
    assert response.host_selectable is False
    assert response.default_enabled is False

    policy_file = (
        tmp_path
        / "local_default"
        / "global_workspace"
        / ".aiasys"
        / "agent_config"
        / "collaboration_roles.json"
    )
    assert policy_file.exists()
    assert '"data_analyst"' in policy_file.read_text(encoding="utf-8")

    catalog = await get_global_experts(current_user=_build_user())
    coder = next(role for role in catalog.roles if role.role_id == "coder")
    assert coder.host_selectable is False
    assert coder.default_enabled is False
    assert coder.visibility_source == "global"


@pytest.mark.asyncio
async def test_workspace_experts_inherit_global_visibility_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts-global-inherit",
        title="继承全局协作角色策略",
        initial_conversation_title="协作角色会话",
    )

    await update_global_expert_visibility(
        "coder",
        UpdateSubAgentVisibilityRequest(
            host_selectable=False,
            default_enabled=False,
        ),
        current_user=_build_user(),
    )

    catalog = await get_workspace_experts(
        "task-experts-global-inherit",
        current_user=_build_user(),
    )
    coder = next(role for role in catalog.roles if role.role_id == "coder")
    assert coder.host_selectable is False
    assert coder.default_enabled is False
    assert coder.visibility_source == "global"


@pytest.mark.asyncio
async def test_workspace_experts_route_includes_workspace_custom_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts-custom",
        title="自定义协作角色工作区",
        initial_conversation_title="协作角色会话",
    )
    subagent_catalog.save_subagent(
        user_id="local_default",
        workspace_id="task-experts-custom",
        name="custom_reader",
        scope="workspace",
        manifest={
            "name": "custom_reader",
            "description": "工作区自定义阅读角色",
            "system_prompt": "阅读资料并总结重点。",
        },
    )

    response = await get_workspace_experts(
        "task-experts-custom",
        current_user=_build_user(),
    )

    role_map = {role.role_id: role for role in response.roles}
    assert "custom_reader" in role_map
    assert role_map["custom_reader"].source == "workspace"
    assert role_map["custom_reader"].description == "工作区自定义阅读角色"


@pytest.mark.asyncio
async def test_workspace_expert_policy_route_persists_workspace_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts-workspace-policy",
        title="工作区协作策略",
        initial_conversation_title="协作策略会话",
    )

    initial_policy = await get_workspace_expert_policy(
        "task-experts-workspace-policy",
        current_user=_build_user(),
    )
    role_map = {role.role_id: role for role in initial_policy.available_roles}
    assert set(role_map) == {"data_analyst", "researcher", "reviewer"}
    assert "coder" not in role_map

    from app.api.routes.workspaces_core import enable_workspace_builtin_expert

    await enable_workspace_builtin_expert(
        "task-experts-workspace-policy",
        "coder",
        current_user=_build_user(),
    )

    initial_policy = await get_workspace_expert_policy(
        "task-experts-workspace-policy",
        current_user=_build_user(),
    )
    role_map = {role.role_id: role for role in initial_policy.available_roles}
    coder_tool_ids = role_map["coder"].tool_ids
    assert len(coder_tool_ids) >= 2

    updated_policy = await update_workspace_expert_policy(
        "task-experts-workspace-policy",
        UpdateWorkspaceCollaborationPolicyRequest(
            enabled_role_ids=["reviewer", "coder", "reviewer"],
            role_tool_ids={
                "coder": [
                    coder_tool_ids[1],
                    coder_tool_ids[0],
                    coder_tool_ids[1],
                ],
            },
            collaboration_policy={
                "max_depth": 2,
                "max_threads": 4,
                "allow_nested_spawn": False,
                "budget_policy": {},
                "timeout_policy": {},
                "stop_policy": {},
            },
        ),
        current_user=_build_user(),
    )

    assert updated_policy.policy_mode == "workspace"
    assert updated_policy.configured_enabled_role_ids == ["coder", "reviewer"]
    assert updated_policy.configured_role_tool_ids == {"coder": coder_tool_ids[:2]}
    assert updated_policy.effective_enabled_role_ids == ["coder", "reviewer"]
    assert updated_policy.effective_role_tool_ids["coder"] == coder_tool_ids[:2]
    assert updated_policy.collaboration_policy.max_depth == 2
    assert updated_policy.collaboration_policy.max_threads == 4

    policy_file = (
        tmp_path
        / "local_default"
        / "task-experts-workspace-policy"
        / ".aiasys"
        / "agent_config"
        / "collaboration_roles.json"
    )
    assert policy_file.exists()
    payload = policy_file.read_text(encoding="utf-8")
    assert '"enabled": true' in payload
    assert "subagent_visibility.json" not in payload


@pytest.mark.asyncio
async def test_global_expert_policy_route_persists_user_defaults(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    initial_policy = await get_global_expert_policy(current_user=_build_user())
    role_map = {role.role_id: role for role in initial_policy.available_roles}
    assert set(role_map) == {"data_analyst", "researcher", "reviewer"}
    assert "coder" not in role_map

    from app.api.routes.workspaces_core import enable_global_builtin_expert

    await enable_global_builtin_expert(
        "coder",
        current_user=_build_user(),
    )

    initial_policy = await get_global_expert_policy(current_user=_build_user())
    role_map = {role.role_id: role for role in initial_policy.available_roles}
    coder_tool_ids = role_map["coder"].tool_ids
    assert len(coder_tool_ids) >= 2

    updated_policy = await update_global_expert_policy(
        UpdateWorkspaceCollaborationPolicyRequest(
            enabled_role_ids=["reviewer", "coder", "reviewer"],
            role_tool_ids={
                "coder": [
                    coder_tool_ids[1],
                    coder_tool_ids[0],
                    coder_tool_ids[1],
                ],
            },
            collaboration_policy={
                "max_depth": 2,
                "max_threads": 3,
                "allow_nested_spawn": False,
                "budget_policy": {},
                "timeout_policy": {},
                "stop_policy": {},
            },
        ),
        current_user=_build_user(),
    )

    assert updated_policy.scope == "global"
    assert updated_policy.policy_mode == "global"
    assert updated_policy.configured_enabled_role_ids == ["coder", "reviewer"]
    assert updated_policy.configured_role_tool_ids == {"coder": coder_tool_ids[:2]}
    assert updated_policy.effective_enabled_role_ids == ["coder", "reviewer"]
    assert updated_policy.effective_role_tool_ids["coder"] == coder_tool_ids[:2]
    assert updated_policy.collaboration_policy.max_depth == 2
    assert updated_policy.collaboration_policy.max_threads == 3

    policy_file = (
        tmp_path
        / "local_default"
        / "global_workspace"
        / ".aiasys"
        / "agent_config"
        / "collaboration_roles.json"
    )
    assert policy_file.exists()
    payload = policy_file.read_text(encoding="utf-8")
    assert '"enabled": true' in payload
    assert "subagent_visibility.json" not in payload


@pytest.mark.asyncio
async def test_workspace_expert_policy_can_disable_inherited_default_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts-disable-default",
        title="禁用默认角色",
        initial_conversation_title="协作策略会话",
    )

    updated_policy = await update_workspace_expert_policy(
        "task-experts-disable-default",
        UpdateWorkspaceCollaborationPolicyRequest(
            enabled_role_ids=["reviewer"],
        ),
        current_user=_build_user(),
    )

    assert updated_policy.configured_enabled_role_ids == ["reviewer"]
    assert updated_policy.effective_enabled_role_ids == ["reviewer"]
    assert "coder" not in updated_policy.effective_enabled_role_ids

    reloaded_policy = await get_workspace_expert_policy(
        "task-experts-disable-default",
        current_user=_build_user(),
    )
    assert reloaded_policy.effective_enabled_role_ids == ["reviewer"]
    policy_file = (
        tmp_path
        / "local_default"
        / "task-experts-disable-default"
        / ".aiasys"
        / "agent_config"
        / "collaboration_roles.json"
    )
    assert '"data_analyst"' in policy_file.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_workspace_expert_policy_rejects_non_selectable_role(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(
        expert_roles_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-experts-workspace-policy-visibility",
        title="协作策略可见性",
        initial_conversation_title="协作策略会话",
    )
    subagent_catalog.save_subagent_visibility_policy(
        user_id="local_default",
        role_id="reviewer",
        scope="workspace",
        workspace_id="task-experts-workspace-policy-visibility",
        host_selectable=False,
        default_enabled=False,
    )

    policy = await get_workspace_expert_policy(
        "task-experts-workspace-policy-visibility",
        current_user=_build_user(),
    )
    role_map = {role.role_id: role for role in policy.available_roles}
    assert role_map["reviewer"].host_selectable is False
    assert "reviewer" not in policy.effective_enabled_role_ids

    with pytest.raises(HTTPException) as exc_info:
        await update_workspace_expert_policy(
            "task-experts-workspace-policy-visibility",
            UpdateWorkspaceCollaborationPolicyRequest(enabled_role_ids=["reviewer"]),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 400
    assert "reviewer" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_execution_role_summary_uses_effective_role_tool_subset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    session_manager = service.session_manager

    monkeypatch.setattr(sessions_module, "session_manager", session_manager)
    monkeypatch.setattr(expert_roles_module, "WORKSPACE_DIR", tmp_path)

    session_manager.create_session(
        session_id="session-execution-role-summary",
        user_id="local_default",
        title="协作节点角色摘要",
        sandbox_mode="local",
        enabled_expert_role_ids=["coder"],
    )

    initial_policy = expert_roles_module.get_session_expert_policy(
        user_id="local_default",
        session_id="session-execution-role-summary",
    )
    # 使用 allowlist 角色（coder）测试有效工具子集摘要
    coder_role = next(
        role for role in initial_policy.available_roles if role.role_id == "coder"
    )
    selected_tool_ids = coder_role.tool_ids[:2]

    session_manager.update_session_expert_policy(
        session_id="session-execution-role-summary",
        user_id="local_default",
        enabled_expert_role_ids=["coder"],
        expert_role_tool_ids={"coder": selected_tool_ids},
    )

    role_summary_map = sessions_execution_module._build_session_role_summary_map(
        user_id="local_default",
        session_id="session-execution-role-summary",
    )

    assert role_summary_map["coder"]["tool_ids"] == selected_tool_ids
    assert role_summary_map["coder"]["tool_names"] == [
        "ReadMediaFile",
        "ListSessionNotebooks",
    ]
    assert role_summary_map["coder"]["tool_count"] == 2
