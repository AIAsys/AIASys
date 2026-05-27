from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes import capabilities as capabilities_route
from app.capabilities.models import (
    CapabilityKind,
    CapabilityManifest,
    CapabilityStatus,
    HealthStatus,
    WorkspaceCapability,
)
from app.models.user import UserInfo
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


@pytest.mark.asyncio
async def test_list_workspace_capabilities_does_not_create_missing_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        capabilities_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await capabilities_route.list_workspace_capabilities(
            "missing-workspace",
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 404
    assert not (tmp_path / "local_default" / "missing-workspace").exists()


@pytest.mark.asyncio
async def test_install_capability_rejects_missing_workspace_without_creating_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        capabilities_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    with pytest.raises(HTTPException) as exc_info:
        await capabilities_route.install_capability_to_workspace(
            "missing-workspace",
            capabilities_route.CapabilityActionRequest(capability_id="demo-skill"),
            current_user=_build_user(),
        )

    assert exc_info.value.status_code == 404
    assert not (tmp_path / "local_default" / "missing-workspace").exists()


@pytest.mark.asyncio
async def test_list_workspace_capabilities_only_returns_error_message_for_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_path = tmp_path / "workspace"
    workspace_path.mkdir()

    declarations = {
        "healthy-skill": WorkspaceCapability(
            capability_id="healthy-skill",
            kind=CapabilityKind.SKILL_PACK,
            enabled=True,
        ),
        "disabled-agent": WorkspaceCapability(
            capability_id="disabled-agent",
            kind=CapabilityKind.SUBAGENT,
            enabled=False,
        ),
        "broken-skill": WorkspaceCapability(
            capability_id="broken-skill",
            kind=CapabilityKind.SKILL_PACK,
            enabled=True,
        ),
    }

    manifests = {
        cap_id: CapabilityManifest(
            capability_id=cap_id,
            kind=declaration.kind,
            display_name=cap_id,
        )
        for cap_id, declaration in declarations.items()
    }

    health = {
        "healthy-skill": HealthStatus(
            status=CapabilityStatus.ACTIVE,
            detail="正常",
        ),
        "disabled-agent": HealthStatus(
            status=CapabilityStatus.DISABLED,
            detail="已禁用",
        ),
        "broken-skill": HealthStatus(
            status=CapabilityStatus.ERROR,
            detail="缺少 SKILL.md",
        ),
    }

    class FakeManager:
        def _read_declarations(self, _workspace_path: Path):
            return declarations

        def get_manifest(self, cap_id: str):
            return manifests[cap_id]

        def verify(self, cap_id: str, _workspace_path: Path):
            return health[cap_id]

    monkeypatch.setattr(
        capabilities_route,
        "_get_workspace_path",
        lambda _user_id, _workspace_id: workspace_path,
    )
    monkeypatch.setattr(
        capabilities_route,
        "get_capability_manager",
        lambda: FakeManager(),
    )

    response = await capabilities_route.list_workspace_capabilities(
        "workspace",
        current_user=_build_user(),
    )

    items = {item.capability_id: item for item in response.capabilities}
    assert items["healthy-skill"].error_message == ""
    assert items["disabled-agent"].error_message == ""
    assert items["broken-skill"].error_message == "缺少 SKILL.md"
