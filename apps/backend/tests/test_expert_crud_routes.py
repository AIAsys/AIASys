"""测试专家 CRUD REST API。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes import workspaces_core as workspaces_core_module
from app.models.expert import CreateExpertRequest, UpdateExpertRequest
from app.models.user import UserInfo
from app.services import expert_roles as expert_roles_module
from app.services.agent import subagent_catalog
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user(user_id: str = "local_default") -> UserInfo:
    return UserInfo(user_id=user_id, role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


@pytest.mark.asyncio
async def test_create_workspace_expert_success(
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

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-crud",
        title="CRUD 测试工作区",

        initial_conversation_title="测试会话",
    )

    response = await workspaces_core_module.create_workspace_expert(
        "task-crud",
        CreateExpertRequest(
            name="custom_analyst",
            description="自定义数据分析专家",
            system_prompt="你是一个专业的数据分析专家。",
            model="kimi-k2",
            tools=["python", "shell"],
            scope="workspace",
        ),
        current_user=_build_user(),
    )

    assert response.name == "custom_analyst"
    assert response.description == "自定义数据分析专家"
    assert response.system_prompt == "你是一个专业的数据分析专家。"
    assert response.model == "kimi-k2"
    assert response.tools == ["python", "shell"]
    assert response.scope == "workspace"


@pytest.mark.asyncio
async def test_get_workspace_expert_detail(
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

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-detail",
        title="详情测试工作区",

    )

    await workspaces_core_module.create_workspace_expert(
        "task-detail",
        CreateExpertRequest(
            name="detail_test",
            description="详情测试",
            system_prompt="测试 system prompt",
        ),
        current_user=_build_user(),
    )

    detail = await workspaces_core_module.get_workspace_expert_detail(
        "task-detail",
        "detail_test",
        current_user=_build_user(),
    )

    assert detail.name == "detail_test"
    assert detail.system_prompt == "测试 system prompt"


@pytest.mark.asyncio
async def test_update_workspace_expert(
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

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-update",
        title="更新测试工作区",

    )

    await workspaces_core_module.create_workspace_expert(
        "task-update",
        CreateExpertRequest(
            name="update_test",
            description="原始描述",
            system_prompt="原始 prompt",
            model="model-a",
        ),
        current_user=_build_user(),
    )

    updated = await workspaces_core_module.update_workspace_expert(
        "task-update",
        "update_test",
        UpdateExpertRequest(
            description="更新后的描述",
            system_prompt="更新后的 prompt",
            model="model-b",
            tools=["file_write"],
        ),
        current_user=_build_user(),
    )

    assert updated.description == "更新后的描述"
    assert updated.system_prompt == "更新后的 prompt"
    assert updated.model == "model-b"
    assert updated.tools == ["file_write"]


@pytest.mark.asyncio
async def test_delete_workspace_expert(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )
    monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-delete",
        title="删除测试工作区",

    )

    await workspaces_core_module.create_workspace_expert(
        "task-delete",
        CreateExpertRequest(
            name="delete_test",
            description="待删除",
            system_prompt="prompt",
        ),
        current_user=_build_user(),
    )

    result = await workspaces_core_module.delete_workspace_expert(
        "task-delete",
        "delete_test",
        current_user=_build_user(),
    )
    assert result["success"] is True
    assert result["name"] == "delete_test"

    # 确认已删除
    with pytest.raises(HTTPException) as exc_info:
        await workspaces_core_module.get_workspace_expert_detail(
            "task-delete",
            "delete_test",
            current_user=_build_user(),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_workspace_expert_rejects_invalid_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-invalid",
        title="非法名称测试",

    )

    with pytest.raises(HTTPException) as exc_info:
        await workspaces_core_module.create_workspace_expert(
            "task-invalid",
            CreateExpertRequest(
                name="123_invalid",
                description="描述",
                system_prompt="prompt",
            ),
            current_user=_build_user(),
        )
    assert exc_info.value.status_code == 400
    assert "格式无效" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_create_workspace_expert_rejects_system_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-system",
        title="系统预设冲突测试",

    )

    with pytest.raises(HTTPException) as exc_info:
        await workspaces_core_module.create_workspace_expert(
            "task-system",
            CreateExpertRequest(
                name="coder",
                description="描述",
                system_prompt="prompt",
            ),
            current_user=_build_user(),
    )
    assert exc_info.value.status_code == 400
    assert exc_info.value.detail


@pytest.mark.asyncio
async def test_cannot_modify_system_preset_via_rest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-preset",
        title="系统预设保护测试",

    )

    # 尝试修改系统预设 coder
    with pytest.raises(HTTPException) as exc_info:
        await workspaces_core_module.update_workspace_expert(
            "task-preset",
            "coder",
            UpdateExpertRequest(description=" hacked"),
            current_user=_build_user(),
        )
    assert exc_info.value.status_code == 403
    assert "系统预设" in str(exc_info.value.detail)

    subagent_catalog.enable_builtin_subagent_to_scope(
        user_id="local_default",
        name="coder",
        scope="workspace",
        workspace_id="task-preset",
    )
    delete_response = await workspaces_core_module.delete_workspace_expert(
        "task-preset",
        "coder",
        current_user=_build_user(),
    )
    assert delete_response == {"success": True, "name": "coder"}
    assert subagent_catalog.is_system_subagent_name("coder") is True
    assert subagent_catalog.is_subagent_installed_to_scope(
        user_id="local_default",
        name="coder",
        scope="workspace",
        workspace_id="task-preset",
    ) is False
