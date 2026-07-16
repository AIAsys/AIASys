"""系统级能力注册表与集成市场 API。"""

from __future__ import annotations

import dataclasses
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.models.capability import (
    CapabilityRegistryResponse,
    IntegrationMarketResponse,
    ToolCategoryRegistryResponse,
)
from app.models.user import UserInfo
from app.services.capability_registry import get_capability_registry_service
from app.services.runtime_storage_settings import RuntimeStorageSettingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


class StoragePathSetting(BaseModel):
    key: str
    effective_path: str
    configured_path: str
    default_path: str
    pending_path: str | None = None
    overridden_by_env: str | None = None
    editable: bool


class StorageSettingsResponse(BaseModel):
    paths: list[StoragePathSetting]
    restart_required: bool
    config_path: str


class UpdateStorageSettingsRequest(BaseModel):
    paths: dict[str, str | None] = Field(default_factory=dict)


class ValidateStoragePathRequest(BaseModel):
    path: str = Field(..., min_length=1)
    create: bool = True


class StoragePathValidationResponse(BaseModel):
    path: str
    ok: bool
    exists: bool
    is_directory: bool
    readable: bool
    writable: bool
    created: bool
    message: str


class StorageMigrationRequest(BaseModel):
    paths: dict[str, str | None] = Field(default_factory=dict)


class StorageMigrationResponse(BaseModel):
    migration_id: str | None = None
    status: str
    created_at: str | None = None
    updated_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    paths: dict[str, str] = Field(default_factory=dict)
    config_paths: dict[str, str] = Field(default_factory=dict)
    items: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    progress: dict = Field(default_factory=dict)
    can_start: bool = False
    message: str | None = None


class UvStatusResponse(BaseModel):
    installed: bool
    version: str | None = None
    path: str | None = None
    message: str | None = None


class UvInstallResponse(BaseModel):
    installed: bool
    version: str | None = None
    path: str | None = None
    message: str


class UvMirrorConfigResponse(BaseModel):
    """uv 镜像配置响应 — 仅含安装器镜像（PyPI/Python 二进制镜像由 uv 自身处理）"""

    installer_mirror: str = ""


class UvMirrorConfigRequest(BaseModel):
    """uv 镜像配置请求"""

    installer_mirror: str = Field(default="", description="uv 安装器镜像基 URL")


def get_runtime_storage_settings_service() -> RuntimeStorageSettingsService:
    return RuntimeStorageSettingsService()


from app.core.uv_utils import find_uv_binary, get_uv_version, install_uv
from app.services.shell_environment import (
    detect_powershell_info,
    detect_shell_environment,
    install_busybox_w32,
    install_busybox_w32_streamed,
    set_powershell_prompt_target,
)


