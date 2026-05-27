"""Session API 辅助函数。

从 sessions.py 提取的纯函数：验证、规范化、payload 构建。
不依赖 sessions.py 的模块级全局变量（session_manager 等通过参数传入）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from app.models.session import SessionMetadata
from app.services.runtime_tooling import canonicalize_runtime_tool_name

WORKSPACE_SUMMARY_INTERNAL_DIRS = {".aiasys"}


# ---------------------------------------------------------------------------
# Recovery policy / session status
# ---------------------------------------------------------------------------


def _compute_recovery_policy_editability(
    metadata: SessionMetadata,
    execution_summary: dict,
) -> tuple[bool, Optional[str]]:
    execution_record_count = int(execution_summary.get("execution_record_count") or 0)
    if metadata.message_count > 0 or execution_record_count > 0:
        return (
            False,
            "当前会话已开始，执行模式只能在空白草稿中修改；如需切换请新建会话。",
        )
    return True, None


def _build_session_status_payload(metadata: SessionMetadata, execution_summary: dict) -> dict:
    can_change_recovery_policy, recovery_policy_lock_reason = _compute_recovery_policy_editability(
        metadata, execution_summary
    )
    effective_recovery_policy = metadata.recovery_policy or execution_summary.get("recovery_policy")
    tasks = [task.model_dump(mode="json") for task in getattr(metadata, "tasks", []) or []]
    task_counts = {"pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0}
    for task in tasks:
        status = str(task.get("status") or "")
        if status in task_counts:
            task_counts[status] += 1

    return {
        "session_id": metadata.session_id,
        "status": metadata.status,
        "message_count": metadata.message_count,
        "code_timeout": metadata.code_timeout,
        "is_empty": metadata.message_count == 0,
        "can_edit_mcp": metadata.message_count == 0,
        "title": metadata.title,
        "has_execution_journal": bool(execution_summary.get("has_execution_journal", False)),
        "execution_record_count": int(execution_summary.get("execution_record_count") or 0),
        "last_execution_status": execution_summary.get("last_execution_status"),
        "last_execution_record_id": execution_summary.get("last_execution_record_id"),
        "recovery_policy": effective_recovery_policy,
        "idempotency_policy": execution_summary.get("idempotency_policy"),
        "requires_confirmation_for_replay": bool(
            execution_summary.get("requires_confirmation_for_replay", True)
        ),
        "last_runtime_state": execution_summary.get("last_runtime_state"),
        "rebuild_status": execution_summary.get("rebuild_status"),
        "last_replay_run_id": execution_summary.get("last_replay_run_id"),
        "last_replayed_sequences": execution_summary.get("last_replayed_sequences"),
        "last_remaining_sequences": execution_summary.get("last_remaining_sequences"),
        "last_failed_sequence": execution_summary.get("last_failed_sequence"),
        "can_change_recovery_policy": can_change_recovery_policy,
        "recovery_policy_lock_reason": recovery_policy_lock_reason,
        "enabled_expert_role_ids": getattr(metadata, "enabled_expert_role_ids", None),
        "expert_role_tool_ids": getattr(metadata, "expert_role_tool_ids", None),
        "collaboration_policy": (
            metadata.collaboration_policy.model_dump(mode="json")
            if getattr(metadata, "collaboration_policy", None) is not None
            else None
        ),
        "execution_policy": (
            metadata.execution_policy.model_dump(mode="json")
            if getattr(metadata, "execution_policy", None) is not None
            else None
        ),
        "can_edit_task_profile_now": True,
        "task_profile_effect": "next_run_only",
        "tasks": tasks,
        "task_counts": task_counts,
        "plan_state": metadata.plan_state.model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Workspace file counting
# ---------------------------------------------------------------------------


def _count_visible_workspace_files(session_dir: Path) -> int:
    if not session_dir.exists():
        return 0

    count = 0
    for file_path in session_dir.rglob("*"):
        if not file_path.is_file():
            continue
        relative_path = file_path.relative_to(session_dir).as_posix()
        if relative_path.split("/", 1)[0] in WORKSPACE_SUMMARY_INTERNAL_DIRS:
            continue
        if relative_path == "metadata.json":
            continue
        if relative_path.endswith("file_snapshots.json"):
            continue
        count += 1
    return count


# ---------------------------------------------------------------------------
# Message filtering
# ---------------------------------------------------------------------------


def _is_system_reminder_message(msg: dict) -> bool:
    """检查消息是否为 SDK 内部注入的 system-reminder 消息。

    这类消息 role 为 user，但 content 以 <system-reminder> 开头，
    是运行时注入给 Agent 的内部指令，不应展示给用户。
    """
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    if not isinstance(content, str):
        return False
    return content.strip().startswith("<system-reminder>")


def _filter_visible_history_messages(messages: list[dict]) -> list[dict]:
    """过滤仅供内部使用的 SDK 消息，保留显式 system 展示消息。"""
    return [
        msg
        for msg in messages
        if msg.get("role") not in ("_checkpoint", "_usage", "_system_prompt")
        and not _is_system_reminder_message(msg)
    ]


def _build_archived_conversation_batches(archived_batches: list[dict]) -> list[dict]:
    """为前端"查看记录"弹窗构建按维护动作分组的对话批次。"""
    conversation_batches: list[dict] = []
    for batch in archived_batches:
        visible_messages = _filter_visible_history_messages(batch.get("messages", []))
        if not visible_messages:
            continue

        archive_file = batch.get("archive_file") or batch.get("archived_at") or "unknown"
        conversation_batches.append(
            {
                "batch_id": f"context_cleared:{archive_file}",
                "type": "context_cleared",
                "archived_at": batch.get("archived_at"),
                "label": "已清理当前对话前的记录",
                "description": "以下为清理前保留的较早对话记录。",
                "messages": visible_messages,
            }
        )

    return conversation_batches


# ---------------------------------------------------------------------------
# Manual replay validation
# ---------------------------------------------------------------------------


def _validate_selected_sequences(
    selected_sequences: Optional[list[int]],
) -> Optional[list[int]]:
    if selected_sequences is None:
        return None
    if not selected_sequences:
        raise HTTPException(status_code=400, detail="selected_sequences 不能为空")
    if any(sequence <= 0 for sequence in selected_sequences):
        raise HTTPException(status_code=400, detail="selected_sequences 必须全部大于 0")
    if list(selected_sequences) != sorted(selected_sequences):
        raise HTTPException(
            status_code=400,
            detail="selected_sequences 必须按 sequence 升序提交",
        )
    if len(set(selected_sequences)) != len(selected_sequences):
        raise HTTPException(
            status_code=400,
            detail="selected_sequences 不允许重复",
        )
    return list(selected_sequences)


def _resolve_manual_replay_records(
    *,
    all_records: list[dict],
    selected_sequences: Optional[list[int]],
    upto_sequence: Optional[int],
    include_failed: bool,
) -> tuple[list[dict], list[int]]:
    records = sorted(all_records, key=lambda item: int(item.get("sequence") or 0))

    if selected_sequences is not None:
        all_sequences = [int(item.get("sequence") or 0) for item in records]
        expected_prefix = all_sequences[: len(selected_sequences)]
        if expected_prefix != selected_sequences:
            raise HTTPException(
                status_code=400,
                detail="当前版本仅支持按顺序重建到某一步，selected_sequences 必须形成连续前缀",
            )

        record_map = {int(item.get("sequence") or 0): item for item in records}
        selected_records = [record_map[sequence] for sequence in selected_sequences]
        if not include_failed:
            failed_sequences = [
                int(item.get("sequence") or 0)
                for item in selected_records
                if item.get("status") != "completed"
            ]
            if failed_sequences:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "当前版本默认不包含失败记录；若需纳入失败记录，请显式开启 include_failed"
                    ),
                )
        return selected_records, selected_sequences

    if upto_sequence is not None:
        records = [item for item in records if int(item.get("sequence") or 0) <= upto_sequence]

    if not include_failed:
        completed_prefix: list[dict] = []
        for item in records:
            if item.get("status") != "completed":
                break
            completed_prefix.append(item)
        records = completed_prefix

    return records, [int(item.get("sequence") or 0) for item in records]


def _requires_risk_acknowledgement(records: list[dict]) -> bool:
    for record in records:
        replay_risk = record.get("replay_risk") or {}
        if replay_risk.get("has_side_effect_risk"):
            return True
    return False


# ---------------------------------------------------------------------------
# User / role normalization
# ---------------------------------------------------------------------------


def _resolve_user_id(request_user_id: Optional[str], user) -> str:
    """解析最终使用的 user_id"""
    if request_user_id:
        if not user.can_access_user_data(request_user_id):
            raise HTTPException(
                status_code=403,
                detail="Access denied",
            )
        return request_user_id
    return user.user_id


def _normalize_requested_expert_role_ids(
    requested_role_ids: list[str] | None,
    available_role_ids: list[str],
) -> list[str] | None:
    if requested_role_ids is None:
        return None

    normalized_role_ids: list[str] = []
    invalid_role_ids: list[str] = []
    for role_id in requested_role_ids:
        text = str(role_id or "").strip()
        if not text:
            continue
        if text not in available_role_ids:
            if text not in invalid_role_ids:
                invalid_role_ids.append(text)
            continue
        if text not in normalized_role_ids:
            normalized_role_ids.append(text)

    if invalid_role_ids:
        raise HTTPException(
            status_code=400,
            detail=("包含无效的专家角色 ID: " + ", ".join(invalid_role_ids)),
        )

    return normalized_role_ids


def _normalize_requested_expert_role_tool_ids(
    requested_role_tool_ids: dict[str, list[str]] | None,
    available_role_tool_ids: dict[str, list[str]],
) -> dict[str, list[str]] | None:
    if requested_role_tool_ids is None:
        return None

    normalized_role_tool_ids: dict[str, list[str]] = {}
    invalid_role_ids: list[str] = []
    invalid_role_tools: dict[str, list[str]] = {}

    for raw_role_id, raw_tool_ids in requested_role_tool_ids.items():
        role_id = str(raw_role_id or "").strip()
        if not role_id:
            continue
        if role_id not in available_role_tool_ids:
            if role_id not in invalid_role_ids:
                invalid_role_ids.append(role_id)
            continue

        available_tool_ids = available_role_tool_ids[role_id]
        available_tool_id_set = set(available_tool_ids)
        requested_tool_id_set: set[str] = set()
        for raw_tool_id in raw_tool_ids or []:
            tool_id = canonicalize_runtime_tool_name(str(raw_tool_id or "").strip())
            if not tool_id:
                continue
            if tool_id not in available_tool_id_set:
                invalid_role_tools.setdefault(role_id, [])
                if tool_id not in invalid_role_tools[role_id]:
                    invalid_role_tools[role_id].append(tool_id)
                continue
            requested_tool_id_set.add(tool_id)

        selected_tool_ids = [
            tool_id for tool_id in available_tool_ids if tool_id in requested_tool_id_set
        ]
        if selected_tool_ids != available_tool_ids:
            normalized_role_tool_ids[role_id] = selected_tool_ids

    if invalid_role_ids or invalid_role_tools:
        detail_parts: list[str] = []
        if invalid_role_ids:
            detail_parts.append("包含无效的专家角色 ID: " + ", ".join(invalid_role_ids))
        for role_id, tool_ids in invalid_role_tools.items():
            detail_parts.append(f"角色 {role_id} 包含无效工具 ID: " + ", ".join(tool_ids))
        raise HTTPException(status_code=400, detail="；".join(detail_parts))

    return normalized_role_tool_ids or None


# ---------------------------------------------------------------------------
# SubAgent helpers
# ---------------------------------------------------------------------------


def _build_subagent_role_projection(
    *,
    route_context: dict[str, object],
    agent_id: str | None,
) -> dict[str, object]:
    control_state = route_context.get("control_state")
    conversation_type = route_context.get("conversation_type")
    session_id = route_context.get("session_id")
    control_hosting_agent_id = getattr(control_state, "hosting_agent_id", None)
    control_hosting_session_id = getattr(control_state, "hosting_session_id", None)
    hosting_controller = bool(
        isinstance(agent_id, str)
        and agent_id
        and control_hosting_agent_id == agent_id
        and (control_hosting_session_id == session_id or conversation_type == "hosting_agent")
    )
    node_role = "hosting_controller" if hosting_controller else "collaboration_node"
    return {
        "workspace_id": route_context.get("workspace_id"),
        "bound_host_session_id": route_context.get("bound_host_session_id"),
        "node_role": node_role,
        "hosting_controller": hosting_controller,
    }


def _materialize_subagent_ownership(
    ownership: object,
    *,
    fallback_host_session_id: str,
    fallback_parent_tool_call_id: str | None,
    fallback_agent_id: str,
    fallback_subagent_type: str,
    bound_host_session_id: str | None = None,
) -> dict[str, object]:
    if isinstance(ownership, dict):
        payload = dict(ownership)
    else:
        payload = {
            "host_session_id": getattr(ownership, "host_session_id", fallback_host_session_id),
            "parent_tool_call_id": getattr(
                ownership, "parent_tool_call_id", fallback_parent_tool_call_id
            ),
            "agent_id": getattr(ownership, "agent_id", fallback_agent_id),
            "subagent_type": getattr(ownership, "subagent_type", fallback_subagent_type),
        }

    payload.setdefault("host_session_id", fallback_host_session_id)
    payload.setdefault("parent_tool_call_id", fallback_parent_tool_call_id)
    payload.setdefault("agent_id", fallback_agent_id)
    payload.setdefault("subagent_type", fallback_subagent_type)
    if bound_host_session_id:
        payload["bound_host_session_id"] = bound_host_session_id
    return payload
