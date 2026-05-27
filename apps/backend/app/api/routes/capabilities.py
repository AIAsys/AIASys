"""统一能力层 API 路由。

提供能力发现、安装、卸载、激活、禁用、验活接口。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.capabilities import CapabilityManifest, get_capability_manager
from app.core.auth import require_auth
from app.core.config import get_user_global_workspace_dir
from app.models.user import UserInfo
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/capabilities", tags=["capabilities"])


# ---- 请求/响应模型 ----


class CapabilityItemResponse(BaseModel):
    capability_id: str
    kind: str
    display_name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    dependencies: list[str] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    source: str = ""  # builtin / store
    tool_names: list[str] = Field(default_factory=list)


class WorkspaceCapabilityItemResponse(BaseModel):
    capability_id: str
    kind: str
    display_name: str = ""
    description: str = ""
    version: str = ""
    enabled: bool = False
    source: str = ""
    status: str = "unknown"  # active / error / disabled / installed
    error_message: str = ""


class AvailableCapabilitiesResponse(BaseModel):
    capabilities: list[CapabilityItemResponse]
    total: int


class WorkspaceCapabilitiesResponse(BaseModel):
    workspace_id: str
    capabilities: list[WorkspaceCapabilityItemResponse]
    total: int


class CapabilityActionRequest(BaseModel):
    capability_id: str
    config: dict[str, Any] | None = Field(default=None, description="安装时的配置参数")


class CapabilityActionResponse(BaseModel):
    success: bool
    capability_id: str
    message: str = ""


class VerifyCapabilityResponse(BaseModel):
    capability_id: str
    status: str
    detail: str = ""
    ok: bool = False


class CapabilitySourceResponse(BaseModel):
    capability_id: str
    file: str
    content: str


class CapabilitySourceTreeEntry(BaseModel):
    path: str
    name: str
    is_dir: bool


class CapabilitySourceTreeResponse(BaseModel):
    capability_id: str
    entries: list[CapabilitySourceTreeEntry]


# ---- 工具函数 ----


def _get_workspace_path(user_id: str, workspace_id: str) -> Path:
    try:
        return get_workspace_registry_service().get_workspace_root(
            user_id,
            workspace_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="无效的 workspace_id") from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"工作区不存在: {workspace_id}") from exc


def _get_global_workspace_path(user_id: str) -> Path:
    path = get_user_global_workspace_dir(user_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _manifest_to_response(manifest: CapabilityManifest, source: str) -> CapabilityItemResponse:
    return CapabilityItemResponse(
        capability_id=manifest.capability_id,
        kind=manifest.kind.value,
        display_name=manifest.display_name,
        description=manifest.description,
        version=manifest.version,
        author=manifest.author,
        dependencies=manifest.dependencies,
        config_schema=manifest.config_schema,
        source=source,
        tool_names=manifest.tool_names,
    )


# ---- 路由 ----


@router.get("/available", response_model=AvailableCapabilitiesResponse)
async def list_available_capabilities(
    current_user: UserInfo = Depends(require_auth()),
) -> AvailableCapabilitiesResponse:
    """列出所有源仓库中可用的能力。"""
    mgr = get_capability_manager()
    manifests = mgr.list_available()
    return AvailableCapabilitiesResponse(
        capabilities=[
            _manifest_to_response(m, mgr._source_registry._infer_source(Path(m.source_dir)))
            for m in manifests
        ],
        total=len(manifests),
    )


@router.get(
    "/workspaces/{workspace_id}",
    response_model=WorkspaceCapabilitiesResponse,
)
async def list_workspace_capabilities(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> WorkspaceCapabilitiesResponse:
    """列出工作区中已安装/启用的能力状态。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_capability_manager()

    declarations = mgr._read_declarations(workspace_path)
    results: list[WorkspaceCapabilityItemResponse] = []

    for cap_id, decl in declarations.items():
        manifest = mgr.get_manifest(cap_id)
        display_name = manifest.display_name if manifest else cap_id
        description = manifest.description if manifest else ""
        version = manifest.version if manifest else decl.version

        # 验活
        health = mgr.verify(cap_id, workspace_path)
        status = health.status.value
        error_message = decl.error_message
        if not error_message and status == "error":
            error_message = health.detail

        results.append(
            WorkspaceCapabilityItemResponse(
                capability_id=cap_id,
                kind=decl.kind.value,
                display_name=display_name,
                description=description,
                version=version,
                enabled=decl.enabled,
                source=decl.source,
                status=status,
                error_message=error_message,
            )
        )

    return WorkspaceCapabilitiesResponse(
        workspace_id=workspace_id,
        capabilities=results,
        total=len(results),
    )


