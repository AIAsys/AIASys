"""AIASys 能力授权决策模块。

采用策略链（Policy Chain）架构：
- 每个策略独立判断，返回决策或 PASS
- 策略按固定优先级遍历，第一个做出决策的策略直接生效
- 会话级自动批准按 pattern_key（如 "shell_command" / "global_write"）记忆，
  而非按工具名记忆
"""

from .service import CapabilityAuthorizationService
from .types import (
    AuthorizationDecision,
    AuthorizationMode,
    CapabilityAuthorizationRequest,
    CapabilityAuthorizationResult,
    RiskLevel,
)

__all__ = [
    "CapabilityAuthorizationService",
    "AuthorizationDecision",
    "AuthorizationMode",
    "CapabilityAuthorizationRequest",
    "CapabilityAuthorizationResult",
    "RiskLevel",
]
