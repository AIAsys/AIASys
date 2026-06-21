"""
用户 UI 设置 API 路由

提供用户界面偏好（如 Activity Bar 顺序、面板布局等）的读取和保存接口。
数据以 JSON 文件形式持久化到用户目录下。
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.session.config_projection import (
    read_user_ui_settings,
    write_user_ui_settings,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ui-settings", tags=["ui-settings"])


class UISettingsPayload(BaseModel):
    """UI 设置保存请求"""

    data: dict[str, Any]


class UISettingsResponse(BaseModel):
    """UI 设置响应"""

    data: dict[str, Any]


@router.get("/{user_id}", response_model=UISettingsResponse)
async def get_ui_settings(
    user_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取用户 UI 设置

    Args:
        user_id: 用户 ID

    Returns:
        用户 UI 设置数据（JSON 对象）
    """
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问该用户的 UI 设置")

    try:
        data = read_user_ui_settings(user_id)
        return UISettingsResponse(data=data)
    except Exception as e:
        logger.error(f"读取用户 UI 设置失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to read UI settings") from e


@router.put("/{user_id}", response_model=UISettingsResponse)
async def save_ui_settings(
    user_id: str,
    request: UISettingsPayload,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    保存用户 UI 设置

    Args:
        user_id: 用户 ID
        request: 包含 UI 设置数据的请求

    Returns:
        保存后的 UI 设置数据
    """
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权修改该用户的 UI 设置")

    try:
        write_user_ui_settings(user_id, request.data)
        return UISettingsResponse(data=request.data)
    except Exception as e:
        logger.error(f"保存用户 UI 设置失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to save UI settings") from e
