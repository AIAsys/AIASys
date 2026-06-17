"""
MCP 管理器（三层合并模型）

设计口径：
- 系统默认：app/mcp/system_defaults.json
- 用户全局：workspaces/{user_id}/global_workspace/.aiasys/mcp_config.json
- 工作区：workspaces/{user_id}/{ws}/.aiasys/mcp_config.json
- 合并规则：高层完全覆盖低层（工作区 > 用户全局 > 系统默认）
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Optional

from app.core.config import WORKSPACE_DIR

from .models import MCPConfig, MCPOperationResult, MCPServerDefinition

logger = logging.getLogger(__name__)


class MCPManager:
    """MCP server 发现、存储与合并管理。"""

    MCP_CONFIG_FILENAME = "mcp_config.json"

    # 系统默认配置路径（代码仓库内）
    SYSTEM_DEFAULTS_PATH = Path(__file__).resolve().parent / "system_defaults.json"

    # 按 user_id 串行化全局仓库 read-modify-write，防止并发写覆盖
    _store_locks: dict[str, threading.Lock] = {}
    _store_locks_guard = threading.Lock()

    @classmethod
    def _get_store_lock(cls, user_id: str) -> threading.Lock:
        """获取（或创建）user_id 对应的全局仓库写锁。"""
        with cls._store_locks_guard:
            lock = cls._store_locks.get(user_id)
            if lock is None:
                lock = threading.Lock()
                cls._store_locks[user_id] = lock
            return lock

    # ---- 路径工具 ----

    def _get_user_mcp_config_path(self, user_id: str) -> Path:
        """返回用户全局 MCP 配置文件路径。"""
        return WORKSPACE_DIR / user_id / "global_workspace" / ".aiasys" / self.MCP_CONFIG_FILENAME

    def _get_workspace_mcp_config_path(self, workspace_path: Path) -> Path:
        """返回工作区 MCP 配置文件路径。"""
        return workspace_path / ".aiasys" / self.MCP_CONFIG_FILENAME

    @staticmethod
    def _infer_user_id_from_workspace_path(workspace_path: Path) -> str | None:
        """从工作区路径推断 user_id。

        期望格式: workspaces/{user_id}/{workspace_id}/...
        """
        try:
            user_id = workspace_path.parent.name
            if user_id:
                return user_id
        except Exception:
            pass
        return None

    # ---- 路径安全 ----

    @staticmethod
    def _is_safe_name(name: str) -> bool:
        """防止路径遍历。"""
        if not name:
            return False
        if name.startswith("."):
            return False
        if "/" in name or "\\" in name or ".." in name:
            return False
        return True

    # ---- 配置读取 ----

    def _load_config_file(self, path: Path) -> MCPConfig:
        """从指定路径读取 MCP 配置。"""
        if not path.exists():
            return MCPConfig()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return MCPConfig.model_validate(data)
        except Exception:
            logger.warning("MCP 配置解析失败: %s", path, exc_info=True)
            return MCPConfig()

    def _save_config_file(self, path: Path, config: MCPConfig) -> None:
        """保存 MCP 配置到指定路径（原子写）。"""
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(config.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(path)

    def _load_system_defaults(self) -> MCPConfig:
        """读取系统默认 MCP 配置。"""
        return self._load_config_file(self.SYSTEM_DEFAULTS_PATH)

    def _load_user_global_config(self, user_id: str) -> MCPConfig:
        """读取用户全局 MCP 配置。"""
        return self._load_config_file(self._get_user_mcp_config_path(user_id))

    def _load_workspace_config(self, workspace_path: Path) -> MCPConfig:
        """读取工作区 MCP 配置。"""
        return self._load_config_file(self._get_workspace_mcp_config_path(workspace_path))

    def _save_workspace_config(self, workspace_path: Path, config: MCPConfig) -> None:
        """保存工作区 MCP 配置。"""
        self._save_config_file(self._get_workspace_mcp_config_path(workspace_path), config)

    # ---- 三层合并 ----

    def get_effective_config(self, workspace_path: Path) -> MCPConfig:
        """返回三层合并后的有效 MCP 配置。

        合并规则：工作区 > 用户全局 > 系统默认
        同名 server 高层覆盖低层，不同名都保留。
        各层的 disabled_servers 均参与最终过滤。
        """
        system_config = self._load_system_defaults()
        user_id = self._infer_user_id_from_workspace_path(workspace_path)

        # 从系统默认开始
        effective = dict(system_config.servers)

        # 用户全局覆盖/扩展
        global_config = MCPConfig()
        if user_id is not None:
            global_config = self._load_user_global_config(user_id)
            effective.update(global_config.servers)

        # 工作区覆盖/扩展
        workspace_config = self._load_workspace_config(workspace_path)
        effective.update(workspace_config.servers)

        # 合并后过滤各层 disabled_servers
        for name in global_config.disabled_servers:
            effective.pop(name, None)
        for name in workspace_config.disabled_servers:
            effective.pop(name, None)

        return MCPConfig(version=1, servers=effective)

    def list_effective_servers(self, workspace_path: Path) -> list[MCPServerDefinition]:
        """返回工作区实际生效的 server 列表。"""
        config = self.get_effective_config(workspace_path)
        return list(config.servers.values())

    # ---- 用户全局仓库 CRUD ----

    def list_store_servers(self, user_id: str) -> list[MCPServerDefinition]:
        """返回用户全局配置中所有 server 定义。"""
        config = self._load_user_global_config(user_id)
        return list(config.servers.values())

    def get_server_definition(self, name: str, user_id: str) -> Optional[MCPServerDefinition]:
        """读取单个 server 的用户全局定义。"""
        if not self._is_safe_name(name):
            return None
        config = self._load_user_global_config(user_id)
        return config.servers.get(name)

    def save_store_server(
        self, user_id: str, definition: MCPServerDefinition, *, force: bool = False
    ) -> MCPOperationResult:
        """保存 server 定义到用户全局配置。"""
        if not self._is_safe_name(definition.name):
            return MCPOperationResult(
                success=False, server_name=definition.name, message="名称包含非法字符"
            )
        with self._get_store_lock(user_id):
            config = self._load_user_global_config(user_id)
            if definition.name in config.servers and not force:
                return MCPOperationResult(
                    success=False,
                    server_name=definition.name,
                    message=f"server '{definition.name}' 已存在，使用 force=True 覆盖",
                )
            config.servers[definition.name] = definition
            self._save_config_file(self._get_user_mcp_config_path(user_id), config)
        return MCPOperationResult(success=True, server_name=definition.name, message="已保存")

    def remove_store_server(self, name: str, user_id: str) -> MCPOperationResult:
        """从用户全局配置删除 server 定义。"""
        if not self._is_safe_name(name):
            return MCPOperationResult(success=False, server_name=name, message="名称包含非法字符")
        with self._get_store_lock(user_id):
            config = self._load_user_global_config(user_id)
            if name not in config.servers:
                return MCPOperationResult(success=False, server_name=name, message="server 不存在")
            del config.servers[name]
            self._save_config_file(self._get_user_mcp_config_path(user_id), config)
        return MCPOperationResult(success=True, server_name=name, message="已删除")

    # ---- 工作区配置操作 ----

    def save_workspace_server(
        self,
        workspace_path: Path,
        definition: MCPServerDefinition,
    ) -> MCPOperationResult:
        """保存 server 定义到工作区配置，同时从禁用列表中移除。"""
        if not self._is_safe_name(definition.name):
            return MCPOperationResult(
                success=False, server_name=definition.name, message="名称包含非法字符"
            )
        config = self._load_workspace_config(workspace_path)
        config.servers[definition.name] = definition
        if definition.name in config.disabled_servers:
            config.disabled_servers.remove(definition.name)
        self._save_workspace_config(workspace_path, config)

        # 同步更新统一能力层声明
        try:
            from app.capabilities.manager import get_capability_manager
            from app.capabilities.models import CapabilityKind, WorkspaceCapability

            cap_mgr = get_capability_manager()
            cap_mgr._write_declaration(
                workspace_path,
                WorkspaceCapability(
                    capability_id=definition.name,
                    kind=CapabilityKind.MCP_SERVER,
                    enabled=True,
                    source="workspace",
                ),
            )
        except Exception as exc:
            logger.warning(
                "MCP server 保存成功但 capability 声明同步失败: %s",
                exc,
                exc_info=True,
            )

        return MCPOperationResult(
            success=True, server_name=definition.name, message="已保存到工作区"
        )

    def remove_workspace_server(self, name: str, workspace_path: Path) -> MCPOperationResult:
        """从工作区配置中移除 server 定义，并将其加入禁用列表。"""
        if not self._is_safe_name(name):
            return MCPOperationResult(success=False, server_name=name, message="名称包含非法字符")
        config = self._load_workspace_config(workspace_path)
        changed = False
        if name in config.servers:
            del config.servers[name]
            changed = True
        if name not in config.disabled_servers:
            config.disabled_servers.append(name)
            changed = True
        if not changed:
            return MCPOperationResult(
                success=False, server_name=name, message="server 不存在于工作区配置"
            )
        self._save_workspace_config(workspace_path, config)

        # 同步更新统一能力层声明
        try:
            from app.capabilities.manager import get_capability_manager

            cap_mgr = get_capability_manager()
            cap_mgr._remove_declaration(workspace_path, name)
        except Exception as exc:
            logger.warning(
                "MCP server 移除成功但 capability 声明同步失败: %s",
                exc,
                exc_info=True,
            )

        return MCPOperationResult(success=True, server_name=name, message="已从工作区禁用")

    def set_store_server_env(
        self, user_id: str, name: str, env: dict[str, str]
    ) -> MCPOperationResult:
        """设置 server 在全局仓库的环境变量。"""
        if not self._is_safe_name(name):
            return MCPOperationResult(success=False, server_name=name, message="名称包含非法字符")
        with self._get_store_lock(user_id):
            config = self._load_user_global_config(user_id)
            if name not in config.servers:
                return MCPOperationResult(
                    success=False, server_name=name, message="server 不存在于全局仓库"
                )
            config.servers[name].env = env
            self._save_config_file(self._get_user_mcp_config_path(user_id), config)
        return MCPOperationResult(success=True, server_name=name, message="环境变量已更新")

    def set_workspace_server_env(
        self, name: str, workspace_path: Path, env: dict[str, str]
    ) -> MCPOperationResult:
        """设置 server 在工作区的环境变量。"""
        if not self._is_safe_name(name):
            return MCPOperationResult(success=False, server_name=name, message="名称包含非法字符")
        config = self._load_workspace_config(workspace_path)
        if name not in config.servers:
            return MCPOperationResult(
                success=False, server_name=name, message="server 不存在于工作区配置"
            )
        config.servers[name].env = env
        self._save_workspace_config(workspace_path, config)
        return MCPOperationResult(success=True, server_name=name, message="环境变量已更新")

    def _get_tools_cache_path(self, workspace_path: Path) -> Path:
        """返回工作区 MCP 工具缓存文件路径。"""
        return workspace_path / ".aiasys" / "mcp_tools_cache.json"

    def _load_tools_cache(self, workspace_path: Path) -> dict[str, list[dict[str, Any]]]:
        """加载工具缓存。"""
        path = self._get_tools_cache_path(workspace_path)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            logger.warning("MCP 工具缓存解析失败: %s", path, exc_info=True)
            return {}

    def _save_tools_cache(
        self, workspace_path: Path, cache: dict[str, list[dict[str, Any]]]
    ) -> None:
        """保存工具缓存。"""
        path = self._get_tools_cache_path(workspace_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")

    def cache_server_tools(
        self,
        workspace_path: Path,
        server_name: str,
        tools: list[dict[str, Any]],
    ) -> None:
        """缓存 server 的工具列表。"""
        cache = self._load_tools_cache(workspace_path)
        cache[server_name] = tools
        self._save_tools_cache(workspace_path, cache)

    def get_cached_server_tools(
        self, workspace_path: Path, server_name: str
    ) -> list[dict[str, Any]]:
        """获取缓存的 server 工具列表。"""
        cache = self._load_tools_cache(workspace_path)
        return cache.get(server_name, [])

    def set_workspace_server_enabled_tools(
        self,
        name: str,
        workspace_path: Path,
        enabled_tools: list[str],
    ) -> MCPOperationResult:
        """设置 server 在工作区中启用的工具列表。"""
        if not self._is_safe_name(name):
            return MCPOperationResult(success=False, server_name=name, message="名称包含非法字符")
        config = self._load_workspace_config(workspace_path)
        if name not in config.servers:
            return MCPOperationResult(
                success=False, server_name=name, message="server 不存在于工作区配置"
            )
        config.servers[name].enabled_tools = enabled_tools
        self._save_workspace_config(workspace_path, config)
        return MCPOperationResult(
            success=True,
            server_name=name,
            message=f"已更新启用的工具列表（{len(enabled_tools)} 个）",
        )

    def get_workspace_server_enabled_tools(self, name: str, workspace_path: Path) -> list[str]:
        """获取 server 在工作区中启用的工具列表。"""
        if not self._is_safe_name(name):
            return []
        config = self._load_workspace_config(workspace_path)
        server = config.servers.get(name)
        if server is None:
            return []
        return list(server.enabled_tools or [])


# ---- 全局单例 ----

_mcp_manager: Optional[MCPManager] = None


def get_mcp_manager() -> MCPManager:
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPManager()
    return _mcp_manager


def get_available_mcps_for_workspace(workspace_path: Path) -> dict[str, Any]:
    """返回工作区可用 MCP 列表。"""
    mgr = get_mcp_manager()
    servers = mgr.list_effective_servers(workspace_path)
    return {
        "servers": [
            {
                "name": s.name,
                "display_name": s.display_name,
                "type": s.type,
                "is_system_default": s.is_system_default,
            }
            for s in servers
        ]
    }
