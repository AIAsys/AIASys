import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.auth import require_auth
from app.core.config import WORKSPACE_DIR
from app.models.session import SessionMetadata
from app.models.user import UserInfo
from app.services.agent import agent_service
from app.services.expert_roles import get_session_expert_policy
from app.services.history import SessionExecutionJournal
from app.services.session import SessionManager
from app.services.tracking import SubAgentTrackingService, get_subagent_tracking_service
from app.services.workspace_registry import get_workspace_registry_service

from .sessions_helpers import (
    _build_archived_conversation_batches,
    _build_session_status_payload,
    _build_subagent_role_projection,
    _compute_recovery_policy_editability,
    _filter_visible_history_messages,
    _materialize_subagent_ownership,
    _requires_risk_acknowledgement,
    _resolve_manual_replay_records,
    _validate_selected_sequences,
)
from .sessions_models import (
    ManualReplayRequest,
    RewriteMessageRequest,
    UpdateRecoveryPolicyRequest,
)

logger = logging.getLogger(__name__)
CLEAR_CONTEXT_MARKER_TEXT = "当前会话已清理，后续回复不会继承以上上下文。"
session_manager = SessionManager(WORKSPACE_DIR)

router = APIRouter(prefix="/sessions", tags=["sessions"])


def _is_runtime_busy(user_id: str, session_id: str) -> bool:
    session_key = f"{user_id}/{session_id}"
    session_lock = getattr(agent_service, "_session_locks", {}).get(session_key)
    return bool(session_lock and session_lock.locked())


async def _manual_replay_records(
    *,
    user_id: str,
    session_id: str,
    session_dir,
    metadata: SessionMetadata,
    records: list[dict],
    restart_runtime: bool,
) -> dict:
    from app.agents.tools.local_ipython_box import (
        LocalIPythonBox,
        LocalIPythonBoxParams,
    )

    replayed_sequences: list[int] = []
    failed_sequence: int | None = None
    failed_error: str | None = None

    if restart_runtime:
        LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)

    tool = LocalIPythonBox()
    tool.workspace = session_dir
    tool.session_id = session_id
    tool.record_execution = False

    for record in records:
        result = await tool.invoke(
            **LocalIPythonBoxParams(
                code=record["code"],
                restart=False,
            ).model_dump()
        )
        if getattr(result, "is_error", False):
            failed_sequence = record.get("sequence")
            failed_error = getattr(result, "message", None) or getattr(
                result,
                "brief",
                None,
            )
            break
        replayed_sequences.append(int(record.get("sequence") or 0))

    return {
        "replayed_sequences": replayed_sequences,
        "failed_sequence": failed_sequence,
        "error": failed_error,
        "completed": failed_sequence is None,
    }


def _get_session_owner_from_metadata(
    session_manager,
    session_id: str,
    user_id: str,
) -> str | None:
    try:
        metadata = session_manager.get_session(session_id, user_id)
        if metadata and hasattr(metadata, "user_id") and metadata.user_id:
            return metadata.user_id
    except Exception as exc:
        logger.warning("获取会话 owner 失败: %s/%s: %s", user_id, session_id, exc)
    return None


def _read_subagent_control_excerpt(
    user_id: str,
    session_id: str,
    agent_id: str,
    filename: str,
    *,
    limit: int = 2000,
) -> str | None:
    from app.services.tracking import _get_session_subagents_dir

    path = _get_session_subagents_dir(user_id, session_id) / agent_id / filename
    try:
        if not path.exists() or not path.is_file():
            return None
        text = path.read_text(encoding="utf-8").strip()
    except Exception:
        logger.warning("读取协作节点控制摘要失败: %s", path)
        return None

    if not text:
        return None
    return text[:limit]


def _get_hosting_binding_for_session(
    *,
    user_id: str,
    session_id: str,
):
    workspace_registry = get_workspace_registry_service()
    workspace_id = workspace_registry.find_workspace_id_by_session_id(
        user_id,
        session_id,
    )
    if not workspace_id:
        return None, None, None
    workspace_root = workspace_registry.get_workspace_root(user_id, workspace_id)
    return workspace_id, workspace_root, None


