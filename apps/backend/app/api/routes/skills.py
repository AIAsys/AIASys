"""
Skill 管理 API（全局存储 + 工作区复制启用模型）
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR, get_user_global_workspace_dir
from app.models.external_skill_market import (
    ExternalSkillMarketDetailResponse,
    ExternalSkillMarketListResponse,
    ExternalSkillMarketSource,
    InstallExternalSkillRequest,
    InstallExternalSkillResponse,
)
from app.models.user import UserInfo
from app.services.skill_external_market_service import get_external_skill_market_service
from app.skills.manager import get_skill_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["skills"])


# ---- 响应模型 ----


class StoreSkillResponse(BaseModel):
    name: str
    display_name: str
    description: str
    source: str
    entry_relative_path: str
    versions: list[str]
    globally_enabled: bool = False
    env_fields: list[dict] = Field(default_factory=list)


class StoreSkillsListResponse(BaseModel):
    skills: list[StoreSkillResponse]
    total: int


class WorkspaceSkillResponse(BaseModel):
    name: str
    display_name: str
    description: str
    source: str
    entry_relative_path: str
    hash_status: str = "unknown"
    version: str | None = None


class WorkspaceSkillsListResponse(BaseModel):
    workspace_id: str
    skills: list[WorkspaceSkillResponse]
    total: int
    workspace_skill_dir: str = ".aiasys/skills"
    container_mount_path: str = "skills"


class EnableSkillRequest(BaseModel):
    skill_name: str = Field(..., description="要启用的 Skill 名称")
    version: str | None = Field(None, description="指定版本号（默认使用当前版本）")
    force: bool = Field(False, description="是否覆盖已启用的同名 Skill")


class DisableSkillRequest(BaseModel):
    skill_name: str = Field(..., description="要禁用的 Skill 名称")


class UpdateSkillRequest(BaseModel):
    skill_name: str = Field(..., description="要更新的 Skill 名称")


class SkillOperationResponse(BaseModel):
    success: bool
    skill_name: str
    message: str


class SkillEntryResponse(BaseModel):
    name: str
    display_name: str
    description: str
    entry_relative_path: str
    content: str
    env_fields: list[dict] = Field(default_factory=list)


class SkillReadmeResponse(BaseModel):
    content: str
    found: bool = True


# ---- 工具函数 ----


def _get_workspace_path(user_id: str, workspace_id: str) -> Path:
    if not re.match(r"^[a-zA-Z0-9_\-]+$", workspace_id):
        raise HTTPException(status_code=400, detail="无效的 workspace_id")

    workspace_path = (WORKSPACE_DIR / user_id / workspace_id).resolve()
    base_path = WORKSPACE_DIR.resolve()
    if not str(workspace_path).startswith(str(base_path)):
        raise HTTPException(status_code=400, detail="非法工作区路径")

    workspace_path.mkdir(parents=True, exist_ok=True)
    return workspace_path


# ---- 外部 Skill 市场（不变） ----


@router.get(
    "/external-market/sources",
    response_model=list[ExternalSkillMarketSource],
)
async def list_external_skill_market_sources(
    current_user: UserInfo = Depends(require_auth()),
) -> list[ExternalSkillMarketSource]:
    service = get_external_skill_market_service()
    return service.list_sources()


@router.get(
    "/external-market/items",
    response_model=ExternalSkillMarketListResponse,
)
async def list_external_skill_market_items(
    source_id: str,
    search: str | None = None,
    category: str | None = None,
    sort_by: str = "recommended",
    page_number: int = 1,
    page_size: int = 24,
    current_user: UserInfo = Depends(require_auth()),
) -> ExternalSkillMarketListResponse:
    service = get_external_skill_market_service()
    try:
        return await service.list_items(
            source_id=source_id,
            search=search,
            category=category,
            sort_by=sort_by,
            page_number=page_number,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.get(
    "/external-market/detail",
    response_model=ExternalSkillMarketDetailResponse,
)
async def get_external_skill_market_item_detail(
    source_id: str,
    item_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> ExternalSkillMarketDetailResponse:
    service = get_external_skill_market_service()
    try:
        return await service.get_item_detail(source_id=source_id, item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.post(
    "/external-market/workspaces/{workspace_id}/install",
    response_model=InstallExternalSkillResponse,
)
async def install_external_skill_to_workspace(
    workspace_id: str,
    request: InstallExternalSkillRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> InstallExternalSkillResponse:
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    service = get_external_skill_market_service()
    try:
        skill_name = await service.install_item(
            request.source_id,
            item_id=request.item_id,
            workspace_path=workspace_path,
            force=request.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc

    return InstallExternalSkillResponse(
        source_id=request.source_id,
        item_id=request.item_id,
        workspace_id=workspace_id,
        skill_name=skill_name,
        message=f"已安装外部 Skill '{skill_name}' 到当前工作区",
    )


# ---- Skill 仓库 ----


@router.get("/store", response_model=StoreSkillsListResponse)
async def list_store_skills(
    current_user: UserInfo = Depends(require_auth()),
) -> StoreSkillsListResponse:
    """返回 Skill 仓库中的所有 skill（含版本信息 + 我的默认启用状态）。"""
    mgr = get_skill_manager()
    skills = mgr.list_store_skills()
    global_ws_path = get_user_global_workspace_dir(current_user.user_id)
    global_skills = set()
    if global_ws_path.exists():
        global_skills = {s.name for s in mgr.list_workspace_skills(global_ws_path)}
    return StoreSkillsListResponse(
        skills=[
            StoreSkillResponse(
                name=skill.name,
                display_name=skill.display_name,
                description=skill.description,
                source=skill.source,
                entry_relative_path=skill.entry_relative_path,
                versions=mgr.get_skill_versions(skill.name),
                globally_enabled=skill.name in global_skills,
                env_fields=skill.env_fields,
            )
            for skill in skills
        ],
        total=len(skills),
    )


@router.post("/store/import", response_model=SkillOperationResponse)
async def import_skill_to_store(
    file: UploadFile = File(...),
    force: bool = Form(False),
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """导入 zip 到 Skill 仓库。"""
    content = await file.read()
    mgr = get_skill_manager()
    result = mgr.import_skill_archive(
        filename=file.filename or "skill.zip",
        content=content,
        force=force,
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    try:
        from app.capabilities.manager import get_capability_manager

        get_capability_manager()._source_registry.clear_cache()
    except Exception:
        pass
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


@router.delete("/store/{skill_name}", response_model=SkillOperationResponse)
async def delete_store_skill(
    skill_name: str,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """从 Skill 仓库删除 skill。"""
    mgr = get_skill_manager()
    result = mgr.remove_store_skill(skill_name)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    try:
        from app.capabilities.manager import get_capability_manager

        get_capability_manager()._source_registry.clear_cache()
    except Exception:
        pass
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


# ---- 我的默认 Skill 管理 ----


@router.get("/global", response_model=WorkspaceSkillsListResponse)
async def list_global_workspace_skills(
    current_user: UserInfo = Depends(require_auth()),
) -> WorkspaceSkillsListResponse:
    """返回我的默认已启用的 skill。"""
    global_ws_path = get_user_global_workspace_dir(current_user.user_id)
    global_ws_path.mkdir(parents=True, exist_ok=True)
    mgr = get_skill_manager()
    skills = mgr.list_workspace_skills(global_ws_path)
    return WorkspaceSkillsListResponse(
        workspace_id="global",
        skills=[
            WorkspaceSkillResponse(
                name=skill.name,
                display_name=skill.display_name,
                description=skill.description,
                source=skill.source,
                entry_relative_path=skill.entry_relative_path,
                **mgr.get_skill_hash_status(skill.name, global_ws_path),
            )
            for skill in skills
        ],
        total=len(skills),
    )


@router.post(
    "/global/enable",
    response_model=SkillOperationResponse,
)
async def enable_skill_for_global_workspace(
    request: EnableSkillRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """启用 skill 到我的默认。"""
    global_ws_path = get_user_global_workspace_dir(current_user.user_id)
    global_ws_path.mkdir(parents=True, exist_ok=True)
    mgr = get_skill_manager()
    result = mgr.enable_skill_global(
        request.skill_name,
        global_ws_path,
        version=request.version,
        force=request.force,
    )
    status_code = 200 if result.success else 400
    if not result.success:
        raise HTTPException(status_code=status_code, detail=result.message)
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


@router.post(
    "/global/disable",
    response_model=SkillOperationResponse,
)
async def disable_skill_for_global_workspace(
    request: DisableSkillRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """从我的默认禁用 skill。"""
    global_ws_path = get_user_global_workspace_dir(current_user.user_id)
    mgr = get_skill_manager()
    result = mgr.disable_skill_global(request.skill_name, global_ws_path)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


# ---- 工作区 Skill 管理 ----


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceSkillsListResponse)
async def list_workspace_skills(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> WorkspaceSkillsListResponse:
    """返回当前工作区已启用的 skill。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    skills = mgr.list_workspace_skills(workspace_path)
    return WorkspaceSkillsListResponse(
        workspace_id=workspace_id,
        skills=[
            WorkspaceSkillResponse(
                name=skill.name,
                display_name=skill.display_name,
                description=skill.description,
                source=skill.source,
                entry_relative_path=skill.entry_relative_path,
                **mgr.get_skill_hash_status(skill.name, workspace_path),
            )
            for skill in skills
        ],
        total=len(skills),
    )


