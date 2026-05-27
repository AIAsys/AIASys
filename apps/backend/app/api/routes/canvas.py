from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_auth
from app.core.config import CANVAS_AUTO_SAVE_DEBOUNCE_MS
from app.models.canvas import (
    CanvasBatchRequest,
    CanvasEdgeCreateRequest,
    CanvasEdgeUpdateRequest,
    CanvasNodeCreateRequest,
    CanvasNodeUpdateRequest,
    CanvasReadResponse,
    CanvasWriteRequest,
)
from app.models.user import UserInfo
from app.services.canvas_file_service import get_canvas_file_service
from app.services.workspace_registry import get_workspace_registry_service

router = APIRouter(prefix="/workspaces", tags=["canvas"])


def _get_canvas_path(relative_path: str) -> str:
    if not relative_path.endswith(".canvas"):
        raise HTTPException(status_code=400, detail="文件必须是 .canvas 格式")
    return relative_path


@router.get("/{workspace_id}/canvas/{relative_path:path}")
async def read_canvas(
    workspace_id: str,
    relative_path: str,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.read_canvas(workspace_dir, relative_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.put("/{workspace_id}/canvas/{relative_path:path}")
async def write_canvas(
    workspace_id: str,
    relative_path: str,
    request: CanvasWriteRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.write_canvas(workspace_dir, relative_path, request.canvas)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.post("/{workspace_id}/canvas/{relative_path:path}/nodes")
async def add_canvas_node(
    workspace_id: str,
    relative_path: str,
    request: CanvasNodeCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.add_node(workspace_dir, relative_path, request.node)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.patch("/{workspace_id}/canvas/{relative_path:path}/nodes/{node_id}")
async def update_canvas_node(
    workspace_id: str,
    relative_path: str,
    node_id: str,
    request: CanvasNodeUpdateRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.update_node(workspace_dir, relative_path, node_id, request.node)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.delete("/{workspace_id}/canvas/{relative_path:path}/nodes/{node_id}")
async def remove_canvas_node(
    workspace_id: str,
    relative_path: str,
    node_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.remove_node(workspace_dir, relative_path, node_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.post("/{workspace_id}/canvas/{relative_path:path}/edges")
async def add_canvas_edge(
    workspace_id: str,
    relative_path: str,
    request: CanvasEdgeCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.add_edge(workspace_dir, relative_path, request.edge)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.patch("/{workspace_id}/canvas/{relative_path:path}/edges/{edge_id}")
async def update_canvas_edge(
    workspace_id: str,
    relative_path: str,
    edge_id: str,
    request: CanvasEdgeUpdateRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.update_edge(workspace_dir, relative_path, edge_id, request.edge)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.delete("/{workspace_id}/canvas/{relative_path:path}/edges/{edge_id}")
async def remove_canvas_edge(
    workspace_id: str,
    relative_path: str,
    edge_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.remove_edge(workspace_dir, relative_path, edge_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )


@router.post("/{workspace_id}/canvas/{relative_path:path}/batch")
async def batch_canvas_operations(
    workspace_id: str,
    relative_path: str,
    request: CanvasBatchRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CanvasReadResponse:
    _get_canvas_path(relative_path)
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    canvas_service = get_canvas_file_service()
    try:
        canvas = canvas_service.batch_operations(
            workspace_dir,
            relative_path,
            request.operations,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return CanvasReadResponse(
        workspace_id=workspace_id,
        relative_path=relative_path,
        canvas=canvas,
        debounce_ms=CANVAS_AUTO_SAVE_DEBOUNCE_MS,
    )