@router.post(
    "/workspaces/{workspace_id}/install",
    response_model=CapabilityActionResponse,
)
async def install_capability_to_workspace(
    workspace_id: str,
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """安装能力到工作区。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_capability_manager()
    result = mgr.install(request.capability_id, workspace_path, config=request.config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post(
    "/workspaces/{workspace_id}/uninstall",
    response_model=CapabilityActionResponse,
)
async def uninstall_capability_from_workspace(
    workspace_id: str,
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """从工作区卸载能力。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_capability_manager()
    result = mgr.uninstall(request.capability_id, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post(
    "/workspaces/{workspace_id}/activate",
    response_model=CapabilityActionResponse,
)
async def activate_capability_for_workspace(
    workspace_id: str,
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """激活工作区中的能力。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_capability_manager()
    result = mgr.activate(request.capability_id, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post(
    "/workspaces/{workspace_id}/deactivate",
    response_model=CapabilityActionResponse,
)
async def deactivate_capability_for_workspace(
    workspace_id: str,
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """禁用工作区中的能力。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_capability_manager()
    result = mgr.deactivate(request.capability_id, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post(
    "/workspaces/{workspace_id}/verify",
    response_model=VerifyCapabilityResponse,
)
async def verify_capability_for_workspace(
    workspace_id: str,
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> VerifyCapabilityResponse:
    """验活工作区中的能力。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_capability_manager()
    health = mgr.verify(request.capability_id, workspace_path)
    return VerifyCapabilityResponse(
        capability_id=request.capability_id,
        status=health.status.value,
        detail=health.detail,
        ok=health.status.value in ("active",),
    )


# ---- global routes ----


@router.get("/global", response_model=WorkspaceCapabilitiesResponse)
async def list_global_capabilities(
    current_user: UserInfo = Depends(require_auth()),
) -> WorkspaceCapabilitiesResponse:
    """列出全局工作区中已安装/启用的能力状态。"""
    workspace_path = _get_global_workspace_path(current_user.user_id)
    mgr = get_capability_manager()

    declarations = mgr._read_declarations(workspace_path)
    results: list[WorkspaceCapabilityItemResponse] = []

    for cap_id, decl in declarations.items():
        manifest = mgr.get_manifest(cap_id)
        display_name = manifest.display_name if manifest else cap_id
        description = manifest.description if manifest else ""
        version = manifest.version if manifest else decl.version

        health = mgr.verify(cap_id, workspace_path)
        status = health.status.value
        error_message = decl.error_message
        if not error_message and status == "error":
            error_message = health.detail

        results.append(
            WorkspaceCapabilityItemResponse(
                capability_id=cap_id,
                kind=decl.kind.value,
                display_name=display_name,
                description=description,
                version=version,
                enabled=decl.enabled,
                source=decl.source,
                status=status,
                error_message=error_message,
            )
        )

    return WorkspaceCapabilitiesResponse(
        workspace_id="global",
        capabilities=results,
        total=len(results),
    )


@router.post("/global/install", response_model=CapabilityActionResponse)
async def install_capability_to_global(
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """安装能力到全局工作区。"""
    workspace_path = _get_global_workspace_path(current_user.user_id)
    mgr = get_capability_manager()
    result = mgr.install(request.capability_id, workspace_path, config=request.config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post("/global/uninstall", response_model=CapabilityActionResponse)
async def uninstall_capability_from_global(
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """从全局工作区卸载能力。"""
    workspace_path = _get_global_workspace_path(current_user.user_id)
    mgr = get_capability_manager()
    result = mgr.uninstall(request.capability_id, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post("/global/activate", response_model=CapabilityActionResponse)
async def activate_capability_for_global(
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """激活全局工作区中的能力。"""
    workspace_path = _get_global_workspace_path(current_user.user_id)
    mgr = get_capability_manager()
    result = mgr.activate(request.capability_id, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post("/global/deactivate", response_model=CapabilityActionResponse)
async def deactivate_capability_for_global(
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilityActionResponse:
    """禁用全局工作区中的能力。"""
    workspace_path = _get_global_workspace_path(current_user.user_id)
    mgr = get_capability_manager()
    result = mgr.deactivate(request.capability_id, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return CapabilityActionResponse(
        success=True,
        capability_id=request.capability_id,
        message=result.message,
    )


@router.post("/global/verify", response_model=VerifyCapabilityResponse)
async def verify_capability_for_global(
    request: CapabilityActionRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> VerifyCapabilityResponse:
    """验活全局工作区中的能力。"""
    workspace_path = _get_global_workspace_path(current_user.user_id)
    mgr = get_capability_manager()
    health = mgr.verify(request.capability_id, workspace_path)
    return VerifyCapabilityResponse(
        capability_id=request.capability_id,
        status=health.status.value,
        detail=health.detail,
        ok=health.status.value in ("active",),
    )


@router.get(
    "/{capability_id}/source",
    response_model=CapabilitySourceResponse | CapabilitySourceTreeResponse,
)
async def get_capability_source_file(
    capability_id: str,
    file: str = "SKILL.md",
    list: bool = False,  # noqa: A002
    current_user: UserInfo = Depends(require_auth()),
) -> CapabilitySourceResponse | CapabilitySourceTreeResponse:
    """读取能力源目录下的指定文件内容，或列出目录树。

    用于 skill_pack / subagent 等能力的文档预览。
    - list=true: 返回目录下所有文件和子目录的列表
    - list=false (默认): 返回指定文件的内容
    """
    mgr = get_capability_manager()
    manifest = mgr.get_manifest(capability_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="能力不存在")

    source_dir = Path(manifest.source_dir)
    if not source_dir.exists() or not source_dir.is_dir():
        raise HTTPException(status_code=404, detail="能力源目录不存在")

    if list:
        entries: list[CapabilitySourceTreeEntry] = []
        try:
            for p in sorted(source_dir.rglob("*"), key=lambda x: x.as_posix()):
                rel = p.relative_to(source_dir).as_posix()
                if p.name.startswith("."):
                    continue
                entries.append(
                    CapabilitySourceTreeEntry(
                        path=rel,
                        name=p.name,
                        is_dir=p.is_dir(),
                    )
                )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"扫描目录失败: {exc}") from exc
        return CapabilitySourceTreeResponse(
            capability_id=capability_id,
            entries=entries,
        )

    target = (source_dir / file).resolve()
    if not target.is_relative_to(source_dir.resolve()):
        raise HTTPException(status_code=400, detail="非法文件路径")
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    try:
        content = target.read_text(encoding="utf-8")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取文件失败: {exc}") from exc

    return CapabilitySourceResponse(
        capability_id=capability_id,
        file=file,
        content=content,
    )
