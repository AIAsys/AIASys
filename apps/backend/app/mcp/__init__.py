"""
MCP 管理模块

三层合并模型：
- 系统默认层 / 用户全局层 / 工作区层
提供 MCP server 的发现、存储和合并功能。
"""

from .manager import (
    MCPManager,
    get_available_mcps_for_workspace,
    get_mcp_manager,
)
from .models import (
    MCPConfig,
    MCPOperationResult,
    MCPServerDefinition,
)

__all__ = [
    "MCPManager",
    "get_mcp_manager",
    "get_available_mcps_for_workspace",
    "MCPConfig",
    "MCPServerDefinition",
    "MCPOperationResult",
]
