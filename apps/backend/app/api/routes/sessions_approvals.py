"""Session 能力确认（审批）API。

对标 kimi-cli ApprovalRuntime 的 resolve / list_pending 能力，
通过 REST API 替代 JSON-RPC，适配 AIASys 的 SSE 架构。
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.agent import agent_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sessions"])


# ---------------------------------------------------------------------------
# 请求/响应模型
# ---------------------------------------------------------------------------


class ApprovalResolveRequest(BaseModel):
    """确认或拒绝能力请求"""

    approved: bool = Field(..., description="True 表示允许，False 表示拒绝")
    feedback: str = Field(default="", description="拒绝时的反馈文案")
    scope: str = Field(
        default="once",
        description='"once" 只批准这一次，"session" 记住到本会话自动批准列表',
    )


class ApprovalRecordResponse(BaseModel):
    """Pending 审批记录"""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    prompt: str
    status: str
    created_at: str
    subagent_name: str | None = None
    agent_id: str | None = None


class ApprovalListResponse(BaseModel):
    """Pending 审批列表响应"""

    pending: list[ApprovalRecordResponse]


class ApprovalResolveResponse(BaseModel):
    """确认操作响应"""

    success: bool
    message: str


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _get_runtime_session(user_id: str, session_id: str, agent_id: str | None = None):
    """从 agent_service 获取活跃 runtime session。

    当提供 agent_id 时，查找子 Agent 的 session 而非 Host session。
    """
    if agent_id:
        from app.services.agent.subagent_registry import get_subagent_registry

        subagent_session = get_subagent_registry().get(agent_id)
        if subagent_session is None:
            raise HTTPException(status_code=404, detail="子 Agent 会话未激活或已关闭")
        if not hasattr(subagent_session, "_confirmation_manager"):
            raise HTTPException(status_code=500, detail="子 Agent 会话不支持能力确认")
        return subagent_session

    session_key = f"{user_id}/{session_id}"
    session = getattr(agent_service, "_active_sessions", {}).get(session_key)
    if session is None:
        raise HTTPException(status_code=404, detail="会话未激活或已关闭")
    if not hasattr(session, "_confirmation_manager"):
        raise HTTPException(status_code=500, detail="会话不支持能力确认")
    return session


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/{user_id}/{session_id}/approvals/{tool_call_id}",
    response_model=ApprovalResolveResponse,
)
async def resolve_approval(
    user_id: str,
    session_id: str,
    tool_call_id: str,
    body: ApprovalResolveRequest,
    agent_id: str | None = Query(None, description="子 Agent ID，处理子 Agent 能力确认时必传"),
    _user: UserInfo = Depends(require_auth()),
):
    """确认或拒绝指定的能力请求。

    前端收到 ``capability_confirmation`` 或 ``subagent_capability_confirmation`` SSE 事件后，
    调用此接口发送用户的审批决定。
    处理子 Agent 的能力确认时需传入 agent_id 参数。
    """
    try:
        session = _get_runtime_session(user_id, session_id, agent_id=agent_id)
    except HTTPException:
        raise

    manager = session._confirmation_manager
    resolved = manager.resolve(
        tool_call_id=tool_call_id,
        approved=body.approved,
        feedback=body.feedback,
        scope=body.scope,
    )

    if not resolved:
        raise HTTPException(
            status_code=404,
            detail="未找到待确认请求，可能已超时或已被处理",
        )

    action = "已批准" if body.approved else "已拒绝"
    logger.info(
        "能力确认已处理: session=%s/%s tool_call_id=%s approved=%s scope=%s",
        user_id,
        session_id,
        tool_call_id,
        body.approved,
        body.scope,
    )
    return ApprovalResolveResponse(success=True, message=action)


@router.get(
    "/{user_id}/{session_id}/approvals/pending",
    response_model=ApprovalListResponse,
)
async def list_pending_approvals(
    user_id: str,
    session_id: str,
    _user: UserInfo = Depends(require_auth()),
):
    """列出当前会话所有 pending 的能力确认请求。

    前端重连 SSE 后调用，恢复可能遗漏的确认弹窗。
    """
    try:
        session = _get_runtime_session(user_id, session_id)
    except HTTPException:
        # 会话未激活也返回空列表（可能是历史会话）
        return ApprovalListResponse(pending=[])

    manager = session._confirmation_manager
    pending = manager.list_pending()

    return ApprovalListResponse(
        pending=[
            ApprovalRecordResponse(
                tool_call_id=r.tool_call_id,
                tool_name=r.tool_name,
                arguments=r.arguments,
                prompt=r.prompt,
                status=r.status,
                created_at=r.created_at.isoformat(),
                subagent_name=r.subagent_name,
                agent_id=r.agent_id,
            )
            for r in pending
        ]
    )
