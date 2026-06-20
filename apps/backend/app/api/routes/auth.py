"""
认证 API 路由

包含当前用户会话、资料与本地工作区上下文相关接口
"""

import logging
import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response

logger = logging.getLogger(__name__)
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import AUTH_CONFIG
from app.core.database import User, get_db
from app.core.security import create_access_token
from app.models.user import UserInfo

router = APIRouter(prefix="/auth", tags=["auth"])


class UpdateProfileRequest(BaseModel):
    """更新个人资料请求"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    phone: Optional[str] = Field(default=None, max_length=32)
    avatar_color: Optional[str] = Field(default=None, max_length=32)
    avatar_char: Optional[str] = Field(default=None, max_length=8)


class UserInfoResponse(BaseModel):
    """用户信息响应"""

    user: dict


def _normalize_phone(phone: Optional[str]) -> Optional[str]:
    if phone is None:
        return None
    value = phone.strip()
    return value if value else None


def _set_auth_cookie(response: Response, access_token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        # 默认本地开发使用 HTTP，secure=False；生产环境请设置 COOKIE_SECURE=true
        secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=30 * 24 * 60 * 60,  # 30 天
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    """清除认证 Cookie。"""
    response.delete_cookie(
        key="access_token",
        path="/",
        secure=os.environ.get("COOKIE_SECURE", "false").lower() == "true",
    )


def _serialize_user(db_user: Optional[User], current_user: Optional[UserInfo] = None) -> dict:
    if db_user:
        return {
            "id": db_user.id,
            "email": db_user.email,
            "name": db_user.name,
            "phone": db_user.phone,
            "role": db_user.role or "user",
            "avatar_color": db_user.avatar_color,
            "avatar_char": db_user.avatar_char,
            "created_at": (db_user.created_at.isoformat() if db_user.created_at else None),
            "updated_at": (db_user.updated_at.isoformat() if db_user.updated_at else None),
        }

    return {
        "id": current_user.user_id if current_user else None,
        "email": getattr(current_user, "email", None) if current_user else None,
        "name": getattr(current_user, "name", None) if current_user else None,
        "phone": getattr(current_user, "phone", None) if current_user else None,
        "role": current_user.role if current_user else "user",
        "avatar_color": None,
        "avatar_char": None,
        "created_at": None,
        "updated_at": None,
    }


@router.post("/logout")
async def logout(response: Response):
    """
    用户登出

    清除 access_token Cookie
    """
    if AUTH_CONFIG.mode == "local":
        _clear_auth_cookie(response)
        return {
            "success": True,
            "message": "单机默认用户模式下无需登出，已清理本地令牌",
        }

    _clear_auth_cookie(response)
    return {"success": True, "message": "Logout successful"}


@router.get("/session", response_model=UserInfoResponse)
async def get_session(
    current_user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前会话信息

    用于前端检查登录状态
    """
    db_user = db.query(User).filter(User.id == current_user.user_id).first()
    return UserInfoResponse(user=_serialize_user(db_user, current_user))


@router.get("/me", response_model=UserInfoResponse)
async def get_me(
    current_user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    获取当前用户信息
    """
    db_user = db.query(User).filter(User.id == current_user.user_id).first()
    return UserInfoResponse(user=_serialize_user(db_user, current_user))


@router.put("/me", response_model=UserInfoResponse)
async def update_me(
    request: UpdateProfileRequest,
    response: Response,
    current_user: UserInfo = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    更新当前用户资料（本地认证）
    """
    db_user = db.query(User).filter(User.id == current_user.user_id).first()
    if not db_user:
        raise HTTPException(
            status_code=400,
            detail="当前本地默认用户记录不存在，暂不支持在本地修改",
        )

    if (
        request.name is None
        and request.phone is None
        and request.avatar_color is None
        and request.avatar_char is None
    ):
        raise HTTPException(status_code=400, detail="请至少提供一个要更新的字段")

    if request.name is not None:
        cleaned_name = request.name.strip()
        if not cleaned_name:
            raise HTTPException(status_code=400, detail="姓名不能为空")
        db_user.name = cleaned_name

    if request.phone is not None:
        db_user.phone = _normalize_phone(request.phone)

    if request.avatar_color is not None:
        db_user.avatar_color = request.avatar_color.strip() or None

    if request.avatar_char is not None:
        db_user.avatar_char = (
            request.avatar_char.strip()[:1] if request.avatar_char.strip() else None
        )

    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    # 刷新 JWT，确保所有依赖 token 的地方立刻拿到最新资料
    access_token = create_access_token(
        data={
            "sub": db_user.id,
            "email": db_user.email,
            "name": db_user.name,
            "phone": db_user.phone,
            "role": "user",
        }
    )
    _set_auth_cookie(response, access_token)

    return UserInfoResponse(user=_serialize_user(db_user, current_user))
