"""系统级能力注册表与集成市场 API。"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
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

router = APIRouter(prefix="/system", tags=["system"])


class StoragePathSetting(BaseModel):
    key: str
    effective_path: str
    configured_path: str
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


def get_runtime_storage_settings_service() -> RuntimeStorageSettingsService:
    return RuntimeStorageSettingsService()


def _find_uv_binary() -> str | None:
    """在 PATH 和常见安装位置中查找 uv 可执行文件。"""
    uv = shutil.which("uv")
    if uv:
        return uv

    home = Path.home()
    candidates: list[Path] = [
        home / ".cargo" / "bin" / "uv",
        home / ".local" / "bin" / "uv",
    ]
    if os.name == "nt":
        candidates.append(home / ".cargo" / "bin" / "uv.exe")

    for p in candidates:
        if p.is_file():
            return str(p)
    return None


def _get_uv_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if completed.returncode == 0:
            raw = (completed.stdout or "").strip()
            # uv --version 输出格式: "uv 0.11.3 (x86_64-unknown-linux-gnu)"
            # 提取纯版本号，去掉前缀和平台信息
            import re

            match = re.search(r"uv\s+(\d+\.\d+\.\d+)", raw)
            if match:
                return match.group(1)
            return raw or None
    except Exception:
        pass
    return None


def _install_uv() -> tuple[bool, str | None, str | None, str]:
    """尝试安装 uv，返回 (是否成功, 路径, 版本, 消息)。"""
    if os.name == "nt":
        command = [
            "powershell",
            "-ExecutionPolicy",
            "ByPass",
            "-c",
            "irm https://astral.sh/uv/install.ps1 | iex",
        ]
    else:
        command = ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except Exception as exc:
        return False, None, None, f"安装命令执行失败: {exc}"

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()

    if completed.returncode != 0:
        detail = stderr or stdout or f"退出码 {completed.returncode}"
        return False, None, None, f"安装失败: {detail}"

    # 安装完成后尝试查找
    path = _find_uv_binary()
    version = _get_uv_version(path) if path else None
    if path:
        return True, path, version, f"Python 包管理器安装成功 ({version or path})"
    return False, None, None, "安装脚本已执行，但未能找到 uv。可能需要刷新环境变量后重试。"


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
    path = _find_uv_binary()
    version = _get_uv_version(path) if path else None
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
    _ = current_user
    # 先检查是否已安装
    existing = _find_uv_binary()
    if existing:
        version = _get_uv_version(existing)
        return UvInstallResponse(
            installed=True,
            version=version,
            path=existing,
            message=f"Python 包管理器已就绪 ({version or existing})",
        )

    ok, path, version, message = _install_uv()
    if not ok:
        raise HTTPException(status_code=500, detail=message)
    return UvInstallResponse(
        installed=True,
        version=version,
        path=path,
        message=message,
    )
