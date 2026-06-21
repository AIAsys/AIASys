import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.session import SessionManager

from .sessions_helpers import _build_session_status_payload

logger = logging.getLogger(__name__)
session_manager = SessionManager(WORKSPACE_DIR)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _build_session_update_response(user_id: str, session_id: str) -> dict:
    updated_metadata = session_manager.get_session(session_id, user_id)
    if not updated_metadata:
        raise HTTPException(status_code=500, detail="会话状态丢失")

    execution_summary = session_manager.get_execution_summary(session_id, user_id)
    return {
        "success": True,
        "session": _build_session_status_payload(
            updated_metadata,
            execution_summary,
        ),
    }


@router.post("/{user_id}/{session_id}/compact")
async def compact_session(
    user_id: str,
    session_id: str,
    request: Request,
    current_user: UserInfo = Depends(require_auth()),
):
    """压缩当前会话 runtime 上下文，支持可选自定义指令。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only compact your own sessions",
        )

    metadata = session_manager.get_session(session_id, user_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="会话不存在")

    try:
        # 解析可选的自定义指令
        body = await request.json()
        instruction = body.get("instruction", "") if body else ""

        await agent_service.compact_session_context(user_id, session_id, instruction)

        # 读取最近一次压缩事件
        compaction_event = None
        session_key = f"{user_id}/{session_id}"
        active_session = getattr(agent_service, "_active_sessions", {}).get(session_key)
        if active_session is not None:
            compaction_event = getattr(active_session, "_last_compaction_event", None)

        response = _build_session_update_response(user_id, session_id)
        if compaction_event:
            response["compaction"] = compaction_event
        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error("压缩对话上下文失败: %s", e)
        raise HTTPException(status_code=500, detail="Context compaction failed") from e