@router.get("/capability-registry", response_model=CapabilityRegistryResponse)
async def get_capability_registry(
    analysis_sandbox_mode: str | None = Query(
        None,
        description="analysis 预览使用的 sandbox mode；当前仅支持 local。",
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """返回系统可识别的能力目录与各 mode 默认预置。"""
    _ = current_user
    return get_capability_registry_service().get_registry(
        user_id=current_user.user_id,
        analysis_sandbox_mode=analysis_sandbox_mode,
    )


@router.get("/integrations-market", response_model=IntegrationMarketResponse)
async def get_integrations_market(
    current_user: UserInfo = Depends(require_auth()),
):
    """返回系统级集成市场目录。"""
    _ = current_user
    return get_capability_registry_service().get_integrations_market()


@router.get("/tool-categories", response_model=ToolCategoryRegistryResponse)
async def get_tool_categories(
    current_user: UserInfo = Depends(require_auth()),
):
    """返回工具功能分类目录。"""
    _ = current_user
    return get_capability_registry_service().get_tool_category_registry()


@router.get("/storage-settings", response_model=StorageSettingsResponse)
async def get_storage_settings(
    current_user: UserInfo = Depends(require_auth()),
):
    """返回当前有效存储路径与待重启生效配置。"""
    _ = current_user
    return get_runtime_storage_settings_service().get_settings()


@router.put("/storage-settings", response_model=StorageSettingsResponse)
async def update_storage_settings(
    request: UpdateStorageSettingsRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """保存待重启生效的存储路径配置。"""
    _ = current_user
    try:
        return get_runtime_storage_settings_service().save_settings(request.paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/storage-settings/validate-path",
    response_model=StoragePathValidationResponse,
)
async def validate_storage_path(
    request: ValidateStoragePathRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """校验存储路径是否可用于重启后的运行态目录。"""
    _ = current_user
    return get_runtime_storage_settings_service().validate_path(
        request.path,
        create=request.create,
    )


@router.get(
    "/storage-settings/migration",
    response_model=StorageMigrationResponse,
)
async def get_storage_migration_status(
    current_user: UserInfo = Depends(require_auth()),
):
    """返回当前存储迁移状态。"""
    _ = current_user
    return get_runtime_storage_settings_service().get_migration_status()


@router.post(
    "/storage-settings/migration/preview",
    response_model=StorageMigrationResponse,
)
async def preview_storage_migration(
    request: StorageMigrationRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """预检存储迁移计划。"""
    _ = current_user
    return get_runtime_storage_settings_service().preview_migration(request.paths)


@router.post(
    "/storage-settings/migration/start",
    response_model=StorageMigrationResponse,
)
async def start_storage_migration(
    request: StorageMigrationRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """启动存储迁移任务。"""
    _ = current_user
    try:
        return get_runtime_storage_settings_service().start_migration(request.paths)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/uv", response_model=UvStatusResponse)
async def get_uv_status(
    current_user: UserInfo = Depends(require_auth()),
):
    """检查全局 uv 安装状态。"""
    _ = current_user
    path = find_uv_binary()
    version = get_uv_version(path) if path else None
    if path:
        return UvStatusResponse(
            installed=True,
            version=version,
            path=path,
            message=f"Python 包管理器已就绪 ({version or ''})",
        )
    return UvStatusResponse(
        installed=False,
        message="Python 包管理器未安装。选择 Python 环境后会自动安装。",
    )


@router.post("/uv", response_model=UvInstallResponse)
async def install_uv_endpoint(
    current_user: UserInfo = Depends(require_auth()),
):
    """全局安装 uv（跨平台）。"""
    # 先检查是否已安装
    existing = find_uv_binary()
    if existing:
        version = get_uv_version(existing)
        return UvInstallResponse(
            installed=True,
            version=version,
            path=existing,
            message=f"Python 包管理器已就绪 ({version or existing})",
        )

    # 读取用户镜像配置，用于安装 uv 本身
    installer_mirror = None
    try:
        from app.core.aiasys_config import load_aiasys_config

        cfg = load_aiasys_config(current_user.user_id)
        if cfg.uv.installer_mirror:
            installer_mirror = cfg.uv.installer_mirror
    except Exception:
        logger.warning(
            "Failed to load AIASys config for user %s, using default installer mirror",
            current_user.user_id,
        )

    ok, path, version, message = install_uv(installer_mirror=installer_mirror)
    if not ok:
        raise HTTPException(status_code=500, detail=message)
    return UvInstallResponse(
        installed=True,
        version=version,
        path=path,
        message=message,
    )


@router.get("/uv/mirror-config", response_model=UvMirrorConfigResponse)
async def get_uv_mirror_config(
    current_user: UserInfo = Depends(require_auth()),
):
    """获取当前用户的 uv 安装器镜像配置。"""
    try:
        from app.core.aiasys_config import load_aiasys_config

        cfg = load_aiasys_config(current_user.user_id)
        return UvMirrorConfigResponse(
            installer_mirror=cfg.uv.installer_mirror,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取镜像配置失败: {exc}") from exc


@router.put("/uv/mirror-config", response_model=UvMirrorConfigResponse)
async def update_uv_mirror_config(
    request: UvMirrorConfigRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新当前用户的 uv 安装器镜像配置。"""
    try:
        from app.core.aiasys_config import UvTomlSection, save_aiasys_uv_config

        uv_section = UvTomlSection(
            installer_mirror=request.installer_mirror.strip(),
        )
        save_aiasys_uv_config(current_user.user_id, uv_section)
        return UvMirrorConfigResponse(
            installer_mirror=uv_section.installer_mirror,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存镜像配置失败: {exc}") from exc


class ShellComponentItem(BaseModel):
    id: str
    name: str
    installed: bool
    path: str | None = None
    version: str | None = None
    description: str = ""
    download_url: str = ""
    license: str = ""
    bundled: bool = False
    optional: bool = False


class PowerShellInfoResponse(BaseModel):
    pwsh_path: str | None = None
    pwsh_version: str | None = None
    powershell_path: str | None = None
    powershell_version: str | None = None
    active_path: str | None = None
    active_version: str | None = None
    prompt_target: str = "auto"
    effective_version: str | None = None


class ShellEnvironmentResponse(BaseModel):
    platform: str
    is_windows: bool
    recommended_family: str
    components: list[ShellComponentItem]
    guidance: str
    powershell: PowerShellInfoResponse | None = None


class PowerShellTargetRequest(BaseModel):
    target: str = Field(..., description="提示词目标版本：auto / 5.1 / 7")


class InstallBusyboxResponse(BaseModel):
    installed: bool
    path: str
    message: str


def _to_powershell_response(info) -> PowerShellInfoResponse | None:
    if info is None:
        return None
    return PowerShellInfoResponse(**dataclasses.asdict(info))


@router.get("/shell-environment", response_model=ShellEnvironmentResponse)
async def get_shell_environment(
    current_user: UserInfo = Depends(require_auth()),
):
    """检测当前系统可用的 shell 环境及增强组件状态。"""
    _ = current_user
    report = detect_shell_environment()
    return ShellEnvironmentResponse(
        platform=report.platform,
        is_windows=report.is_windows,
        recommended_family=report.recommended_family,
        components=[ShellComponentItem(**dataclasses.asdict(c)) for c in report.components],
        guidance=report.guidance,
        powershell=_to_powershell_response(report.powershell),
    )


@router.put(
    "/shell-environment/powershell-target",
    response_model=PowerShellInfoResponse,
)
async def update_powershell_target(
    request: PowerShellTargetRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """设置 Agent 提示词的 PowerShell 目标版本（auto / 5.1 / 7）。"""
    _ = current_user
    try:
        set_powershell_prompt_target(request.target)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _to_powershell_response(detect_powershell_info(force=True))


@router.post("/shell-environment/install-busybox", response_model=InstallBusyboxResponse)
async def install_busybox_endpoint(
    current_user: UserInfo = Depends(require_auth()),
):
    """从官方源下载并安装 busybox-w32 到用户数据目录。"""
    _ = current_user
    try:
        ok, path = await install_busybox_w32()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"下载 busybox-w32 失败: {exc}") from exc

    if not ok:
        raise HTTPException(status_code=500, detail=path)
    return InstallBusyboxResponse(
        installed=True,
        path=path,
        message=f"busybox-w32 已下载到 {path}",
    )


@router.get("/shell-environment/install-busybox/stream")
async def install_busybox_stream_endpoint(
    current_user: UserInfo = Depends(require_auth()),
):
    """流式下载 busybox-w32，通过 SSE 返回下载进度。"""
    _ = current_user
    import json

    async def event_stream():
        async for event in install_busybox_w32_streamed():
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