def _get_subagent_route_context(
    *,
    user_id: str,
    session_id: str,
) -> dict[str, object]:
    workspace_id, _, control_state = _get_hosting_binding_for_session(
        user_id=user_id,
        session_id=session_id,
    )
    bound_host_session_id = None
    conversation_type = None
    try:
        metadata = session_manager.get_session(session_id, user_id)
        bound_host_session_id = getattr(metadata, "bound_host_session_id", None)
        conversation_type = getattr(metadata, "conversation_type", None)
    except Exception:
        pass

    return {
        "session_id": session_id,
        "workspace_id": workspace_id,
        "control_state": control_state,
        "bound_host_session_id": bound_host_session_id,
        "conversation_type": conversation_type,
    }


def _get_tracking_service() -> SubAgentTrackingService:
    return get_subagent_tracking_service()


def _build_role_tool_names(tool_ids: list[str]) -> list[str]:
    tool_names: list[str] = []
    for tool_id in tool_ids:
        short_name = str(tool_id or "").split(":")[-1].strip()
        if short_name and short_name not in tool_names:
            tool_names.append(short_name)
    return tool_names


def _build_role_summary_payload(
    role: object,
    *,
    effective_tool_ids: list[str] | None,
) -> dict[str, object]:
    if hasattr(role, "model_dump"):
        payload = role.model_dump(mode="json")
    else:
        payload = {
            "role_id": str(getattr(role, "role_id", "") or "").strip(),
            "display_name": str(getattr(role, "display_name", "") or "").strip(),
            "description": str(getattr(role, "description", "") or "").strip(),
            "when_to_use": str(getattr(role, "when_to_use", "") or "").strip(),
            "default_model": getattr(role, "default_model", None),
            "tool_policy": str(getattr(role, "tool_policy", "allowlist") or "allowlist"),
            "tool_ids": list(getattr(role, "tool_ids", []) or []),
            "tool_names": list(getattr(role, "tool_names", []) or []),
            "tool_count": int(getattr(role, "tool_count", 0) or 0),
            "permissions": list(getattr(role, "permissions", []) or []),
            "capabilities": list(getattr(role, "capabilities", []) or []),
            "supports_background": bool(getattr(role, "supports_background", True)),
            "agent_file": str(getattr(role, "agent_file", "") or "").strip(),
            "source": str(getattr(role, "source", "system") or "system"),
        }

    original_tool_policy = str(payload.get("tool_policy") or "allowlist")
    original_tool_ids = list(payload.get("tool_ids") or [])
    resolved_tool_ids = (
        list(effective_tool_ids) if effective_tool_ids is not None else original_tool_ids
    )
    payload["tool_ids"] = resolved_tool_ids
    payload["tool_names"] = _build_role_tool_names(resolved_tool_ids)
    payload["tool_count"] = len(payload["tool_names"])
    payload["tool_policy"] = (
        "inherit" if original_tool_policy == "inherit" and not resolved_tool_ids else "allowlist"
    )
    return payload


def _build_session_role_summary_map(
    *,
    user_id: str,
    session_id: str,
) -> dict[str, dict[str, object]]:
    try:
        policy = get_session_expert_policy(
            user_id=user_id,
            session_id=session_id,
        )
    except FileNotFoundError:
        return {}
    except Exception:
        logger.warning(
            "构建协作节点角色摘要失败: user=%s session=%s",
            user_id,
            session_id,
            exc_info=True,
        )
        return {}

    role_summary_map: dict[str, dict[str, object]] = {}
    effective_role_tool_ids = getattr(policy, "effective_role_tool_ids", {}) or {}
    for role in getattr(policy, "available_roles", []) or []:
        role_id = str(getattr(role, "role_id", "") or "").strip()
        if not role_id:
            continue
        role_summary_map[role_id] = _build_role_summary_payload(
            role,
            effective_tool_ids=effective_role_tool_ids.get(role_id),
        )
    return role_summary_map


