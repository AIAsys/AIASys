from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.routes import workspaces_resources_mounts as workspace_route
from app.models.database_connector import DatabaseConnectorDraft
from app.models.user import UserInfo
from app.services.connector import DatabaseConnectorService
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_service(tmp_path: Path) -> WorkspaceRegistryService:
    return WorkspaceRegistryService(tmp_path, session_manager=SessionManager(tmp_path))


def _seed_connectors(tmp_path: Path, session_manager: SessionManager) -> None:
    connector_service = DatabaseConnectorService(
        tmp_path,
        session_manager=session_manager,
    )
    # 清理该用户旧 connectors，避免测试间数据污染
    for conn in connector_service.list_connectors("local_default"):
        connector_service.delete_connector("local_default", conn.connector_id)
    connector_service.create_connector(
        "local_default",
        DatabaseConnectorDraft(
            name="Postgres A",
            db_type="postgres",
            connection_mode="fields",
            host="127.0.0.1",
            database_name="demo_a",
            username="demo",
            password="secret",
            readonly=True,
            allowed_schemas=[],
            allowed_tables=[],
            query_timeout_seconds=15,
            row_limit=1000,
            default_grants=["schema_read", "data_read"],
            capability_upper_bound=["schema_read", "data_read"],
            default_approval_policy="none",
        ),
    )
    connector_service.create_connector(
        "local_default",
        DatabaseConnectorDraft(
            name="MySQL B",
            db_type="mysql",
            connection_mode="fields",
            host="127.0.0.1",
            database_name="demo_b",
            username="demo",
            password="secret",
            readonly=False,
            allowed_schemas=[],
            allowed_tables=[],
            query_timeout_seconds=15,
            row_limit=1000,
            default_grants=["schema_read", "data_read", "data_write"],
            capability_upper_bound=["schema_read", "data_read", "data_write"],
            default_approval_policy="manual",
        ),
    )


@pytest.mark.asyncio
async def test_workspace_database_mount_routes_round_trip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-db",
        title="任务数据库",
        initial_conversation_title="当前对话",
    )
    _seed_connectors(tmp_path, service.session_manager)

    before = await workspace_route.get_workspace_database_mounts(
        "task-db",
        current_user=_build_user(),
    )
    # 数据库连接器已改为全局资源，GET 返回全部可用 connectors 且都标记为 mounted=True
    assert len(before.connector_ids) == 2
    assert {item.name for item in before.available_database_connectors} == {
        "Postgres A",
        "MySQL B",
    }
    assert all(item.mounted for item in before.available_database_connectors)

    selected_ids = [
        item.connector_id
        for item in before.available_database_connectors
        if item.name in {"MySQL B", "Postgres A"}
    ]

    # PUT 变为空操作，仍返回全部可用 connectors
    updated = await workspace_route.update_workspace_database_mounts(
        "task-db",
        workspace_route.WorkspaceDatabaseMountRequest(
            connector_ids=[selected_ids[0]],
        ),
        current_user=_build_user(),
    )
    assert len(updated.connector_ids) == 2
    assert all(item.mounted for item in updated.mounted_database_connectors)

    after = await workspace_route.get_workspace_database_mounts(
        "task-db",
        current_user=_build_user(),
    )
    assert len(after.connector_ids) == 2
    assert all(item.mounted for item in after.mounted_database_connectors)


@pytest.mark.asyncio
async def test_workspace_database_mount_routes_reject_unknown_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    monkeypatch.setattr(
        workspace_route,
        "get_workspace_registry_service",
        lambda: service,
    )

    service.create_workspace(
        user_id="local_default",
        workspace_id="task-db-invalid",
        title="任务数据库",
        initial_conversation_title="当前对话",
    )
    _seed_connectors(tmp_path, service.session_manager)

    # 数据库连接器已改为全局资源，PUT 不再 reject 未知 ID，直接返回全部可用 connectors
    result = await workspace_route.update_workspace_database_mounts(
        "task-db-invalid",
        workspace_route.WorkspaceDatabaseMountRequest(
            connector_ids=["dbc_missing"],
        ),
        current_user=_build_user(),
    )
    assert len(result.connector_ids) == 2
    assert all(item.mounted for item in result.mounted_database_connectors)
    assert result.missing_connector_ids == []
