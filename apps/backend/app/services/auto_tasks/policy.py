from __future__ import annotations

from typing import Any

from app.models.task_profile import ExecutionPolicyMode, normalize_execution_policy


def is_auto_task_control_disabled_for_execution_policy(execution_policy: Any) -> bool:
    normalized_policy = normalize_execution_policy(execution_policy)
    policy_mode = getattr(normalized_policy, "mode", None)
    if hasattr(policy_mode, "value"):
        policy_mode = getattr(policy_mode, "value")
    return str(policy_mode or "").strip().lower() == ExecutionPolicyMode.AUTO_EXPLORE.value


def ensure_auto_task_allowed_for_workspace(
    *,
    user_id: str,
    workspace_id: str,
    workspace_registry: Any,
) -> None:
    workspace_registry._read_workspace_meta(user_id, workspace_id)
