import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.session import StructuredMessage
from app.models.user import UserInfo
from app.services.session import SessionManager

from .sessions_helpers import _filter_visible_history_messages
from .sessions_models import MessageRequest

logger = logging.getLogger(__name__)
session_manager = SessionManager(WORKSPACE_DIR)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("/{user_id}/{session_id}/messages")
async def add_message(
    user_id: str,
    session_id: str,
    request: MessageRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """添加消息到会话"""
    # 检查是否有权访问该用户的数据
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only add messages to your own sessions",
        )

    try:
        message = StructuredMessage(
            role=request.role,
            content=request.content,
            timestamp=datetime.now().isoformat(),
        )
        session_manager.add_message(session_id, user_id, message.model_dump())
        return {"success": True}
    except Exception as e:
        logger.error(f"添加消息失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to add message")


@router.get("/{user_id}/{session_id}/messages")
async def get_messages(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取会话消息历史"""
    # 检查是否有权访问该用户的数据
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own messages")

    try:
        history = session_manager.get_history(session_id, user_id)
        # 过滤内部 SDK 消息和 system prompt
        filtered_history = _filter_visible_history_messages(history)
        return {"messages": filtered_history}
    except Exception as e:
        logger.error(f"获取消息失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve messages")


@router.get("/{user_id}/{session_id}/file-snapshots")
async def get_file_snapshots(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取会话的文件快照历史（视图快照）

    返回每次工具调用前后的文件列表，用于历史回顾时了解当时的文件状态。
    """
    # 检查是否有权访问该用户的数据
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only access your own file snapshots",
        )

    try:
        snapshots = session_manager.get_file_snapshots(session_id, user_id)
        return {"snapshots": snapshots}
    except Exception as e:
        logger.error(f"获取文件快照失败: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve file snapshots")
