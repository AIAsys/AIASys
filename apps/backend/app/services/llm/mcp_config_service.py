"""
MCP 配置服务（三层合并模型）

底层委托给 MCPManager。新代码应直接使用 app.mcp.MCPManager。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config import WORKSPACE_DIR
from app.mcp import get_mcp_manager
from app.mcp.models import MCPServerDefinition
from app.models.mcp import MCPServerConfig

logger = logging.getLogger(__name__)


def _definition_to_server_config(definition: MCPServerDefinition) -> MCPServerConfig:
    """将 MCPServerDefinition 转换为 MCPServerConfig。"""
    return MCPServerConfig(
        name=definition.name,
        type=definition.type,
        url=definition.url,
        headers=definition.headers,
        command=definition.command,
        args=definition.args,
        env=definition.env,
        enabled=True,
        is_system_default=definition.is_system_default,
        auto_attach_modes=definition.auto_attach_modes,
        description=definition.description,
        timeout_ms=definition.timeout_ms,
    )


class MCPConfigService:
    """MCP 配置服务。

    底层委托给 MCPManager。
    """

    def __init__(self):
        self.workspace_dir = WORKSPACE_DIR
        self._mgr = get_mcp_manager()

    def remove_server(self, user_id: str, server_name: str) -> bool:
        """删除 MCP Server。"""
        result = self._mgr.remove_store_server(server_name, user_id)
        return result.success

    def get_server_config(self, user_id: str, server_name: str) -> Optional[MCPServerConfig]:
        """获取特定 Server 配置。"""
        definition = self._mgr.get_server_definition(server_name, user_id)
        if definition is None:
            return None
        return _definition_to_server_config(definition)

    def get_sdk_config(
        self,
        user_id: str,
        session_id: str,
        workspace_path: Path | None = None,
        include_system_default: bool = True,
    ) -> List[Dict[str, Any]] | None:
        """获取会话的最终 MCP 配置（给 SDK 使用）。

        三层合并后返回 SDK 格式配置列表。
        """
        if workspace_path is None:
            workspace_path = self.workspace_dir / user_id / session_id

        definitions = self._mgr.list_effective_servers(workspace_path)
        if not definitions:
            return None

        if not include_system_default:
            definitions = [s for s in definitions if not s.is_system_default]

        sdk_configs = []
        for server in definitions:
            try:
                sdk_configs.append(server.to_sdk_config())
            except Exception as e:
                logger.error(f"转换 Server {server.name} 配置失败: {e}")

        return sdk_configs if sdk_configs else None


def get_system_default_mcps(user_id: str) -> List[MCPServerConfig]:
    """获取系统默认 MCP 列表。"""
    mgr = get_mcp_manager()
    system_config = mgr._load_system_defaults()
    return [_definition_to_server_config(s) for s in system_config.servers.values()]


def get_auto_attach_system_mcps(user_id: str, mode: str | None) -> List[MCPServerConfig]:
    """获取当前 mode 下应自动附着的系统 MCP。"""
    return [
        server.model_copy(update={"auto_attached_by_mode": True})
        for server in get_system_default_mcps(user_id)
        if server.should_auto_attach_for_mode(mode)
    ]


# 全局服务实例
_mcp_config_service: Optional[MCPConfigService] = None


def get_mcp_config_service() -> MCPConfigService:
    global _mcp_config_service
    if _mcp_config_service is None:
        _mcp_config_service = MCPConfigService()
    return _mcp_config_service
