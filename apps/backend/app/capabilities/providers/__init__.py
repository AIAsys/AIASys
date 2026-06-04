"""Capability Provider 实现。

每种能力类型（skill_pack / mcp_server / subagent）实现统一的
CapabilityProvider 接口，供 CapabilityManager 调用。
"""

from __future__ import annotations

from .base import CapabilityProvider
from .mcp_provider import MCPProvider
from .skill_provider import SkillProvider
from .subagent_provider import SubagentProvider

__all__ = [
    "CapabilityProvider",
    "SkillProvider",
    "MCPProvider",
    "SubagentProvider",
]
