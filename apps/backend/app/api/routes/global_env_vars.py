"""全局环境变量 API"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.global_env_vars import get_global_env_vars, set_global_env_vars

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/global-env-vars", tags=["global-env-vars"])


class GlobalEnvVarsBody(BaseModel):
    env_vars: dict[str, str] = Field(default_factory=dict)


class GlobalEnvVarsResponse(BaseModel):
    env_vars: dict[str, str]


@router.get("/{user_id}", response_model=GlobalEnvVarsResponse)
async def get_global_env_vars_route(
    user_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权访问")
    return GlobalEnvVarsResponse(env_vars=get_global_env_vars(user_id))


@router.put("/{user_id}", response_model=GlobalEnvVarsResponse)
async def set_global_env_vars_route(
    user_id: str,
    body: GlobalEnvVarsBody,
    current_user: UserInfo = Depends(require_auth()),
):
    if current_user.user_id != user_id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="无权修改")
    set_global_env_vars(user_id, body.env_vars)
    return GlobalEnvVarsResponse(env_vars=body.env_vars)


@router.get("/me", response_model=GlobalEnvVarsResponse)
async def get_my_global_env_vars(
    current_user: UserInfo = Depends(require_auth()),
):
    """获取当前登录用户的全局环境变量。"""
    return GlobalEnvVarsResponse(env_vars=get_global_env_vars(current_user.user_id))


@router.put("/me", response_model=GlobalEnvVarsResponse)
async def set_my_global_env_vars(
    body: GlobalEnvVarsBody,
    current_user: UserInfo = Depends(require_auth()),
):
    """设置当前登录用户的全局环境变量。"""
    set_global_env_vars(current_user.user_id, body.env_vars)
    return GlobalEnvVarsResponse(env_vars=body.env_vars)