def _attach_subagent_role_summary(
    payload: dict[str, object],
    *,
    role_summary_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    role_id = str(payload.get("subagent_type") or "").strip()
    payload["role_summary"] = role_summary_map.get(role_id)
    return payload


@router.get("/{user_id}/{session_id}/execution-records")
async def get_session_execution_records(
    user_id: str,
    session_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    """获取 session execution journal 记录。"""
    # 首先尝试从 session metadata 获取真实的 owner user_id
    # 这解决了前端 user_id 与 session 实际 owner 不一致的问题
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        # metadata 未写 owner 时，按路径中的 user_id 查找。
        actual_user_id = user_id

    # 权限检查使用实际的 owner user_id
    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only access your own execution records",
        )

    try:
        metadata = session_manager.get_session(session_id, actual_user_id)
        if not metadata:
            metadata = session_manager.create_session(
                session_id=session_id,
                user_id=actual_user_id,
                title="新会话",
                env_id=None,
                sandbox_mode=None,
            )
            logger.info(
                "[AutoCreate] execution-records 自动创建草稿: %s/%s",
                actual_user_id,
                session_id,
            )

        execution_summary = session_manager.get_execution_summary(session_id, actual_user_id)
        records = session_manager.get_execution_records(
            session_id,
            actual_user_id,
            limit=limit,
        )
        maintenance_markers = session_manager.list_execution_maintenance_markers(
            session_id,
            actual_user_id,
        )
        return {
            "user_id": actual_user_id,
            "session_id": session_id,
            "summary": _build_session_status_payload(metadata, execution_summary),
            "records": records,
            "maintenance_markers": maintenance_markers,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 execution journal 失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.post("/{user_id}/{session_id}/recovery-policy")
async def update_session_recovery_policy(
    user_id: str,
    session_id: str,
    request: UpdateRecoveryPolicyRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新 session 的执行恢复策略。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only update your own recovery policy",
        )

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        can_change_recovery_policy, lock_reason = _compute_recovery_policy_editability(
            metadata,
            execution_summary,
        )
        if not can_change_recovery_policy:
            raise HTTPException(
                status_code=409,
                detail=lock_reason or "当前会话不允许切换执行模式",
            )

        ok = session_manager.update_session_recovery_policy(
            session_id,
            user_id,
            request.recovery_policy,
        )
        if not ok:
            raise HTTPException(status_code=500, detail="更新恢复策略失败")

        updated_metadata = session_manager.get_session(session_id, user_id)
        if request.recovery_policy == "discard" and updated_metadata:
            from app.agents.tools.local_ipython_box import LocalIPythonBox
            from app.services.history import SessionExecutionJournal

            session_dir = session_manager._get_session_dir(session_id, user_id)
            LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)
            SessionExecutionJournal(session_dir, session_id).update_recovery_config(
                last_runtime_state="discarded"
            )

        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        return {
            "success": True,
            "session": _build_session_status_payload(
                updated_metadata or metadata,
                execution_summary,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新恢复策略失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.get("/{user_id}/{session_id}/recovery-policy")
async def get_session_recovery_policy(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取 session 的执行恢复策略摘要。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only access your own recovery policy",
        )

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        can_change_recovery_policy, lock_reason = _compute_recovery_policy_editability(
            metadata,
            execution_summary,
        )
        effective_recovery_policy = metadata.recovery_policy or execution_summary.get(
            "recovery_policy"
        )

        return {
            "session_id": session_id,
            "recovery_policy": effective_recovery_policy,
            "can_change_recovery_policy": can_change_recovery_policy,
            "recovery_policy_lock_reason": lock_reason,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取恢复策略失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.post("/{user_id}/{session_id}/manual-replay")
async def manual_replay_session_records(
    user_id: str,
    session_id: str,
    request: ManualReplayRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """按 execution journal 显式重放 session 执行记录。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only replay your own execution records",
        )

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        recovery_policy = metadata.recovery_policy or execution_summary.get("recovery_policy")
        if recovery_policy != "manual_replay":
            raise HTTPException(
                status_code=409,
                detail="当前 recovery_policy 不是 manual_replay，不能执行手动重放",
            )

        selected_sequences = _validate_selected_sequences(request.selected_sequences)
        records, source_sequences = _resolve_manual_replay_records(
            all_records=session_manager.get_execution_records(
                session_id,
                user_id,
                limit=1000,
            ),
            selected_sequences=selected_sequences,
            upto_sequence=request.upto_sequence,
            include_failed=request.include_failed,
        )

        if not records:
            raise HTTPException(status_code=400, detail="没有可重放的 execution records")
        if _requires_risk_acknowledgement(records) and not request.risk_acknowledged:
            raise HTTPException(
                status_code=400,
                detail="当前选择包含可能重复产生副作用的步骤，请先确认风险后再重建",
            )

        session_dir = session_manager._get_session_dir(session_id, user_id)
        replay_started_at = datetime.now().isoformat()
        replay_result = await _manual_replay_records(
            user_id=user_id,
            session_id=session_id,
            session_dir=session_dir,
            metadata=metadata,
            records=records,
            restart_runtime=request.restart_runtime,
        )
        replay_finished_at = datetime.now().isoformat()
        remaining_sequences = [
            sequence
            for sequence in source_sequences
            if sequence not in set(replay_result["replayed_sequences"])
        ]
        rebuild_status = "completed" if replay_result["completed"] else "partial_failed"
        journal = SessionExecutionJournal(session_dir, session_id)
        replay_audit = journal.append_replay_run(
            started_at=replay_started_at,
            finished_at=replay_finished_at,
            source_sequences=source_sequences,
            recovery_policy=recovery_policy,
            sandbox_mode=metadata.sandbox_mode,
            env_id=metadata.env_id,
            restart_runtime=request.restart_runtime,
            include_failed=request.include_failed,
            risk_acknowledged=request.risk_acknowledged,
            upto_sequence=request.upto_sequence,
            selected_sequences=selected_sequences,
            replayed_sequences=replay_result["replayed_sequences"],
            remaining_sequences=remaining_sequences,
            rebuild_status=rebuild_status,
            completed=replay_result["completed"],
            failed_sequence=replay_result["failed_sequence"],
            error=replay_result["error"],
        )
        journal.update_recovery_config(
            last_runtime_state=("available" if replay_result["completed"] else "failed"),
            last_rebuild_status=rebuild_status,
            last_replay_run_id=replay_audit["replay_run_id"],
            last_replayed_sequences=replay_result["replayed_sequences"],
            last_remaining_sequences=remaining_sequences,
            last_failed_sequence=replay_result["failed_sequence"],
        )

        updated_metadata = session_manager.get_session(session_id, user_id)
        updated_summary = session_manager.get_execution_summary(session_id, user_id)
        return {
            "success": replay_result["completed"],
            "rebuild_status": rebuild_status,
            "replayed_count": len(replay_result["replayed_sequences"]),
            "replayed_sequences": replay_result["replayed_sequences"],
            "remaining_sequences": remaining_sequences,
            "failed_sequence": replay_result["failed_sequence"],
            "error": replay_result["error"],
            "replay_run_id": replay_audit["replay_run_id"],
            "session": _build_session_status_payload(
                updated_metadata or metadata,
                updated_summary,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动重放 execution journal 失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.post("/{user_id}/{session_id}/reset-history")
async def reset_session_history(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """清理旧历史对话与 execution 记录，按最新结构重建 session sidecar。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only reset your own sessions",
        )

    try:
        from app.agents.tools.local_ipython_box import LocalIPythonBox

        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        try:
            await agent_service.stop_session(user_id, session_id)
        except Exception as stop_err:
            logger.warning("重置 session 前中断会话失败（继续）: %s", stop_err)

        LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)

        session_manager.reset_session_history(session_id, user_id)
        updated_metadata = session_manager.get_session(session_id, user_id)
        if not updated_metadata:
            raise HTTPException(status_code=500, detail="重置后会话状态丢失")

        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        return {
            "success": True,
            "session": _build_session_status_payload(
                updated_metadata,
                execution_summary,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置会话历史失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.post("/{user_id}/{session_id}/rewrite-from-message")
async def rewrite_session_from_message(
    user_id: str,
    session_id: str,
    request: RewriteMessageRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """重写指定用户消息，并截断其后的当前聊天上下文。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only update your own sessions",
        )

    try:
        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        if _is_runtime_busy(user_id, session_id):
            raise HTTPException(status_code=409, detail="当前会话正在执行，不能编辑重发")

        if not request.preserve_attachments:
            raise HTTPException(status_code=400, detail="当前版本必须保留原附件引用")

        try:
            await agent_service.stop_session(user_id, session_id)
        except Exception as stop_err:
            logger.warning("重写消息前停止运行态失败（继续）: %s", stop_err)

        rewrite_result = session_manager.rewrite_history_from_message(
            session_id=session_id,
            user_id=user_id,
            message_id=request.message_id,
            content=request.content,
            confirm_drop_tail=request.confirm_drop_tail,
        )
        updated_metadata = session_manager.get_session(session_id, user_id)
        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        current_messages = _filter_visible_history_messages(rewrite_result.get("messages", []))
        current_messages = session_manager.assign_history_message_ids(
            session_id,
            current_messages,
        )

        return {
            "success": True,
            "message_id": rewrite_result["message_id"],
            "dropped_count": rewrite_result["dropped_count"],
            "archive": rewrite_result.get("archive"),
            "messages": current_messages,
            "current_messages": current_messages,
            "session": _build_session_status_payload(
                updated_metadata or metadata,
                execution_summary,
            ),
        }
    except HTTPException:
        raise
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as e:
        logger.error(f"重写会话消息失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.post("/{user_id}/{session_id}/rebuild-runtime")
async def rebuild_session_runtime(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """仅重建当前 session 的运行态，不清理对话历史与执行记录。"""
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(
            status_code=403,
            detail="You can only rebuild your own sessions",
        )

    try:
        from app.agents.tools.local_ipython_box import LocalIPythonBox
        from app.services.history import SessionExecutionJournal

        metadata = session_manager.get_session(session_id, user_id)
        if not metadata:
            raise HTTPException(status_code=404, detail="会话不存在")

        try:
            await agent_service.stop_session(user_id, session_id)
        except Exception as stop_err:
            logger.warning("重置代码运行态前中断会话失败（继续）: %s", stop_err)

        LocalIPythonBox.shutdown_kernel(session_id=session_id, user_id=user_id)

        session_dir = session_manager._get_session_dir(session_id, user_id)
        SessionExecutionJournal(session_dir, session_id).update_recovery_config(
            last_runtime_state="refresh_required"
        )

        updated_metadata = session_manager.get_session(session_id, user_id)
        execution_summary = session_manager.get_execution_summary(session_id, user_id)
        return {
            "success": True,
            "session": _build_session_status_payload(
                updated_metadata or metadata,
                execution_summary,
            ),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"重置代码运行态失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.get("/history/{user_id}/{session_id}")
async def get_session_history(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取 Agent 会话历史记录

    返回以 SDK `context.jsonl` 为基础的历史数据，并为用户消息补充
    `display_content` 等 UI 展示字段；系统内部消息（`_checkpoint`, `_usage`）
    会在这里被过滤掉。保留显式的 `system` 展示消息，例如“当前会话已清理”分隔线。
    """
    # 检查是否有权访问该用户的历史
    if not current_user.can_access_user_data(user_id):
        raise HTTPException(status_code=403, detail="You can only access your own history")

    try:
        # 获取 SDK 的消息历史（原始格式）
        archived_batches = session_manager.list_cleared_context_archives(
            session_id,
            user_id,
        )
        sdk_history = await agent_service.get_session_history(user_id, session_id)
        current_messages = _filter_visible_history_messages(sdk_history)
        current_messages = session_manager.assign_history_message_ids(
            session_id,
            current_messages,
        )
        conversation_batches = _build_archived_conversation_batches(archived_batches)

        messages = []
        for batch in conversation_batches:
            archived_messages = batch.get("messages", [])
            archived_messages = session_manager.assign_history_message_ids(
                session_id,
                archived_messages,
            )
            messages.extend(archived_messages)
            messages.append(
                {
                    "role": "system",
                    "content": CLEAR_CONTEXT_MARKER_TEXT,
                    "display_content": CLEAR_CONTEXT_MARKER_TEXT,
                    "timestamp": batch.get("archived_at"),
                }
            )

        # 只过滤掉系统内部消息，保留用于 UI 展示的 system 分隔线
        messages.extend(current_messages)

        # 直接返回原始格式
        return {
            "user_id": user_id,
            "session_id": session_id,
            "messages": messages,
            "current_messages": current_messages,
            "archived_batches": conversation_batches,
            "can_resume": len(messages) > 0,
        }
    except Exception as e:
        logger.error(f"获取历史失败: {e}")
        import traceback

        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail="Operation failed")


@router.get("/{user_id}/{session_id}/execution-tree")
async def get_execution_tree(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """
    获取 Host Agent 执行树

    返回 Host Agent 状态和 Sub Agents 列表（用于执行流概览）
    """
    # 首先尝试从 session metadata 获取真实的 owner user_id
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    try:
        # 获取 Host Agent 的 events 来解析状态
        from app.services.agent import agent_service

        host_events = await agent_service.get_session_execution_events(actual_user_id, session_id)
        route_context = _get_subagent_route_context(
            user_id=actual_user_id,
            session_id=session_id,
        )
        role_summary_map = _build_session_role_summary_map(
            user_id=actual_user_id,
            session_id=session_id,
        )

        tree = tracking_service.get_execution_tree(
            user_id=actual_user_id,
            session_id=session_id,
            host_events=host_events,
        )
        subagent_calls: list[dict[str, object]] = []
        for raw_call in tree.subagent_calls:
            call = dict(raw_call)
            raw_subagent = call.get("subagent") or {}
            subagent = dict(raw_subagent) if isinstance(raw_subagent, dict) else {}
            ownership_payload = _materialize_subagent_ownership(
                subagent.get("ownership"),
                fallback_host_session_id=session_id,
                fallback_parent_tool_call_id=(
                    call.get("parent_tool_call_id")
                    if isinstance(call.get("parent_tool_call_id"), str)
                    else (
                        call.get("tool_call_id")
                        if isinstance(call.get("tool_call_id"), str)
                        else None
                    )
                ),
                fallback_agent_id=str(subagent.get("agent_id") or subagent.get("id") or ""),
                fallback_subagent_type=str(
                    subagent.get("subagent_type") or subagent.get("name") or "unknown"
                ),
                bound_host_session_id=route_context.get("bound_host_session_id"),
            )
            role_projection = _build_subagent_role_projection(
                route_context=route_context,
                agent_id=str(ownership_payload.get("agent_id") or ""),
            )
            parent_tool_call_id = ownership_payload.get("parent_tool_call_id")

            subagent.update(
                {
                    "id": ownership_payload.get("agent_id") or subagent.get("id"),
                    "agent_id": ownership_payload.get("agent_id"),
                    "subagent_type": ownership_payload.get("subagent_type"),
                    "host_session_id": ownership_payload.get("host_session_id"),
                    "bound_host_session_id": ownership_payload.get("bound_host_session_id"),
                    "parent_tool_call_id": parent_tool_call_id,
                    "ownership": ownership_payload,
                    "workspace_id": role_projection.get("workspace_id"),
                    "node_role": role_projection.get("node_role"),
                    "hosting_controller": role_projection.get("hosting_controller"),
                }
            )
            _attach_subagent_role_summary(
                subagent,
                role_summary_map=role_summary_map,
            )

            call["tool_call_id"] = call.get("tool_call_id") or parent_tool_call_id or ""
            call["parent_tool_call_id"] = parent_tool_call_id
            call["subagent"] = subagent
            subagent_calls.append(call)

        result = {
            "host": {
                "status": tree.host_status,
                "current_step": tree.host_current_step,
                "total_steps": tree.host_total_steps,
                "session_id": session_id,
                "workspace_id": route_context.get("workspace_id"),
                "bound_host_session_id": route_context.get("bound_host_session_id"),
            },
            "subagent_calls": subagent_calls,
        }
        logger.debug("Execution tree result: %s subagents", len(tree.subagent_calls))
        return result
    except Exception as e:
        logger.error(f"获取执行树失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.get("/{user_id}/{session_id}/host-events")
async def get_host_events(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """
    获取 Host Agent 自己的执行事件（不含 Sub Agent 内部事件）
    """
    # 首先尝试从 session metadata 获取真实的 owner user_id
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    try:
        from app.services.agent import agent_service

        # 获取 Host Agent 的完整事件流
        events = await agent_service.get_session_execution_events(actual_user_id, session_id)

        # 过滤掉 Sub Agent 内部事件（保留 SubagentEvent 本身，但不展开内部）
        filtered_events = []
        for event in events:
            event_type = str(event.get("type", "") or "")
            if event_type.startswith("subagent_"):
                continue
            if event_type == "worker.lifecycle.changed" and event.get("scope") == "subagent":
                continue
            filtered_events.append(event)

        return {
            "events": filtered_events,
            "total": len(filtered_events),
        }
    except Exception as e:
        logger.error(f"获取 Host 事件失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.get("/{user_id}/{session_id}/subagents")
async def list_subagents(
    user_id: str,
    session_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """
    列出会话中的所有 Sub Agents
    """
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    try:
        route_context = _get_subagent_route_context(
            user_id=actual_user_id,
            session_id=session_id,
        )
        role_summary_map = _build_session_role_summary_map(
            user_id=actual_user_id,
            session_id=session_id,
        )
        summaries = tracking_service.list_subagents(actual_user_id, session_id)
        subagent_payloads: list[dict[str, object]] = []
        for summary in summaries:
            ownership_payload = _materialize_subagent_ownership(
                summary.ownership,
                fallback_host_session_id=session_id,
                fallback_parent_tool_call_id=summary.task_tool_call_id or None,
                fallback_agent_id=summary.id,
                fallback_subagent_type=summary.name or "unknown",
                bound_host_session_id=route_context.get("bound_host_session_id"),
            )
            role_projection = _build_subagent_role_projection(
                route_context=route_context,
                agent_id=summary.id,
            )
            subagent_payloads.append(
                _attach_subagent_role_summary(
                    {
                        "id": ownership_payload.get("agent_id") or summary.id,
                        "agent_id": ownership_payload.get("agent_id"),
                        "name": summary.name,
                        "status": summary.status,
                        "description": summary.description,
                        "subagent_type": ownership_payload.get("subagent_type"),
                        "host_session_id": ownership_payload.get("host_session_id"),
                        "bound_host_session_id": ownership_payload.get("bound_host_session_id"),
                        "parent_tool_call_id": ownership_payload.get("parent_tool_call_id"),
                        "ownership": ownership_payload,
                        "workspace_id": role_projection.get("workspace_id"),
                        "node_role": role_projection.get("node_role"),
                        "hosting_controller": role_projection.get("hosting_controller"),
                        "progress": summary.progress,
                        "duration_ms": summary.duration_ms,
                        "created_at": summary.created_at,
                        "updated_at": summary.updated_at,
                    },
                    role_summary_map=role_summary_map,
                )
            )
        return {
            "subagents": subagent_payloads,
            "total": len(summaries),
        }
    except Exception as e:
        logger.error(f"列出 Sub Agents 失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


@router.get("/{user_id}/{session_id}/subagents/{agent_id}")
async def get_subagent_detail(
    user_id: str,
    session_id: str,
    agent_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """
    获取 Sub Agent 完整详情（包括事件流和输出文件）
    """
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    try:
        detail = tracking_service.get_subagent_detail(actual_user_id, session_id, agent_id)
        if not detail:
            raise HTTPException(status_code=404, detail="Sub Agent not found")
        route_context = _get_subagent_route_context(
            user_id=actual_user_id,
            session_id=session_id,
        )
        role_summary_map = _build_session_role_summary_map(
            user_id=actual_user_id,
            session_id=session_id,
        )
        ownership_payload = _materialize_subagent_ownership(
            detail.ownership,
            fallback_host_session_id=session_id,
            fallback_parent_tool_call_id=None,
            fallback_agent_id=detail.id,
            fallback_subagent_type=detail.name or "unknown",
            bound_host_session_id=route_context.get("bound_host_session_id"),
        )
        role_projection = _build_subagent_role_projection(
            route_context=route_context,
            agent_id=str(ownership_payload.get("agent_id") or detail.id),
        )
        return _attach_subagent_role_summary(
            {
                "id": ownership_payload.get("agent_id") or detail.id,
                "agent_id": ownership_payload.get("agent_id"),
                "name": detail.name,
                "status": detail.status,
                "description": detail.description,
                "subagent_type": ownership_payload.get("subagent_type"),
                "host_session_id": ownership_payload.get("host_session_id"),
                "bound_host_session_id": ownership_payload.get("bound_host_session_id"),
                "parent_tool_call_id": ownership_payload.get("parent_tool_call_id"),
                "ownership": ownership_payload,
                "workspace_id": role_projection.get("workspace_id"),
                "node_role": role_projection.get("node_role"),
                "hosting_controller": role_projection.get("hosting_controller"),
                "duration_ms": detail.duration_ms,
                "created_at": detail.created_at,
                "updated_at": detail.updated_at,
                "meta": detail.meta,
                "events": detail.events,
                "context": detail.context,
                "output_files": detail.output_files,
            },
            role_summary_map=role_summary_map,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Sub Agent 详情失败: {e}")
        raise HTTPException(status_code=500, detail="Operation failed")


# hosting-controller 只作为协作节点角色保留，不再提供单独控制端点。


@router.post("/{user_id}/{session_id}/subagents/{agent_id}/stop")
async def stop_subagent(
    user_id: str,
    session_id: str,
    agent_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """
    停止运行中的 Sub Agent
    """
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(actual_user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    try:
        result = await agent_service.stop_subagent_execution(
            user_id=actual_user_id,
            session_id=session_id,
            agent_id=agent_id,
            subagent_status=detail.meta.get("status"),
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Operation failed") from exc
    except Exception as exc:
        logger.error("停止 Sub Agent 失败: %s", exc)
        raise HTTPException(status_code=500, detail="Operation failed") from exc


@router.post("/{user_id}/{session_id}/subagents/{agent_id}/retry")
async def retry_subagent(
    user_id: str,
    session_id: str,
    agent_id: str,
    current_user: UserInfo = Depends(require_auth()),
    tracking_service: SubAgentTrackingService = Depends(_get_tracking_service),
):
    """
    重试失败的 Sub Agent
    """
    actual_user_id = _get_session_owner_from_metadata(session_manager, session_id, user_id)
    if not actual_user_id:
        actual_user_id = user_id

    if not current_user.can_access_user_data(actual_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own sessions")

    detail = tracking_service.get_subagent_detail(actual_user_id, session_id, agent_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Sub Agent not found")

    prompt_excerpt = _read_subagent_control_excerpt(
        actual_user_id,
        session_id,
        agent_id,
        "prompt.txt",
    )
    output_excerpt = _read_subagent_control_excerpt(
        actual_user_id,
        session_id,
        agent_id,
        "output",
    )

    try:
        result = await agent_service.retry_subagent_execution(
            user_id=actual_user_id,
            session_id=session_id,
            agent_id=agent_id,
            description=detail.description or detail.name,
            subagent_status=detail.meta.get("status"),
            prompt_excerpt=prompt_excerpt,
            output_excerpt=output_excerpt,
        )
        return result
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail="Operation failed") from exc
    except Exception as exc:
        logger.error("重试 Sub Agent 失败: %s", exc)
        raise HTTPException(status_code=500, detail="Operation failed") from exc