@router.post(
    "/workspaces/{workspace_id}/enable",
    response_model=SkillOperationResponse,
)
async def enable_skill_for_workspace(
    workspace_id: str,
    request: EnableSkillRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """在工作区启用 skill（从 Skill 仓库复制到工作区）。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    result = mgr.enable_skill(
        request.skill_name,
        workspace_path,
        version=request.version,
        force=request.force,
    )
    status_code = 200 if result.success else 400
    if not result.success:
        raise HTTPException(status_code=status_code, detail=result.message)
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


@router.post(
    "/workspaces/{workspace_id}/disable",
    response_model=SkillOperationResponse,
)
async def disable_skill_for_workspace(
    workspace_id: str,
    request: DisableSkillRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """在工作区禁用 skill。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    result = mgr.disable_skill(request.skill_name, workspace_path)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


@router.post(
    "/workspaces/{workspace_id}/update",
    response_model=SkillOperationResponse,
)
async def update_skill_for_workspace(
    workspace_id: str,
    request: UpdateSkillRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """更新工作区中的 skill（从源重新复制）。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    result = mgr.update_skill(request.skill_name, workspace_path)
    status_code = 200 if result.success else 400
    if not result.success:
        raise HTTPException(status_code=status_code, detail=result.message)
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )


@router.get(
    "/workspaces/{workspace_id}/{skill_name}/entry",
    response_model=SkillEntryResponse,
)
async def get_workspace_skill_entry(
    workspace_id: str,
    skill_name: str,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillEntryResponse:
    """读取工作区或 Skill 仓库中指定 skill 的 SKILL.md。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    result = mgr.get_workspace_skill_entry_content(
        workspace_path=workspace_path,
        skill_name=skill_name,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Skill not found")

    info, content = result
    return SkillEntryResponse(
        name=info.name,
        display_name=info.display_name,
        description=info.description,
        entry_relative_path=info.entry_relative_path,
        content=content,
        env_fields=info.env_fields,
    )


@router.get(
    "/workspaces/{workspace_id}/{skill_name}/readme",
    response_model=SkillReadmeResponse,
)
async def get_workspace_skill_readme(
    workspace_id: str,
    skill_name: str,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillReadmeResponse:
    """读取工作区或 Skill 仓库中指定 skill 的 README.md。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    content = mgr.get_skill_readme_content(
        workspace_path=workspace_path,
        skill_name=skill_name,
    )
    if content is None:
        return SkillReadmeResponse(content="", found=False)
    return SkillReadmeResponse(content=content)


@router.delete(
    "/workspaces/{workspace_id}/{skill_name}",
    response_model=SkillOperationResponse,
)
async def delete_workspace_skill(
    workspace_id: str,
    skill_name: str,
    current_user: UserInfo = Depends(require_auth()),
) -> SkillOperationResponse:
    """删除工作区中的 skill。"""
    workspace_path = _get_workspace_path(current_user.user_id, workspace_id)
    mgr = get_skill_manager()
    result = mgr.remove_workspace_skill(skill_name, workspace_path)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return SkillOperationResponse(
        success=result.success,
        skill_name=result.skill_name,
        message=result.message,
    )
