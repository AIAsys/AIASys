"""
自动任务服务。
"""

from app.services.auto_tasks.engine import (
    AutoTaskStore,
    ensure_auto_tasks_running,
    stop_auto_tasks,
)
from app.services.auto_tasks.executor import run_auto_task
from app.services.auto_tasks.models import (
    MIN_INTERVAL_SECONDS,
    AutoTask,
    AutoTaskTriggerType,
    FirstRunPolicy,
    HostingBootstrapMode,
    OverlapPolicy,
    TaskCategory,
    TaskStatus,
)
from app.services.auto_tasks.policy import ensure_auto_task_allowed_for_workspace

__all__ = [
    "AutoTask",
    "AutoTaskTriggerType",
    "FirstRunPolicy",
    "TaskCategory",
    "TaskStatus",
    "MIN_INTERVAL_SECONDS",
    "HostingBootstrapMode",
    "OverlapPolicy",
    "AutoTaskStore",
    "ensure_auto_tasks_running",
    "stop_auto_tasks",
    "run_auto_task",
    "ensure_auto_task_allowed_for_workspace",
]
