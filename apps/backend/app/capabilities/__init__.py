"""统一能力层（Capability Layer）。

覆盖 Skill、MCP、子 Agent 的全生命周期管理：
- 发现（SourceRegistry 扫描源仓库）
- 安装/卸载（Provider 实现）
- 激活/禁用（Provider 实现）
- 验证（Provider 实现 + Manager 聚合）
- 依赖解析（Manager 自动处理）
"""

from __future__ import annotations

from .manager import CapabilityManager, get_capability_manager
from .models import (
    CapabilityDeclaration,
    CapabilityHealthcheck,
    CapabilityKind,
    CapabilityManifest,
    CapabilityStatus,
    HealthStatus,
    InstallResult,
    WorkspaceCapability,
)
from .source_registry import CapabilitySourceRegistry

__all__ = [
    "CapabilityDeclaration",
    "CapabilityHealthcheck",
    "CapabilityKind",
    "CapabilityManifest",
    "CapabilityManager",
    "CapabilitySourceRegistry",
    "CapabilityStatus",
    "get_capability_manager",
    "HealthStatus",
    "InstallResult",
    "WorkspaceCapability",
]
