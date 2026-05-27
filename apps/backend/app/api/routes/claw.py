"""
Claw 通信绑定 API（支持 session 级兼容与全局级主推）
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.claw import (
    ChannelBindingsResponse,
    ClawConnector,
    ClawDispatchRequest,
    ClawDispatchResult,
    ClawOutboundPreview,
    ClawPlatformCatalogItem,
    ClawQrLoginSession,
    ClawQrLoginStartRequest,
    ClawQrLoginStatus,
    SessionClawBinding,
    SessionClawBindingRequest,
)
from app.models.user import UserInfo
from app.services.claw import ClawService
from app.services.session import SessionManager

router = APIRouter(prefix="/claw", tags=["claw"])
_CLAW_SERVICE = ClawService(WORKSPACE_DIR)
_SESSION_MANAGER = SessionManager(WORKSPACE_DIR)


def _resolve_user_scope(request_user_id: Optional[str], current_user: UserInfo) -> str:
    if request_user_id:
        if not current_user.can_access_user_data(request_user_id):
            raise HTTPException(status_code=403, detail="无权访问该用户的 Claw 连接")
        return request_user_id
    return current_user.user_id


def _ensure_session_access(session_id: str, user_id: str) -> None:
    if _SESSION_MANAGER.get_session(session_id, user_id) is None:
        raise HTTPException(status_code=404, detail="目标会话不存在")


@router.get("/connectors", response_model=list[ClawConnector])
async def list_claw_connectors(
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    return _CLAW_SERVICE.list_connectors(resolved_user_id)


@router.get("/channels/{channel_id}/bindings", response_model=ChannelBindingsResponse)
async def list_channel_claw_bindings(
    channel_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """列出绑定到指定频道的所有会话。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    bindings = _CLAW_SERVICE.list_channel_bindings(resolved_user_id, channel_id)
    return ChannelBindingsResponse(channel_id=channel_id, bindings=bindings)


@router.get("/platforms", response_model=list[ClawPlatformCatalogItem])
async def list_claw_platforms(
    current_user: UserInfo = Depends(require_auth()),
):
    _ = current_user
    return _CLAW_SERVICE.list_platforms()


@router.get("/gateway-sessions")
async def list_claw_gateway_sessions(
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    """列出该用户的所有 Gateway Sessions（远端聊天映射）。"""
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    return _CLAW_SERVICE.list_gateway_sessions(resolved_user_id)


@router.post("/{platform}/qr-login/start", response_model=ClawQrLoginSession)
async def start_qr_login(
    platform: str,
    request: ClawQrLoginStartRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    try:
        return await _CLAW_SERVICE.start_qr_login(
            resolved_user_id,
            platform=platform,
            bot_type=request.bot_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Operation failed") from exc


@router.post("/{platform}/qr-login/{flow_id}/poll", response_model=ClawQrLoginStatus)
async def poll_qr_login(
    platform: str,
    flow_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    try:
        return await _CLAW_SERVICE.poll_qr_login(resolved_user_id, flow_id, platform=platform)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Operation failed") from exc


@router.get("/sessions/{session_id}/binding", response_model=SessionClawBinding)
async def get_session_claw_binding(
    session_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    return _CLAW_SERVICE.get_session_binding(resolved_user_id, session_id)


@router.put("/sessions/{session_id}/binding", response_model=SessionClawBinding)
async def save_session_claw_binding(
    session_id: str,
    request: SessionClawBindingRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        return _CLAW_SERVICE.save_session_binding(resolved_user_id, session_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.delete("/sessions/{session_id}/binding", response_model=SessionClawBinding)
async def clear_session_claw_binding(
    session_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    return _CLAW_SERVICE.clear_session_binding(resolved_user_id, session_id)


@router.post("/sessions/{session_id}/start", response_model=SessionClawBinding)
async def start_session_claw_link(
    session_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        return _CLAW_SERVICE.start_session_link(resolved_user_id, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.post("/sessions/{session_id}/stop", response_model=SessionClawBinding)
async def stop_session_claw_link(
    session_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    return _CLAW_SERVICE.stop_session_link(resolved_user_id, session_id)


@router.get("/sessions/{session_id}/outbound-preview", response_model=ClawOutboundPreview)
async def get_session_claw_outbound_preview(
    session_id: str,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    return _CLAW_SERVICE.get_outbound_preview(resolved_user_id, session_id)


@router.post(
    "/sessions/{session_id}/dispatch-last-reply",
    response_model=ClawDispatchResult,
)
async def dispatch_session_claw_last_reply(
    session_id: str,
    request: ClawDispatchRequest,
    user_id: Optional[str] = Query(None, description="用户 ID，仅管理员可指定"),
    current_user: UserInfo = Depends(require_auth()),
):
    resolved_user_id = _resolve_user_scope(user_id, current_user)
    _ensure_session_access(session_id, resolved_user_id)
    try:
        return await _CLAW_SERVICE.dispatch_last_reply(
            resolved_user_id,
            session_id,
            force=request.force,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail="Operation failed") from exc
