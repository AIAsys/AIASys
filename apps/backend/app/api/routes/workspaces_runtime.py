from fastapi import APIRouter, Depends, HTTPException

from app.api.routes.workspaces_conversation_utils import (
    _build_workspace_conversation_runtime_summary,
    _get_workspace_conversation_runtime,
)
from app.core.auth import require_auth
from app.models.user import UserInfo
from app.models.workspace import (
    ConversationRuntimeActionResponse,
    ConversationRuntimeListResponse,
)
from app.services.history import SessionExecutionJournal
from app.services.workspace_registry import get_workspace_registry_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


@router.get(
    "/{workspace_id}/conversation-runtimes",
    response_model=ConversationRuntimeListResponse,
)
async def list_workspace_conversation_runtimes(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    try:
        workspace = service.get_workspace(
            current_user.user_id,
            workspace_id,
            include_conversations=True,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    runtimes = [
        _build_workspace_conversation_runtime_summary(
            service=service,
            user_id=current_user.user_id,
            workspace_id=workspace_id,
            current_conversation_id=workspace.current_conversation_id,
            conversation=conversation,
        )
        for conversation in workspace.conversations
    ]
    return ConversationRuntimeListResponse(
        workspace_id=workspace_id,
        current_conversation_id=workspace.current_conversation_id,
        conversation_runtimes=runtimes,
        total=len(runtimes),
    )


@router.post(
    "/{workspace_id}/conversations/{conversation_id}/runtime/start",
    response_model=ConversationRuntimeActionResponse,
)
async def start_workspace_conversation_runtime(
    workspace_id: str,
    conversation_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    runtime = _get_workspace_conversation_runtime(
        service=service,
        user_id=current_user.user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )
    if runtime.runtime_summary.get("runtime_kind") not in ("local_ipython", "uv"):
        raise HTTPException(status_code=400, detail="当前会话不支持显式开启运行态")
    if runtime.runtime_summary.get("runtime_busy"):
        raise HTTPException(status_code=409, detail="当前会话正在执行，不能开启运行态")

    from app.agents.tools.local_ipython_box import LocalIPythonBox

    workspace_dir = service._get_workspace_dir(current_user.user_id, workspace_id)
    tool = LocalIPythonBox()
    tool.workspace = workspace_dir
    tool.session_id = runtime.session_id
    await LocalIPythonBox.start_kernel(
        session_id=runtime.session_id,
        user_id=current_user.user_id,
        cwd=str(workspace_dir),
        helper_env=tool._resolve_runtime_helper_env(),
    )
    session_dir = service.session_manager._get_session_dir(
        runtime.session_id,
        current_user.user_id,
    )
    SessionExecutionJournal(session_dir, runtime.session_id).update_recovery_config(
        last_runtime_state="available"
    )

    updated_runtime = _get_workspace_conversation_runtime(
        service=service,
        user_id=current_user.user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )
    return ConversationRuntimeActionResponse(
        action="start",
        message="已准备当前会话的执行环境。",
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        session_id=runtime.session_id,
        runtime=updated_runtime,
    )


@router.post(
    "/{workspace_id}/conversations/{conversation_id}/runtime/stop",
    response_model=ConversationRuntimeActionResponse,
)
async def stop_workspace_conversation_runtime(
    workspace_id: str,
    conversation_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    service = get_workspace_registry_service()
    runtime = _get_workspace_conversation_runtime(
        service=service,
        user_id=current_user.user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )
    if runtime.runtime_summary.get("runtime_kind") not in ("local_ipython", "uv"):
        raise HTTPException(status_code=400, detail="当前会话不支持显式关闭运行态")
    if runtime.runtime_summary.get("runtime_busy"):
        raise HTTPException(status_code=409, detail="当前会话正在执行，不能关闭运行态")

    from app.agents.tools.local_ipython_box import LocalIPythonBox

    LocalIPythonBox.shutdown_kernel(session_id=runtime.session_id, user_id=current_user.user_id)
    session_dir = service.session_manager._get_session_dir(
        runtime.session_id,
        current_user.user_id,
    )
    SessionExecutionJournal(session_dir, runtime.session_id).update_recovery_config(
        last_runtime_state="discarded"
    )

    updated_runtime = _get_workspace_conversation_runtime(
        service=service,
        user_id=current_user.user_id,
        workspace_id=workspace_id,
        conversation_id=conversation_id,
    )
    return ConversationRuntimeActionResponse(
        action="stop",
        message="已释放当前会话的执行环境。",
        workspace_id=workspace_id,
        conversation_id=conversation_id,
        session_id=runtime.session_id,
        runtime=updated_runtime,
    )
