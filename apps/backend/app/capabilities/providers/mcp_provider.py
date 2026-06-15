"""MCP 类型能力 Provider。

安装/卸载动作：在工作区 mcp_config.json 中增删 server 配置。
激活/禁用动作：改 disabled_servers 列表。
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

from app.capabilities.models import (
    CapabilityKind,
    CapabilityManifest,
    CapabilityStatus,
    HealthStatus,
    InstallResult,
)
from app.capabilities.providers.base import CapabilityProvider, CapabilityProviderContext
from app.mcp import MCPConfig, MCPServerDefinition, get_mcp_manager

logger = logging.getLogger(__name__)


class MCPProvider(CapabilityProvider):
    """MCP 能力 Provider。

    install    = 把 server 配置从系统级复制到工作区 mcp_config.json
    uninstall  = 从工作区 mcp_config.json 删除 server
    activate   = 从 disabled_servers 移除
    deactivate = 加入 disabled_servers
    verify     = 检查工作区 MCP 配置存在性和禁用状态
    """

    def resolve_manifest(self, source_dir: Path) -> CapabilityManifest | None:
        manifest_path = source_dir / "manifest.toml"
        if not manifest_path.exists():
            return None
        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("MCP manifest 解析失败 %s: %s", manifest_path, exc)
            return None

        cap_id = str(raw.get("capability_id", source_dir.name)).strip()
        if not cap_id:
            return None

        return CapabilityManifest(
            capability_id=cap_id,
            kind=CapabilityKind.MCP_SERVER,
            display_name=str(raw.get("display_name", cap_id)).strip(),
            description=str(raw.get("description", "")).strip(),
            version=str(raw.get("version", "1.0.0")).strip(),
            author=str(raw.get("author", "")).strip(),
            dependencies=[],
            config_schema=raw.get("config_schema") or {},
            min_platform_version="0.1.0",
            source_dir=str(source_dir),
        )

    def install(
        self,
        cap_id: str,
        workspace_path: Path,
        source_dir: Path,
        config: dict[str, Any] | None = None,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        # 读取 manifest 中引用的 server_name
        server_name = self._resolve_server_name(cap_id, source_dir)
        if not server_name:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"MCP '{cap_id}' manifest 缺少 server_name",
            )

        # 优先从 manifest 自身读取 server 定义，若 manifest 未提供再从系统默认配置读取
        server_def = self._load_server_definition_from_manifest(source_dir)
        if server_def is None:
            system_config = self._load_system_mcp_config()
            server_def = system_config.get("servers", {}).get(server_name)
        if not server_def:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"系统 MCP 配置或 manifest 中不存在 server '{server_name}'",
            )

        server_payload = dict(server_def)

        # 如果有用户自定义 config，合并到 server 配置
        if config:
            server_payload.update(config)

        try:
            definition = MCPServerDefinition.model_validate(server_payload)
        except Exception as exc:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"MCP server 配置无效: {exc}",
            )

        result = get_mcp_manager().save_workspace_server(workspace_path, definition)
        if not result.success:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=result.message,
            )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"MCP '{cap_id}' (server: {server_name}) 已安装",
        )

    def uninstall(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        server_name = self._find_server_name_by_cap_id(cap_id, workspace_path)
        if not server_name:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"MCP '{cap_id}' 未在工作区安装",
            )

        result = get_mcp_manager().remove_workspace_server(server_name, workspace_path)
        if not result.success:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=result.message,
            )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"MCP '{cap_id}' 已卸载",
        )

    def activate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        server_name = self._find_server_name_by_cap_id(cap_id, workspace_path)
        if not server_name:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"MCP '{cap_id}' 未安装",
            )

        ws_config = self._load_workspace_mcp_config(workspace_path)
        disabled = ws_config.setdefault("disabled_servers", [])
        if server_name in disabled:
            disabled.remove(server_name)
            self._save_workspace_mcp_config(workspace_path, ws_config)

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"MCP '{cap_id}' 已激活",
        )

    def deactivate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        server_name = self._find_server_name_by_cap_id(cap_id, workspace_path)
        if not server_name:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"MCP '{cap_id}' 未安装",
            )

        ws_config = self._load_workspace_mcp_config(workspace_path)
        disabled = ws_config.setdefault("disabled_servers", [])
        if server_name not in disabled:
            disabled.append(server_name)
            self._save_workspace_mcp_config(workspace_path, ws_config)

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"MCP '{cap_id}' 已禁用",
        )

    def verify(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> HealthStatus:
        server_name = self._find_server_name_by_cap_id(cap_id, workspace_path)
        if not server_name:
            return HealthStatus(
                status=CapabilityStatus.AVAILABLE,
                detail="未安装",
            )

        ws_config = self._load_workspace_mcp_config(workspace_path)
        servers = ws_config.get("servers", {})
        disabled = set(ws_config.get("disabled_servers", []))

        if server_name not in servers:
            return HealthStatus(
                status=CapabilityStatus.ERROR,
                detail="server 配置缺失",
            )

        if server_name in disabled:
            return HealthStatus(
                status=CapabilityStatus.DISABLED,
                detail="已禁用",
            )

        return HealthStatus(
            status=CapabilityStatus.INSTALLED,
            detail="已配置，未执行 MCP 连接验活",
        )

    def is_installed(
        self, cap_id: str, workspace_path: Path, context: CapabilityProviderContext | None = None
    ) -> bool:
        return self._find_server_name_by_cap_id(cap_id, workspace_path) is not None

    # ---- 内部方法 ----

    def _resolve_server_name(self, cap_id: str, source_dir: Path) -> str:
        manifest_path = source_dir / "manifest.toml"
        if not manifest_path.exists():
            return cap_id
        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
            return str(raw.get("server_name", cap_id)).strip() or cap_id
        except Exception:
            return cap_id

    def _load_server_definition_from_manifest(
        self, source_dir: Path
    ) -> dict[str, Any] | None:
        """从 manifest 的 [server_definition] 段读取 MCP server 配置。"""
        manifest_path = source_dir / "manifest.toml"
        if not manifest_path.exists():
            return None
        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
            return raw.get("server_definition")
        except Exception:
            return None

    def _find_server_name_by_cap_id(self, cap_id: str, workspace_path: Path) -> str | None:
        """在工作区 mcp_config.json 中查找 cap_id 对应的 server_name。"""
        ws_config = self._load_workspace_mcp_config(workspace_path)
        servers = ws_config.get("servers", {})

        # 直接匹配
        if cap_id in servers:
            return cap_id

        # 复用 CapabilitySourceRegistry 的 manifest 查询，避免重复文件 IO
        from app.capabilities.manager import get_capability_manager

        manifest = get_capability_manager()._source_registry.get_manifest(cap_id)
        if manifest is not None:
            server_name = manifest.capability_id
            if server_name in servers:
                return server_name
        return None

    def _load_system_mcp_config(self) -> dict[str, Any]:
        config = get_mcp_manager()._load_system_defaults()
        return config.model_dump(mode="json")

    def _load_workspace_mcp_config(self, workspace_path: Path) -> dict[str, Any]:
        return get_mcp_manager()._load_workspace_config(workspace_path).model_dump(mode="json")

    def _save_workspace_mcp_config(self, workspace_path: Path, config: dict[str, Any]) -> None:
        try:
            get_mcp_manager()._save_workspace_config(
                workspace_path,
                MCPConfig.model_validate(config),
            )
        except Exception as exc:
            logger.warning("MCP 配置保存失败 %s: %s", workspace_path, exc)
