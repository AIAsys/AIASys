"""工作区模板 API 路由"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.core.templates import (
    build_template_payload,
    delete_user_template,
    export_workspace_as_template,
    get_workspace_template,
    list_workspace_templates,
)
from app.models.external_template_market import (
    ExternalTemplateMarketListResponse,
    InstallExternalTemplateRequest,
)
from app.models.user import UserInfo
from app.services.template_external_market_service import (
    get_external_template_market_service,
)
from app.services.workspace_registry import WorkspaceRegistryService

router = APIRouter(prefix="/workspace-templates", tags=["workspace-templates"])


@router.get("/external-market/sources")
async def list_template_market_sources(
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """列出所有可用的模板市场源。"""
    service = get_external_template_market_service()
    return {"sources": service.list_sources()}


@router.get("/external-market/items")
async def list_template_market_items(
    source_id: str,
    current_user: UserInfo = Depends(require_auth()),
    search: str | None = None,
    category: str | None = None,
) -> ExternalTemplateMarketListResponse:
    """列出指定市场源的模板条目。"""
    service = get_external_template_market_service()
    return service.list_items(source_id, current_user.user_id, search, category)


@router.get("/external-market/detail")
async def get_template_market_detail(
    source_id: str,
    item_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """获取模板市场条目详情。"""
    service = get_external_template_market_service()
    detail = service.get_item_detail(source_id, current_user.user_id, item_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Template market item not found")
    return detail.model_dump()


@router.post("/external-market/install")
async def install_template_market_item(
    request: InstallExternalTemplateRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """将市场模板安装到用户自定义模板目录。"""
    service = get_external_template_market_service()
    try:
        result = service.install_item(request.source_id, current_user.user_id, request.item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("")
async def list_templates(
    current_user: UserInfo = Depends(require_auth()),
    installed_only: bool = False,
) -> dict[str, Any]:
    """列出工作区模板。

    installed_only=true 时只返回用户目录中的模板（已安装）。
    """
    templates = list_workspace_templates(current_user.user_id, installed_only=installed_only)
    return {
        "templates": [build_template_payload(t) for t in templates],
        "total": len(templates),
    }


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """获取单个模板详情。"""
    template = get_workspace_template(template_id, current_user.user_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Template not found")
    return build_template_payload(template)


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    current_user: UserInfo = Depends(require_auth()),
) -> dict[str, Any]:
    """删除用户自定义模板。系统内置模板不可删除。"""
    deleted = delete_user_template(template_id, current_user.user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Template not found or is a built-in template")
    return {"template_id": template_id, "deleted": True}


class ExportTemplateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(default="", max_length=512)
    icon: str = Field(default="file", max_length=64)
    category: str = Field(default="自定义", max_length=64)
    template_id: str | None = Field(default=None, max_length=128)
    files: list[str] | None = Field(default=None, description="要包含的文件路径列表")
    include_env_vars: bool = Field(default=False, description="是否包含工作区环境变量")

    model_config = {"str_strip_whitespace": True}

    @field_validator("template_id")
    @classmethod
    def _validate_template_id(cls, v: str | None) -> str | None:
        if v is not None:
            from app.core.templates import _is_safe_template_id

            if not _is_safe_template_id(v):
                raise ValueError("不安全的模板 ID")
        return v

    @field_validator("files")
    @classmethod
    def _validate_files(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            from app.core.templates import _is_safe_relative_path

            for path in v:
                if not _is_safe_relative_path(path):
                    raise ValueError(f"不安全的文件路径: {path}")
        return v


@router.post("/{workspace_id}/export")
async def export_workspace_template(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
    body: ExportTemplateRequest = Body(...),
) -> dict[str, Any]:
    """将工作区导出为自定义模板。"""
    # 验证工作区存在
    service = WorkspaceRegistryService(WORKSPACE_DIR)
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    workspace_dir = service.get_workspace_root(current_user.user_id, workspace_id)

    try:
        template = export_workspace_as_template(
            workspace_dir=workspace_dir,
            user_id=current_user.user_id,
            name=body.name,
            description=body.description,
            icon=body.icon,
            category=body.category,
            template_id=body.template_id,
            files=body.files,
            include_env_vars=body.include_env_vars,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return build_template_payload(template)
