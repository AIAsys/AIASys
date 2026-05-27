"""
自动任务模型。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

MIN_INTERVAL_SECONDS = 60


class AutoTaskTriggerType(str, Enum):
    once = "once"
    interval = "interval"
    cron = "cron"
    continuous = "continuous"


class TaskStatus(str, Enum):
    active = "active"
    paused = "paused"
    disabled = "disabled"
    completed = "completed"


class TaskCategory(str, Enum):
    scheduled = "scheduled"
    continuous = "continuous"


class FirstRunPolicy(str, Enum):
    immediate = "immediate"
    next_scheduled = "next_scheduled"


class HostingBootstrapMode(str, Enum):
    resume_only = "resume_only"
    launch_check = "launch_check"


class OverlapPolicy(str, Enum):
    skip = "skip"
    queue = "queue"
    parallel = "parallel"


@dataclass
class AutoTask:
    """工作区绑定的自动任务。"""

    task_id: str
    workspace_id: str
    user_id: str
    prompt: str
    trigger_type: AutoTaskTriggerType
    trigger_value: str
    status: TaskStatus = TaskStatus.active
    title: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    fired_count: int = 0
    consecutive_errors: int = 0
    last_error: Optional[str] = None
    model: Optional[str] = None
    model_id: Optional[str] = None
    sandbox_mode: Optional[str] = None
    attachments: list[str] = field(default_factory=list)
    auto_enable_hosting: bool = False
    hosting_bootstrap_mode: HostingBootstrapMode = HostingBootstrapMode.resume_only
    overlap_policy: OverlapPolicy = OverlapPolicy.skip
    pending_run_count: int = 0
    bind_session_id: Optional[str] = None
    continuation_prompt: Optional[str] = None
    max_continuations: int = -1
    # 任务类别与停止条件（v0.4.0 新增）
    task_category: TaskCategory = TaskCategory.scheduled
    first_run_policy: FirstRunPolicy = FirstRunPolicy.next_scheduled
    stop_on_consecutive_errors: int = 10
    stop_on_signal: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["trigger_type"] = (
            self.trigger_type.value if isinstance(self.trigger_type, Enum) else self.trigger_type
        )
        payload["status"] = self.status.value if isinstance(self.status, Enum) else self.status
        payload["hosting_bootstrap_mode"] = (
            self.hosting_bootstrap_mode.value
            if isinstance(self.hosting_bootstrap_mode, Enum)
            else self.hosting_bootstrap_mode
        )
        payload["overlap_policy"] = (
            self.overlap_policy.value
            if isinstance(self.overlap_policy, Enum)
            else self.overlap_policy
        )
        payload["task_category"] = (
            self.task_category.value if isinstance(self.task_category, Enum) else self.task_category
        )
        payload["first_run_policy"] = (
            self.first_run_policy.value
            if isinstance(self.first_run_policy, Enum)
            else self.first_run_policy
        )
        payload["session_strategy"] = "bind_session" if self.bind_session_id else "new_each_time"
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AutoTask:
        kwargs = dict(data)
        kwargs["trigger_type"] = AutoTaskTriggerType(kwargs.get("trigger_type", "interval"))
        kwargs["status"] = TaskStatus(kwargs.get("status", "active"))
        kwargs["hosting_bootstrap_mode"] = HostingBootstrapMode(
            kwargs.get("hosting_bootstrap_mode", "resume_only")
        )
        kwargs["overlap_policy"] = OverlapPolicy(kwargs.get("overlap_policy", "skip"))
        kwargs["task_category"] = TaskCategory(
            kwargs.get("task_category", TaskCategory.scheduled.value)
        )
        kwargs["first_run_policy"] = FirstRunPolicy(
            kwargs.get("first_run_policy", FirstRunPolicy.next_scheduled.value)
        )
        if kwargs["trigger_type"] == AutoTaskTriggerType.continuous:
            kwargs["trigger_value"] = ""
            kwargs["task_category"] = TaskCategory.continuous
            kwargs["first_run_policy"] = FirstRunPolicy.immediate
        session_strategy = kwargs.pop("session_strategy", None)
        if session_strategy == "new_each_time":
            kwargs["bind_session_id"] = None
        valid_fields = {field_info.name for field_info in cls.__dataclass_fields__.values()}
        unknown_fields = set(kwargs.keys()) - valid_fields
        if unknown_fields:
            import logging

            _logger = logging.getLogger(__name__)
            _logger.warning(
                "AutoTask.from_dict 遇到未知字段，将被丢弃: %s",
                sorted(unknown_fields),
            )
        return cls(**{key: value for key, value in kwargs.items() if key in valid_fields})
