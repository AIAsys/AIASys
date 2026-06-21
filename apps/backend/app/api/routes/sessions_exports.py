import io
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo
from app.utils.file_utils import sanitize_content_disposition_filename
from app.services.export import (
    SessionExportNotFoundError,
    SessionExportScope,
    SessionExportService,
    SessionImportError,
    SessionImportService,
)
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService

logger = logging.getLogger(__name__)
session_manager = SessionManager(WORKSPACE_DIR)
workspace_registry = WorkspaceRegistryService(WORKSPACE_DIR, session_manager=session_manager)
session_export_service = SessionExportService(session_manager)
session_import_service = SessionImportService(
    workspace_root=WORKSPACE_DIR,
    session_manager=session_manager,
    registry=workspace_registry,
)

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
                exported_by=current_user.user_id,
            )
            return StreamingResponse(
                io.BytesIO(payload),
                media_type="application/json",
                headers={"Content-Disposition": f'attachment; filename="{sanitize_content_disposition_filename(download_filename)}"'},
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
                exported_by=current_user.user_id,
            )

        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{sanitize_content_disposition_filename(download_filename)}"'},
        )
    except SessionExportNotFoundError:
        raise HTTPException(status_code=404, detail="Session export not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("会话导出失败: %s", e)
        raise HTTPException(status_code=500, detail="Export failed") from e


@router.post("/{user_id}/import")
async def import_session_conversation(
    user_id: str,
    workspace_id: str = Query(..., description="导入目标工作区 ID"),
    file: UploadFile = File(..., description="session_conversation_export JSON 文件"),
    current_user: UserInfo = Depends(require_auth()),
):
    """导入 session_conversation_export JSON，作为新会话追加到指定工作区。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only import into your own workspaces")

    try:
        content = await file.read()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"读取文件失败: {exc}") from exc

    try:
        summary = session_import_service.import_conversation(
            user_id=user_id,
            workspace_id=workspace_id,
            json_bytes=content,
        )
        return summary
    except SessionImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("会话导入失败: %s", exc)
        raise HTTPException(status_code=500, detail="Import failed") from exc
