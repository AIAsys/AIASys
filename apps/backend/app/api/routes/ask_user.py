"""
AskUser 工具 API 路由

处理用户对 AskUser 请求的响应
"""

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.agents.tools.ask_user import (
    AskUserRequest,
    AskUserStore,
    AskUserType,
    get_ask_user_tool,
)
from app.core.auth import require_auth
from app.core.config import AUTH_MODE
from app.models.user import UserInfo

router = APIRouter(prefix="/ask-user", tags=["ask-user"])


class AskUserResolveRequest(BaseModel):
    """用户响应请求"""

    request_id: str = Field(description="请求ID")
    approved: bool = Field(description="是否批准/确认")
    value: Any | None = Field(None, description="用户输入的值")


class AskUserResolveResponse(BaseModel):
    """处理结果"""

    success: bool
    message: str


class AskUserDevCreateRequest(BaseModel):
    """开发/测试辅助：为当前用户注入待处理的 AskUser 请求。"""

    session_id: str = Field(description="绑定的会话 ID")
    request_id: str | None = Field(default=None, description="可选，自定义请求 ID")
    type: AskUserType = Field(default=AskUserType.CONFIRM, description="询问类型")
    title: str = Field(default="测试确认", description="标题")
    message: str = Field(default="请确认是否继续", description="详细消息")
    placeholder: str | None = Field(default=None, description="输入占位符")
    options: list[dict[str, Any]] | None = Field(default=None, description="选项列表")
    default_value: Any | None = Field(default=None, description="默认值")
    timeout: int = Field(default=300, description="超时时间（秒）", ge=10, le=600)
    created_at: str | None = Field(default=None, description="可选，自定义创建时间")


def _ensure_dev_test_support_enabled() -> None:
    """仅在本地/无认证开发模式下暴露测试注入能力。"""
    if AUTH_MODE not in {"local", "none"}:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/resolve", response_model=AskUserResolveResponse)
async def resolve_ask_user(
    request: AskUserResolveRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    处理用户对 AskUser 请求的响应

    前端在用户使用确认框/输入框后调用此 API
    """
    store = AskUserStore()
    pending = store.get_request(request.request_id)
    if pending is None or pending.future.done():
        raise HTTPException(
            status_code=404,
            detail="Request not found, may have timed out or been processed",
        )

    if not current_user.can_access_user_data(pending.user_id):
        raise HTTPException(status_code=403, detail="无权响应该 AskUser 请求")

    tool = get_ask_user_tool()

    try:
        success = await tool.resolve(
            request_id=request.request_id,
            approved=request.approved,
            value=request.value,
        )

        if success:
            return AskUserResolveResponse(success=True, message="响应已处理，Agent 将继续执行")
        else:
            raise HTTPException(
                status_code=404,
                detail="Request not found, may have timed out or been processed",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to process response")


@router.get("/pending")
async def get_pending_requests(
    session_id: str | None = Query(None, description="按会话ID过滤"),
    user_id: str | None = Query(None, description="按用户ID过滤"),
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取待处理的请求列表（调试用）

    Returns:
        待处理请求数量及ID列表
    """
    store = AskUserStore()
    effective_user_id = user_id
    if effective_user_id:
        if not current_user.can_access_user_data(effective_user_id):
            raise HTTPException(status_code=403, detail="无权查看该用户的 AskUser 请求")
    elif not current_user.is_admin():
        effective_user_id = current_user.user_id

    pending_items = store.list_pending(
        session_id=session_id,
        user_id=effective_user_id,
    )
    pending_ids = [item["request_id"] for item in pending_items]

    return {
        "pending_count": len(pending_ids),
        "request_ids": pending_ids,
        "requests": pending_items,
    }


@router.post("/dev/create-pending")
async def create_dev_pending_request(
    payload: AskUserDevCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    开发/测试辅助：为当前登录用户创建一条 pending AskUser 请求。

    仅用于本地浏览器回归与调试，不在生产认证模式开放。
    """
    _ensure_dev_test_support_enabled()

    request_id = payload.request_id or f"dev-ask-user-{uuid4()}"
    request = AskUserRequest(
        request_id=request_id,
        type=payload.type,
        title=payload.title,
        message=payload.message,
        placeholder=payload.placeholder,
        options=payload.options,
        default_value=payload.default_value,
        timeout=payload.timeout,
        created_at=payload.created_at or datetime.now().isoformat(),
    )

    store = AskUserStore()
    store.create_request(
        request=request,
        session_id=payload.session_id,
        user_id=current_user.user_id,
    )

    pending_items = store.list_pending(
        session_id=payload.session_id,
        user_id=current_user.user_id,
    )

    return {
        "success": True,
        "request_id": request_id,
        "session_id": payload.session_id,
        "pending_count": len(pending_items),
        "request": request.model_dump(),
    }


@router.get("/health")
async def health_check():
    """
    健康检查

    Returns:
        服务状态
    """
    return {"status": "ok", "service": "ask-user"}
