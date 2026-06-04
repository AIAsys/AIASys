"""工作区容器资源 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_auth
from app.models.container_resource import (
    ContainerLogsResponse,
    ContainerResourceActionResponse,
    RegisterContainerRequest,
    WorkspaceContainerResourceRegistry,
)
from app.models.user import UserInfo
from app.services.container_resource import (
    ContainerResourceService,
    get_container_resource_service,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/container-resources",
    tags=["container-resources"],
)


def _service() -> ContainerResourceService:
    return get_container_resource_service()


def _raise_runtime_error(exc: RuntimeError) -> None:
    detail = str(exc) or "容器资源操作失败"
    status_code = 503 if "不可用" in detail else 400
    raise HTTPException(status_code=status_code, detail=detail) from exc


@router.get(
    "",
    response_model=WorkspaceContainerResourceRegistry,
)
async def list_workspace_container_resources(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前工作区登记的容器资源。"""
    try:
        return _service().list_workspace_containers(
            current_user.user_id,
            workspace_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "",
    response_model=ContainerResourceActionResponse,
)
async def register_workspace_container_resource(
    workspace_id: str,
    request: RegisterContainerRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """登记或创建当前工作区的容器资源。"""
    try:
        container = _service().register_container(
            current_user.user_id,
            workspace_id,
            container_id=request.container_id,
            name=request.name,
            image=request.image,
            container_id_or_name=request.container_id_or_name,
            workspace_mount_path=request.workspace_mount_path,
            create_container=request.create_container,
            auto_start=request.auto_start,
            command=request.command,
            env=request.env,
            labels=request.labels,
            ports=request.ports,
        )
        return ContainerResourceActionResponse(
            workspace_id=workspace_id,
            container=container,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.get(
    "/{container_id}",
    response_model=ContainerResourceActionResponse,
)
async def inspect_workspace_container_resource(
    workspace_id: str,
    container_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """查看单个容器资源的当前状态。"""
    try:
        container = _service().inspect_container(
            current_user.user_id,
            workspace_id,
            container_id,
        )
        return ContainerResourceActionResponse(
            workspace_id=workspace_id,
            container=container,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/{container_id}/start",
    response_model=ContainerResourceActionResponse,
)
async def start_workspace_container_resource(
    workspace_id: str,
    container_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """启动指定容器资源。"""
    try:
        container = _service().start_container(
            current_user.user_id,
            workspace_id,
            container_id,
        )
        return ContainerResourceActionResponse(
            workspace_id=workspace_id,
            container=container,
            refresh_required=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/{container_id}/stop",
    response_model=ContainerResourceActionResponse,
)
async def stop_workspace_container_resource(
    workspace_id: str,
    container_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """停止指定容器资源。"""
    try:
        container = _service().stop_container(
            current_user.user_id,
            workspace_id,
            container_id,
        )
        return ContainerResourceActionResponse(
            workspace_id=workspace_id,
            container=container,
            refresh_required=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.delete(
    "/{container_id}",
    response_model=ContainerResourceActionResponse,
)
async def unregister_workspace_container_resource(
    workspace_id: str,
    container_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """从当前工作区取消容器资源登记。"""
    try:
        container = _service().unregister_container(
            current_user.user_id,
            workspace_id,
            container_id,
        )
        return ContainerResourceActionResponse(
            workspace_id=workspace_id,
            container=container,
            refresh_required=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.get(
    "/{container_id}/logs",
    response_model=ContainerLogsResponse,
)
async def get_workspace_container_resource_logs(
    workspace_id: str,
    container_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取指定容器资源的日志。"""
    try:
        logs = _service().get_container_logs(
            current_user.user_id,
            workspace_id,
            container_id,
        )
        return ContainerLogsResponse(
            container_id=container_id,
            logs=logs,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)
