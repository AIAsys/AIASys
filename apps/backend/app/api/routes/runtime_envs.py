"""工作区运行环境登记 API。"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Query

logger = logging.getLogger(__name__)

from app.core.auth import require_auth
from app.models.runtime_environment import (
    BindWorkspaceRuntimeEnvRequest,
    EnsureWorkspaceNodeEnvRequest,
    EnsureWorkspaceUvEnvRequest,
    InstallNodeVersionRequest,
    InstallWorkspacePackagesRequest,
    NodeRuntimeActionResponse,
    NodeRuntimeEnvActionResponse,
    NodeRuntimeEnvRegistryResponse,
    RegisterWorkspacePythonEnvRequest,
    RuntimeEnvActionResponse,
    SetDefaultNodeVersionRequest,
    UninstallNodeVersionRequest,
    UseNodeVersionRequest,
    WorkspaceRuntimeEnvInspectionResponse,
    WorkspaceRuntimeEnvRegistryResponse,
)
from app.models.user import UserInfo
from app.services.node_runtime import (
    NodeRuntimeService,
    get_node_runtime_service,
)
from app.services.runtime_environment import (
    RuntimeEnvironmentService,
    get_runtime_environment_service,
    resolve_workspace_runtime_dir,
)

router = APIRouter(
    prefix="/workspaces/{workspace_id}/runtime-environments",
    tags=["runtime-environments"],
)


def _service() -> RuntimeEnvironmentService:
    return get_runtime_environment_service()


def _raise_runtime_error(exc: RuntimeError) -> None:
    detail = str(exc) or "运行环境操作失败"
    status_code = 503 if "不可用" in detail else 400
    raise HTTPException(status_code=status_code, detail=detail) from exc


def _node_service() -> NodeRuntimeService:
    return get_node_runtime_service()


# 跟踪后台 uv sync 任务，避免重复触发。
# key: "{user_id}:{workspace_id}:{env_id}"
_uv_sync_tasks: dict[str, asyncio.Task] = {}


def _uv_sync_task_key(user_id: str, workspace_id: str, env_id: str) -> str:
    return f"{user_id}:{workspace_id}:{env_id}"


async def _background_uv_sync(
    service: RuntimeEnvironmentService,
    user_id: str,
    workspace_id: str,
    env_id: str,
) -> None:
    """后台执行 uv sync，避免阻塞 HTTP 请求。"""
    key = _uv_sync_task_key(user_id, workspace_id, env_id)
    try:
        await asyncio.to_thread(
            service.sync_uv_env,
            user_id,
            workspace_id,
            env_id=env_id,
        )
    except Exception:
        logger.exception("后台 uv sync 失败: %s", key)
    finally:
        _uv_sync_tasks.pop(key, None)


@router.get(
    "",
    response_model=WorkspaceRuntimeEnvRegistryResponse,
)
async def list_workspace_runtime_envs(
    workspace_id: str,
    inspect: bool = Query(True, description="是否刷新环境状态"),
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前工作区登记的 UV 运行环境。"""
    try:
        # inspect 时会调用 python -m pip list，可能耗时数秒，放到线程池避免阻塞事件循环
        return await asyncio.to_thread(
            _service().list_workspace_envs,
            current_user.user_id,
            workspace_id,
            inspect=inspect,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/uv",
    response_model=RuntimeEnvActionResponse,
)
async def ensure_workspace_uv_env(
    workspace_id: str,
    request: EnsureWorkspaceUvEnvRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """创建或刷新工作区默认 UV 环境登记。

    如果请求包含 sync/create_venv，会立即返回 status=syncing，并在后台执行 uv sync，
    避免首次环境准备耗时过长导致 HTTP 502/超时。
    """
    service = _service()
    user_id = current_user.user_id
    env_id = request.env_id
    try:
        needs_sync = request.create_venv or request.sync
        if needs_sync:
            # 先快速创建 pyproject/registry 并标记为 syncing，立即响应前端
            env = await asyncio.to_thread(
                service.prepare_uv_env,
                user_id,
                workspace_id,
                env_id=env_id,
                display_name=request.display_name,
                python_version=request.python_version,
                packages=request.packages,
            )

            key = _uv_sync_task_key(user_id, workspace_id, env_id)
            existing_task = _uv_sync_tasks.get(key)
            if existing_task is None or existing_task.done():
                task = asyncio.create_task(
                    _background_uv_sync(service, user_id, workspace_id, env_id)
                )
                _uv_sync_tasks[key] = task
            return RuntimeEnvActionResponse(
                workspace_id=workspace_id,
                env=env,
                command_result=None,
            )

        env, command_result = await asyncio.to_thread(
            service.ensure_uv_env,
            user_id,
            workspace_id,
            env_id=env_id,
            display_name=request.display_name,
            python_version=request.python_version,
            packages=request.packages,
            create_venv=False,
            sync=False,
        )
        return RuntimeEnvActionResponse(
            workspace_id=workspace_id,
            env=env,
            command_result=command_result,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/registered-python",
    response_model=RuntimeEnvActionResponse,
)
async def register_workspace_python_env(
    workspace_id: str,
    request: RegisterWorkspacePythonEnvRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """把已登记或本机可用 Python 解释器登记到当前工作区。"""
    try:
        env = await asyncio.to_thread(
            _service().register_python_env,
            current_user.user_id,
            workspace_id,
            python_executable=request.python_executable,
            env_id=request.env_id,
            display_name=request.display_name,
            source_kernel_name=request.source_kernel_name,
        )
        refresh_required = False
        if request.activate:
            env = await asyncio.to_thread(
                _service().bind_workspace_env,
                current_user.user_id,
                workspace_id,
                env.env_id,
            )
            refresh_required = True
        return RuntimeEnvActionResponse(
            workspace_id=workspace_id,
            env=env,
            refresh_required=refresh_required,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/{env_id}/packages",
    response_model=RuntimeEnvActionResponse,
)
async def install_workspace_uv_packages(
    workspace_id: str,
    env_id: str,
    request: InstallWorkspacePackagesRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """向工作区 UV 环境登记依赖包。"""
    try:
        env, command_result = await asyncio.to_thread(
            _service().install_workspace_packages,
            current_user.user_id,
            workspace_id,
            env_id=env_id,
            packages=request.packages,
            sync=request.sync,
        )
        return RuntimeEnvActionResponse(
            workspace_id=workspace_id,
            env=env,
            command_result=command_result,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/active",
    response_model=RuntimeEnvActionResponse,
)
async def bind_workspace_runtime_env(
    workspace_id: str,
    request: BindWorkspaceRuntimeEnvRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """把登记环境设为工作区默认执行环境。"""
    try:
        env = await asyncio.to_thread(
            _service().bind_workspace_env,
            current_user.user_id,
            workspace_id,
            request.env_id,
        )
        return RuntimeEnvActionResponse(
            workspace_id=workspace_id,
            env=env,
            refresh_required=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


# ── Node.js / fnm 端点 ──


@router.get(
    "/node",
    response_model=NodeRuntimeEnvRegistryResponse,
)
async def list_workspace_node_envs(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前工作区登记的 Node.js/fnm 运行环境。"""
    try:
        return _node_service().list_node_envs(
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
    "/node",
    response_model=NodeRuntimeEnvActionResponse,
)
async def ensure_workspace_node_env(
    workspace_id: str,
    request: EnsureWorkspaceNodeEnvRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """创建或刷新工作区 Node.js/fnm 环境。"""
    try:
        env, command_result = _node_service().ensure_node_env(
            current_user.user_id,
            workspace_id,
            env_id=request.env_id,
            display_name=request.display_name,
            node_version=request.node_version,
            npm_packages=request.npm_packages,
        )
        refresh_required = False
        if request.activate:
            env = _node_service().bind_node_env(
                current_user.user_id,
                workspace_id,
                env.env_id,
            )
            refresh_required = True
        return NodeRuntimeEnvActionResponse(
            workspace_id=workspace_id,
            env=env,
            refresh_required=refresh_required,
            command_result=command_result,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/node/install",
    response_model=NodeRuntimeActionResponse,
)
async def install_node_version(
    workspace_id: str,
    request: InstallNodeVersionRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """通过 fnm 安装指定 Node.js 版本。"""
    try:
        result = _node_service().install_node_version(
            current_user.user_id, workspace_id, version=request.node_version
        )
        return NodeRuntimeActionResponse(workspace_id=workspace_id, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/node/use",
    response_model=NodeRuntimeActionResponse,
)
async def use_node_version(
    workspace_id: str,
    request: UseNodeVersionRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在工作区切换到指定 Node.js 版本。"""
    try:
        result = _node_service().use_node_version(
            current_user.user_id, workspace_id, request.env_id, request.node_version
        )
        return NodeRuntimeActionResponse(workspace_id=workspace_id, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/node/default",
    response_model=NodeRuntimeActionResponse,
)
async def set_default_node_version(
    workspace_id: str,
    request: SetDefaultNodeVersionRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """设置全局默认 Node.js 版本。"""
    try:
        result = _node_service().set_default_node_version(
            current_user.user_id, workspace_id, request.node_version
        )
        return NodeRuntimeActionResponse(workspace_id=workspace_id, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.get(
    "/node/current",
    response_model=NodeRuntimeActionResponse,
)
async def get_current_node_version(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """查看当前激活的 Node.js 版本。"""
    try:
        result = _node_service().get_current_node_version(current_user.user_id, workspace_id)
        return NodeRuntimeActionResponse(workspace_id=workspace_id, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.post(
    "/node/uninstall",
    response_model=NodeRuntimeActionResponse,
)
async def uninstall_node_version(
    workspace_id: str,
    request: UninstallNodeVersionRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """卸载指定 Node.js 版本。"""
    try:
        result = _node_service().uninstall_node_version(
            current_user.user_id, workspace_id, request.node_version
        )
        return NodeRuntimeActionResponse(workspace_id=workspace_id, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.get(
    "/node/remote",
    response_model=NodeRuntimeActionResponse,
)
async def list_remote_node_versions(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """查看可远程安装的 Node.js 版本列表。"""
    try:
        result = _node_service().list_remote_versions(current_user.user_id, workspace_id)
        return NodeRuntimeActionResponse(workspace_id=workspace_id, result=result)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.get(
    "/{env_id}",
    response_model=WorkspaceRuntimeEnvInspectionResponse,
)
async def inspect_workspace_runtime_env(
    workspace_id: str,
    env_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """查看单个登记环境的当前状态和材料文件。"""
    service = _service()
    try:
        # inspect_env 会执行 python -m pip list，放到线程池避免阻塞
        env = await asyncio.to_thread(
            service.inspect_env, current_user.user_id, workspace_id, env_id
        )
        workspace_dir = await asyncio.to_thread(
            service.workspace_registry.get_workspace_root,
            current_user.user_id,
            workspace_id,
        )
        registry_path = service._registry_path(workspace_dir)
        env_dir = resolve_workspace_runtime_dir(workspace_dir)
        return WorkspaceRuntimeEnvInspectionResponse(
            workspace_id=workspace_id,
            env=env,
            registry_path=str(registry_path),
            material_files={
                "pyproject.toml": (env_dir / "pyproject.toml").exists(),
                "uv.lock": (env_dir / "uv.lock").exists(),
                ".python-version": (env_dir / ".python-version").exists(),
                ".venv": (env_dir / ".venv").exists(),
            },
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)


@router.delete(
    "/{env_id}",
    response_model=RuntimeEnvActionResponse,
)
async def unregister_workspace_runtime_env(
    workspace_id: str,
    env_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """从当前工作区取消运行环境登记。"""
    try:
        env = await asyncio.to_thread(
            _service().unregister_workspace_env,
            current_user.user_id,
            workspace_id,
            env_id,
        )
        return RuntimeEnvActionResponse(
            workspace_id=workspace_id,
            env=env,
            refresh_required=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        _raise_runtime_error(exc)
