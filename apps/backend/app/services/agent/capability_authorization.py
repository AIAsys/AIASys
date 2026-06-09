"""能力授权决策服务（兼容层）。

实现已迁移至 app.services.agent.authorization 模块。
本文件保留以兼容现有导入路径，后续可逐步迁移到新的导入路径。
"""

from __future__ import annotations

# 从新模块重新导出全部公共接口
from app.services.agent.authorization import (  # noqa: F401
    AuthorizationDecision,
    AuthorizationMode,
    CapabilityAuthorizationRequest,
    CapabilityAuthorizationResult,
    CapabilityAuthorizationService,
    RiskLevel,
)
