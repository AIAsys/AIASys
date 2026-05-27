import io
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.export import (
    SessionExportNotFoundError,
    SessionExportScope,
    SessionExportService,
)
from app.services.session import SessionManager

from .sessions_helpers import _is_system_reminder_message

logger = logging.getLogger(__name__)
session_manager = SessionManager(WORKSPACE_DIR)
session_export_service = SessionExportService(session_manager)

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/{user_id}/{session_id}/export")
async def export_session_artifact(
    user_id: str,
    session_id: str,
    scope: SessionExportScope = Query(
        default="bundle",
        description="导出范围: bundle | conversation | workspace",
    ),
    current_user: UserInfo = Depends(require_auth()),
):
    """按范围导出会话对话记录 / 工作区 / 审计包。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only export your own sessions")

    try:
        conversation_messages = []
        if scope in {"bundle", "conversation"}:
            conversation_messages = await agent_service.get_session_history(user_id, session_id)
            conversation_messages = [
                msg
                for msg in conversation_messages
                if msg.get("role") not in ("_checkpoint", "_usage", "_system_prompt", "system")
                and not _is_system_reminder_message(msg)
            ]

        logger.info(
            "会话导出: %s/%s scope=%s by %s",
            user_id,
            session_id,
            scope,
            current_user.user_id,
        )

        if scope == "conversation":
            payload, download_filename = session_export_service.build_conversation_export(
                user_id=user_id,
                session_id=session_id,
                conversation_messages=conversation_messages,
                exported_by=current_user.user_id,
            )
            return StreamingResponse(
                io.BytesIO(payload),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
            )

        if scope == "workspace":
            zip_buffer, download_filename = session_export_service.build_workspace_archive(
                user_id=user_id,
                session_id=session_id,
                exported_by=current_user.user_id,
            )
        else:
            zip_buffer, download_filename = session_export_service.build_bundle_archive(
                user_id=user_id,
                session_id=session_id,
                conversation_messages=conversation_messages,
                exported_by=current_user.user_id,
            )

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{download_filename}"'},
        )
    except SessionExportNotFoundError:
        raise HTTPException(status_code=404, detail="Session export not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("会话导出失败: %s", e)
        raise HTTPException(status_code=500, detail="Export failed")
