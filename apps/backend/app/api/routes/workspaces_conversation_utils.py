"""
任务工作区与对话主接口
"""

from __future__ import annotations

import logging

from fastapi import HTTPException

from app.api.routes.workspaces_runtime_utils import (
    _is_runtime_busy,
    _resolve_runtime_control_capability,
)
from app.models.workspace import (
    WorkspaceConversationRuntimeSummary,
    WorkspaceConversationSummary,
)
from app.services.runtime.session_runtime_state import build_session_runtime_summary

logger = logging.getLogger(__name__)


def _build_workspace_conversation_runtime_summary(
    *,
    service,
    user_id: str,
    workspace_id: str,
    current_conversation_id: str | None,
    conversation: WorkspaceConversationSummary,
) -> WorkspaceConversationRuntimeSummary:
    metadata = service.session_manager.get_session(conversation.session_id, user_id)
    execution_summary = service.session_manager.get_execution_summary(
        conversation.session_id,
        user_id,
    )
    session_dir = service.session_manager._get_session_dir(
        conversation.session_id,
        user_id,
    )
    runtime_summary = build_session_runtime_summary(
        session_dir=session_dir,
        session_id=conversation.session_id,
        user_id=user_id,
        sandbox_mode=getattr(metadata, "sandbox_mode", None),
        env_id=getattr(metadata, "env_id", None),
        last_runtime_state=execution_summary.get("last_runtime_state"),
        runtime_busy=_is_runtime_busy(user_id, conversation.session_id),
    )
    can_start_runtime, can_stop_runtime, runtime_control_reason = (
        _resolve_runtime_control_capability(runtime_summary)
    )

    return WorkspaceConversationRuntimeSummary(
        workspace_id=workspace_id,
        conversation_id=conversation.conversation_id,
        session_id=conversation.session_id,
        title=conversation.title,
        updated_at=conversation.updated_at,
        source=conversation.source,
        conversation_type=conversation.conversation_type,
        bound_host_session_id=conversation.bound_host_session_id,
        execution_policy=conversation.execution_policy,
        status=conversation.status,
        message_count=conversation.message_count,
        execution_record_count=conversation.execution_record_count or 0,
        last_runtime_state=execution_summary.get("last_runtime_state"),
        runtime_summary=runtime_summary,
        can_start_runtime=can_start_runtime,
        can_stop_runtime=can_stop_runtime,
        runtime_control_reason=runtime_control_reason,
        is_current=conversation.conversation_id == current_conversation_id,
    )


def _build_automation_conversation_projection(
    conversation: WorkspaceConversationSummary,
) -> dict:
    return {
        "conversation_id": conversation.conversation_id,
        "session_id": conversation.session_id,
        "title": conversation.title,
        "status": conversation.status,
        "updated_at": conversation.updated_at,
        "source": conversation.source,
        "conversation_type": conversation.conversation_type,
        "bound_host_session_id": conversation.bound_host_session_id,
        "execution_policy_mode": conversation.execution_policy.mode.value,
        "automation_continuation_id": conversation.automation_continuation_id,
        "automation_continuation_target_kind": conversation.automation_continuation_target_kind,
    }


def _get_workspace_conversation_runtime(
    *,
    service,
    user_id: str,
    workspace_id: str,
    conversation_id: str,
) -> WorkspaceConversationRuntimeSummary:
    workspace = service.get_workspace(
        user_id,
        workspace_id,
        include_conversations=True,
    )
    for conversation in workspace.conversations:
        if conversation.conversation_id != conversation_id:
            continue
        return _build_workspace_conversation_runtime_summary(
            service=service,
            user_id=user_id,
            workspace_id=workspace_id,
            current_conversation_id=workspace.current_conversation_id,
            conversation=conversation,
        )
    raise HTTPException(status_code=404, detail="会话不存在")
