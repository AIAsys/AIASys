"""工作区运行环境登记 API。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.models.runtime_environment import (
    BindWorkspaceRuntimeEnvRequest,
    EnsureWorkspaceUvEnvRequest,
    InstallWorkspacePackagesRequest,
    RegisterWorkspacePythonEnvRequest,
    RuntimeEnvActionResponse,
    WorkspaceRuntimeEnvInspectionResponse,
    WorkspaceRuntimeEnvRegistryResponse,
)
from app.models.user import UserInfo
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
        return _service().list_workspace_envs(
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
    """创建或刷新工作区默认 UV 环境登记。"""
    try:
        env, command_result = _service().ensure_uv_env(
            current_user.user_id,
            workspace_id,
            env_id=request.env_id,
            display_name=request.display_name,
            python_version=request.python_version,
            packages=request.packages,
            create_venv=request.create_venv,
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
        env = _service().register_python_env(
            current_user.user_id,
            workspace_id,
            python_executable=request.python_executable,
            env_id=request.env_id,
            display_name=request.display_name,
            source_kernel_name=request.source_kernel_name,
        )
        refresh_required = False
        if request.activate:
            env = _service().bind_workspace_env(
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
        env, command_result = _service().install_workspace_packages(
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
        env = _service().bind_workspace_env(
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
        env = service.inspect_env(current_user.user_id, workspace_id, env_id)
        workspace_dir = service.workspace_registry.get_workspace_root(
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
        env = _service().unregister_workspace_env(
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
