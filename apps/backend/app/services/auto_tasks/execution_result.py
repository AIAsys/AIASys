from __future__ import annotations

from typing import Any

from app.services.auto_tasks.models import AutoTask, TaskStatus


def result_executed(result: dict[str, Any] | None) -> bool:
    if isinstance(result, dict) and result.get("executed") is False:
        return False
    return True


def non_execution_error_message(result: dict[str, Any] | None) -> str:
    if not isinstance(result, dict):
        return "自动任务未执行"
    reason = str(result.get("execution_reason") or "").strip()
    if reason == "bound_session_missing":
        session_id = str(result.get("session_id") or "").strip()
        if session_id:
            return f"绑定 Session 不存在: {session_id}"
        return "绑定 Session 不存在"
    if reason:
        return f"自动任务未执行: {reason}"
    return "自动任务未执行"


def _max_consecutive_errors(task: AutoTask) -> int:
    return getattr(task, "stop_on_consecutive_errors", 10) or 10


def record_execution_failure(task: AutoTask, error: str) -> None:
    task.consecutive_errors = int(task.consecutive_errors or 0) + 1
    task.last_error = error
    max_errors = _max_consecutive_errors(task)
    if task.consecutive_errors >= max_errors:
        task.status = TaskStatus.disabled


def record_non_execution_failure(task: AutoTask, result: dict[str, Any] | None) -> None:
    record_execution_failure(task, non_execution_error_message(result))


def record_execution_success(task: AutoTask) -> None:
    task.consecutive_errors = 0
    task.last_error = None
