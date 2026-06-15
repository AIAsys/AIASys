"""
MCP 会话配置服务（三层合并模型）

当前口径：
- 系统默认：app/mcp/system_defaults.json
- 用户全局：global_workspace/.aiasys/mcp_config.json
- 工作区：{workspace}/.aiasys/mcp_config.json
- 合并规则：工作区 > 用户全局 > 系统默认
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import List, Optional

from app.core.config import WORKSPACE_DIR
from app.mcp import get_mcp_manager
from app.mcp.models import MCPServerDefinition
from app.models.mcp import MCPServerConfig
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)

# 支持 ${VAR} 形式的环境变量占位符
_ENV_PLACEHOLDER_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_env_placeholders(value: str, env: dict[str, str]) -> str:
    """解析字符串中的 ${VAR} 占位符。

    优先使用 server.env 中声明的值，其次回退到进程环境变量。
    未找到时保留原占位符，便于排查。
    """

    def _replace(match: re.Match) -> str:
        var_name = match.group(1)
        return env.get(var_name) or os.environ.get(var_name) or match.group(0)

    return _ENV_PLACEHOLDER_RE.sub(_replace, value)


def _definition_to_server_config(definition: MCPServerDefinition) -> MCPServerConfig:
    """将 MCPServerDefinition 转换为 MCPServerConfig。"""
    return MCPServerConfig(
        name=definition.name,
        display_name=definition.display_name,
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
        enabled_tools=list(definition.enabled_tools or []),
    )


class MCPSessionService:
    """MCP 会话配置服务。"""

    def __init__(self):
        self.workspace_dir = WORKSPACE_DIR
        self._mgr = get_mcp_manager()

    def _get_session_dir(self, user_id: str, session_id: str) -> Path:
        return self.workspace_dir / user_id / session_id

    def _get_logical_workspace_dir(self, user_id: str, session_id: str) -> Path:
        workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
            user_id,
            session_id,
        )
        if workspace_id:
            return get_workspace_registry_service()._get_workspace_dir(user_id, workspace_id)
        return self._get_session_dir(user_id, session_id)

    def get_session_mcp_servers(self, user_id: str, session_id: str) -> List[MCPServerConfig]:
        """获取会话的 MCP 服务器列表（三层合并后）。"""
        try:
            workspace_dir = self._get_logical_workspace_dir(user_id, session_id)
            definitions = self._mgr.list_effective_servers(workspace_dir)
            return [_definition_to_server_config(d) for d in definitions]
        except Exception as exc:
            logger.error("读取会话 %s MCP 配置失败: %s", session_id, exc)
            return []

    def add_session_mcp_server(
        self, user_id: str, session_id: str, server: MCPServerConfig
    ) -> bool:
        """为会话添加 MCP 服务器。

        保存到用户全局配置，使所有工作区可用。
        """
        try:
            definition = MCPServerDefinition(
                name=server.name,
                display_name=server.name,
                type=server.type,
                url=server.url,
                headers=server.headers or {},
                command=server.command,
                args=server.args or [],
                env=server.env or {},
                description=server.description,
                timeout_ms=server.timeout_ms,
            )
            self._mgr.save_store_server(user_id, definition, force=True)
            return True
        except Exception as e:
            logger.error("保存会话 MCP 配置失败: %s", e)
            return False

    def remove_session_mcp_server(self, user_id: str, session_id: str, server_name: str) -> bool:
        """删除会话的 MCP 服务器。

        从用户全局配置删除。
        """
        try:
            self._mgr.remove_store_server(server_name, user_id)
            return True
        except Exception as e:
            logger.error("删除会话 MCP 服务器失败: %s", e)
            return False

    def get_sdk_config(self, user_id: str, session_id: str) -> List[dict]:
        """获取 SDK 可用的 MCP 配置格式。

        返回 fastmcp.MCPConfig 兼容的格式：
        [{"mcpServers": {"server_name": {...}, ...}}]
        """
        servers = self.get_session_mcp_servers(user_id, session_id)

        mcp_servers = {}
        for server in servers:
            if not server.enabled:
                continue

            if server.type in ("http", "streamable-http", "sse"):
                server_config = {
                    "url": server.url,
                    "transport": server.type if server.type != "http" else None,
                }
                server_config = {k: v for k, v in server_config.items() if v is not None}
            elif server.type == "stdio":
                server_config = {"command": server.command}
                if server.args:
                    server_config["args"] = server.args
            else:
                server_config = {"url": server.url}

            if server.env:
                server_config["env"] = server.env
            if server.headers:
                # 解析 headers 中的 ${VAR} 占位符，支持从 server.env 或进程环境变量取值
                resolved_env = server.env or {}
                server_config["headers"] = {
                    key: _resolve_env_placeholders(value, resolved_env)
                    for key, value in server.headers.items()
                }
            if server.enabled_tools:
                server_config["enabled_tools"] = server.enabled_tools

            mcp_servers[server.name] = server_config

        if mcp_servers:
            return [{"mcpServers": mcp_servers}]
        return []


# 单例
_mcp_session_service: Optional[MCPSessionService] = None


def get_mcp_session_service() -> MCPSessionService:
    global _mcp_session_service
    if _mcp_session_service is None:
        _mcp_session_service = MCPSessionService()
    return _mcp_session_service
