"""授权决策类型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AuthorizationMode(str, Enum):
    """授权档位。"""

    MANUAL = "manual"
    SMART = "smart"
    AUTO = "auto"
    FULL_AUTO = "full_auto"


class AuthorizationDecision(str, Enum):
    """授权决策结果。"""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
    BLOCK = "block"


class RiskLevel(str, Enum):
    """能力调用风险等级。"""

    READONLY = "readonly"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True, kw_only=True)
class CapabilityAuthorizationRequest:
    """单次能力调用的授权请求。"""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    # 工具元数据（由调用方或工具注册表提供）
    risk_level: RiskLevel = RiskLevel.MEDIUM
    effect_scope: str = "workspace"  # workspace | global | session | external
    side_effect: bool = True
    # 上下文
    authorization_mode: AuthorizationMode = AuthorizationMode.SMART
    remembered_grants: list[dict[str, Any]] = field(default_factory=list)
    # Skill 安全元数据（EnableSkill 时使用，避免循环导入用 dict）
    skill_security: dict[str, Any] = field(default_factory=dict)
    # 特殊标记
    is_subagent: bool = False
    # Plan Mode 上下文
    plan_mode_active: bool = False
    plan_file_path: str | None = None


@dataclass(slots=True, kw_only=True)
class CapabilityAuthorizationResult:
    """授权决策结果。"""

    decision: AuthorizationDecision
    reason: str = ""
    # 当 decision=ASK 时，建议给用户的确认文案
    confirmation_prompt: str = ""
    # 当 decision=DENY/BLOCK 时，返回给模型的错误信息
    denial_message: str = ""
    # 用于会话级自动批准记忆的 pattern key
    # 按 pattern 记忆（如 "shell_command" / "global_write"）而非工具名
    pattern_key: str | None = None
