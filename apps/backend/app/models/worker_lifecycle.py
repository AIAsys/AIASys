"""Worker lifecycle 结束事件投影。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

WorkerLifecycleScope = Literal["host", "subagent"]
WorkerLifecycleStatus = Literal["finished", "cancelled", "interrupted", "failed"]


@dataclass(frozen=True)
class WorkerLifecycleProjection:
    status: WorkerLifecycleStatus
    reason: str


def build_worker_lifecycle_event(
    *,
    scope: WorkerLifecycleScope,
    status: WorkerLifecycleStatus,
    reason: str,
    task_tool_call_id: Optional[str] = None,
    subagent_name: Optional[str] = None,
    parent_tool_call_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    subagent_type: Optional[str] = None,
) -> dict[str, Any]:
    event = {
        "type": "worker.lifecycle.changed",
        "scope": scope,
        "status": status,
        "reason": reason,
        "task_tool_call_id": task_tool_call_id,
        "subagent_name": subagent_name,
    }
    effective_parent_tool_call_id = parent_tool_call_id or task_tool_call_id
    if effective_parent_tool_call_id is not None:
        event["parent_tool_call_id"] = effective_parent_tool_call_id
    if agent_id is not None:
        event["agent_id"] = agent_id
    if subagent_type is not None:
        event["subagent_type"] = subagent_type
    return event


def project_host_lifecycle_from_wire(item: Any) -> Optional[WorkerLifecycleProjection]:
    if _is_turn_end_item(item):
        return WorkerLifecycleProjection(status="finished", reason="turn_end")
    if _is_step_interrupted_item(item):
        return WorkerLifecycleProjection(status="interrupted", reason="step_interrupted")

    status = _extract_status_value(item)
    if status == "cancelled":
        return WorkerLifecycleProjection(status="cancelled", reason="status_cancelled")
    if status == "failed":
        return WorkerLifecycleProjection(status="failed", reason="status_failed")
    if status == "interrupted":
        return WorkerLifecycleProjection(status="interrupted", reason="status_interrupted")
    return None


def project_subagent_lifecycle_from_wire(item: Any) -> Optional[WorkerLifecycleProjection]:
    return project_host_lifecycle_from_wire(item)


def project_subagent_lifecycle_from_task_result(
    *,
    is_error: bool,
    content: str,
) -> Optional[WorkerLifecycleProjection]:
    if not is_error:
        return None

    normalized = (content or "").strip().lower()
    if any(keyword in normalized for keyword in ("cancelled", "canceled", "cancel")):
        return WorkerLifecycleProjection(status="cancelled", reason="task_tool_result_cancelled")
    if any(keyword in normalized for keyword in ("interrupted", "interruption")):
        return WorkerLifecycleProjection(
            status="interrupted", reason="task_tool_result_interrupted"
        )
    return WorkerLifecycleProjection(status="failed", reason="task_tool_result_failed")


def _is_turn_end_item(item: Any) -> bool:
    item_type = getattr(item, "type", None)
    if isinstance(item_type, str) and item_type.strip().lower() == "turn_end":
        return True
    return item.__class__.__name__ == "TurnEnd"


def _is_step_interrupted_item(item: Any) -> bool:
    if item.__class__.__name__ == "StepInterrupted":
        return True
    status = getattr(item, "status", None)
    return isinstance(status, str) and status.strip().lower() == "interrupted"


def _extract_status_value(item: Any) -> Optional[str]:
    value = getattr(item, "status", None)
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in {"cancelled", "canceled"}:
        return "cancelled"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"interrupted"}:
        return "interrupted"
    return None
