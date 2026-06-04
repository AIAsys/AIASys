from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.models.workspace import (
    WorkspaceDatabaseMountRequest,
    WorkspaceDatabaseMountResponse,
    WorkspaceKnowledgeBaseMountRequest,
    WorkspaceKnowledgeBaseMountResponse,
)
from app.services.workspace_registry import get_workspace_registry_service

router = APIRouter()


@router.get(
    "/{workspace_id}/database-connectors",
    response_model=WorkspaceDatabaseMountResponse,
)
async def get_workspace_database_mounts(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.api.routes.workspaces_resource_utils import (
        _build_workspace_database_mount_response,
    )
    from app.services.connector import DatabaseConnectorService

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    connector_service = DatabaseConnectorService(
        service.base_dir,
        session_manager=service.session_manager,
    )
    available_connectors = connector_service.list_connectors(
        current_user.user_id, workspace_id=workspace_id
    )
    all_connector_ids = [
        str(getattr(conn, "connector_id", ""))
        for conn in available_connectors
        if getattr(conn, "connector_id", None)
    ]
    return _build_workspace_database_mount_response(
        workspace_id=workspace_id,
        mounted_ids=all_connector_ids,
        available_connectors=available_connectors,
    )


@router.put(
    "/{workspace_id}/database-connectors",
    response_model=WorkspaceDatabaseMountResponse,
)
async def update_workspace_database_mounts(
    workspace_id: str,
    request: WorkspaceDatabaseMountRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.api.routes.workspaces_resource_utils import (
        _build_workspace_database_mount_response,
    )
    from app.services.connector import DatabaseConnectorService

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    connector_service = DatabaseConnectorService(
        service.base_dir,
        session_manager=service.session_manager,
    )
    available_connectors = connector_service.list_connectors(
        current_user.user_id, workspace_id=workspace_id
    )
    all_connector_ids = [
        str(getattr(conn, "connector_id", ""))
        for conn in available_connectors
        if getattr(conn, "connector_id", None)
    ]
    return _build_workspace_database_mount_response(
        workspace_id=workspace_id,
        mounted_ids=all_connector_ids,
        available_connectors=available_connectors,
    )


@router.get(
    "/{workspace_id}/knowledge-bases",
    response_model=WorkspaceKnowledgeBaseMountResponse,
)
async def get_workspace_knowledge_base_mounts(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.api.routes.workspaces_resource_utils import (
        _build_workspace_knowledge_base_mount_response,
    )
    from app.knowledge import get_sqlite_kb_service

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    # 知识库已取消挂载，返回全部可用知识库且都标记为 mounted=True
    kb_service = get_sqlite_kb_service()
    visible_knowledge_bases = kb_service.list_knowledge_bases(current_user.user_id)
    all_kb_ids = [str(kb.id) for kb in visible_knowledge_bases if getattr(kb, "id", None)]
    return _build_workspace_knowledge_base_mount_response(
        workspace_id=workspace_id,
        mounted_ids=all_kb_ids,
        visible_knowledge_bases=visible_knowledge_bases,
    )


@router.put(
    "/{workspace_id}/knowledge-bases",
    response_model=WorkspaceKnowledgeBaseMountResponse,
)
async def update_workspace_knowledge_base_mounts(
    workspace_id: str,
    request: WorkspaceKnowledgeBaseMountRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    from app.api.routes.workspaces_resource_utils import (
        _build_workspace_knowledge_base_mount_response,
    )
    from app.knowledge import get_sqlite_kb_service

    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    # 知识库已取消挂载，PUT 变为空操作，直接返回全部可用知识库
    kb_service = get_sqlite_kb_service()
    visible_knowledge_bases = kb_service.list_knowledge_bases(current_user.user_id)
    all_kb_ids = [str(kb.id) for kb in visible_knowledge_bases if getattr(kb, "id", None)]
    return _build_workspace_knowledge_base_mount_response(
        workspace_id=workspace_id,
        mounted_ids=all_kb_ids,
        visible_knowledge_bases=visible_knowledge_bases,
    )
