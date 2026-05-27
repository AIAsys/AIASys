"""任务工作层配置模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class ExecutionPolicyMode(str, Enum):
    CHAT_ASSIST = "chat_assist"
    AUTO_EXPLORE = "auto_explore"


class CheckpointPolicy(str, Enum):
    STAGE_BOUNDARY = "stage_boundary"
    STEP_BOUNDARY = "step_boundary"
    MANUAL_ONLY = "manual_only"


class TaskExecutionPolicy(BaseModel):
    """任务运行行为策略。"""

    mode: ExecutionPolicyMode = Field(
        default=ExecutionPolicyMode.CHAT_ASSIST,
        description="任务运行行为：普通对话协作或自动探索",
    )
    auto_continue: bool = Field(
        default=False,
        description="是否允许系统在没有新用户消息时自动续跑",
    )
    checkpoint_policy: CheckpointPolicy = Field(
        default=CheckpointPolicy.STAGE_BOUNDARY,
        description="自动探索过程中默认的 checkpoint 粒度",
    )
    human_gate_rules: list[str] = Field(
        default_factory=lambda: [
            "high_risk_action",
            "budget_limit",
            "goal_ambiguous",
        ],
        description="遇到这些条件时必须先停给人",
    )
    max_parallel_sessions: int = Field(
        default=1,
        ge=1,
        description="自动探索允许同时推进的最大支线数",
    )
    max_continuations: int = Field(
        default=8,
        ge=-1,
        description="单轮自动推进允许排队的 continuation 上限，-1 表示无限续杯",
    )
    max_runtime_minutes: int = Field(
        default=30,
        ge=1,
        description="单轮自动推进允许占用的最大运行时长（分钟）",
    )

    @field_validator("human_gate_rules", mode="before")
    @classmethod
    def _normalize_gate_rules(cls, value: Any) -> list[str]:
        if value is None:
            return [
                "high_risk_action",
                "budget_limit",
                "goal_ambiguous",
            ]
        if not isinstance(value, list):
            raise ValueError("human_gate_rules 必须是字符串列表")
        normalized: list[str] = []
        for item in value:
            text = str(item).strip()
            if text and text not in normalized:
                normalized.append(text)
        return normalized

    @model_validator(mode="after")
    def _sync_mode_defaults(self) -> TaskExecutionPolicy:
        if self.mode == ExecutionPolicyMode.AUTO_EXPLORE:
            self.auto_continue = True
            if self.checkpoint_policy == CheckpointPolicy.MANUAL_ONLY:
                self.checkpoint_policy = CheckpointPolicy.STAGE_BOUNDARY
        else:
            self.auto_continue = False
        return self


def default_execution_policy() -> TaskExecutionPolicy:
    return TaskExecutionPolicy()


def normalize_execution_policy(
    execution_policy: Any,
) -> TaskExecutionPolicy:
    if isinstance(execution_policy, TaskExecutionPolicy):
        return execution_policy
    if isinstance(execution_policy, dict):
        return TaskExecutionPolicy.model_validate(execution_policy)
    return default_execution_policy()


def build_task_profile_summary(
    *,
    execution_policy: Any,
) -> dict[str, Any]:
    policy = normalize_execution_policy(execution_policy)
    return {
        "execution_policy": policy.model_dump(mode="json"),
    }
