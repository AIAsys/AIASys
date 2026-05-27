"""统一能力管理器。

负责：
- 依赖解析和批量安装
- 工作区级能力声明读写（capabilities.toml）
- 模板声明应用
- 工作区验活
"""

from __future__ import annotations

import logging
import tomllib
from pathlib import Path
from typing import Any

import tomli_w

from app.capabilities.models import (
    CapabilityDeclaration,
    CapabilityKind,
    CapabilityManifest,
    CapabilityStatus,
    HealthStatus,
    InstallResult,
    WorkspaceCapability,
)
from app.capabilities.providers import MCPProvider, SkillProvider, SubagentProvider
from app.capabilities.providers.base import CapabilityProvider, CapabilityProviderContext, Scope
from app.capabilities.source_registry import CapabilitySourceRegistry

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[CapabilityKind, CapabilityProvider] = {
    CapabilityKind.SKILL_PACK: SkillProvider(),
    CapabilityKind.MCP_SERVER: MCPProvider(),
    CapabilityKind.SUBAGENT: SubagentProvider(),
}


class CapabilityManager:
    """统一能力管理器。"""

    def __init__(self) -> None:
        self._source_registry = CapabilitySourceRegistry()

    # ---- 源仓库查询 ----

    def list_available(self) -> list[CapabilityManifest]:
        """返回所有源仓库中可用的能力。"""
        return self._source_registry.scan_all()

    def get_manifest(self, cap_id: str) -> CapabilityManifest | None:
        """按 ID 获取能力 manifest。"""
        return self._source_registry.get_manifest(cap_id)

    # ---- 工作区操作 ----

    def install(
        self,
        cap_id: str,
        workspace_path: Path,
        config: dict[str, Any] | None = None,
        scope: Scope = "workspace",
        _visited: set[str] | None = None,
    ) -> InstallResult:
        """安装能力到目标作用域（含依赖解析）。

        _visited 参数仅供内部递归使用，用于检测依赖环。
        """
        # 环检测
        if _visited is None:
            _visited = set()
        if cap_id in _visited:
            cycle_path = " -> ".join(_visited) + f" -> {cap_id}"
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"检测到依赖环: {cycle_path}",
            )
        _visited.add(cap_id)

        manifest = self._source_registry.get_manifest(cap_id)
        if manifest is None:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"能力 '{cap_id}' 在源仓库中不存在",
            )

        provider = _PROVIDER_MAP.get(manifest.kind)
        if provider is None:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"未知能力类型: {manifest.kind}",
            )

        target_path = self._resolve_target_path(workspace_path, scope)

        # 依赖解析：使用依赖项自身类型对应的 Provider
        for dep_id in manifest.dependencies:
            dep_manifest = self._source_registry.get_manifest(dep_id)
            if dep_manifest is None:
                return InstallResult(
                    success=False,
                    capability_id=cap_id,
                    message=f"依赖 '{dep_id}' 在源仓库中不存在",
                )
            dep_provider = _PROVIDER_MAP.get(dep_manifest.kind)
            if dep_provider is None:
                return InstallResult(
                    success=False,
                    capability_id=cap_id,
                    message=f"依赖 '{dep_id}' 类型未知: {dep_manifest.kind}",
                )
            dep_ctx = CapabilityProviderContext(scope=scope)
            if not dep_provider.is_installed(dep_id, target_path, dep_ctx):
                dep_result = self.install(
                    dep_id, workspace_path, config=config, scope=scope, _visited=_visited
                )
                if not dep_result.success:
                    return InstallResult(
                        success=False,
                        capability_id=cap_id,
                        message=f"依赖 '{dep_id}' 安装失败: {dep_result.message}",
                    )

        source_dir = Path(manifest.source_dir)
        if not source_dir.exists():
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"源目录不存在: {manifest.source_dir}",
            )

        context = self._build_provider_context(workspace_path, scope)
        result = provider.install(cap_id, target_path, source_dir, config, context)
        if result.success:
            self._write_declaration(
                target_path,
                WorkspaceCapability(
                    capability_id=cap_id,
                    kind=manifest.kind,
                    enabled=True,
                    source=self._infer_source(source_dir),
                    version=manifest.version,
                    config=config or {},
                ),
            )
        return result

    def uninstall(
        self, cap_id: str, workspace_path: Path, scope: Scope = "workspace"
    ) -> InstallResult:
        """从目标作用域卸载能力。"""
        target_path = self._resolve_target_path(workspace_path, scope)
        manifest = self._source_registry.get_manifest(cap_id)
        provider = _PROVIDER_MAP.get(manifest.kind) if manifest else None
        declarations = self._read_declarations(target_path)
        ctx = CapabilityProviderContext(scope=scope)
        if provider is None:
            # 尝试从所有 provider 中找到已安装的
            for p in _PROVIDER_MAP.values():
                if p.is_installed(cap_id, target_path, ctx):
                    provider = p
                    break
            if provider is None and cap_id in declarations:
                provider = _PROVIDER_MAP.get(declarations[cap_id].kind)

        if provider is None:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"能力 '{cap_id}' 未安装",
            )

        if cap_id in declarations and not provider.is_installed(cap_id, target_path, ctx):
            self._remove_declaration(target_path, cap_id)
            return InstallResult(
                success=True,
                capability_id=cap_id,
                message=f"能力 '{cap_id}' 安装内容不存在，已清理声明",
            )

        context = self._build_provider_context(workspace_path, scope)
        result = provider.uninstall(cap_id, target_path, context)
        if result.success:
            self._remove_declaration(target_path, cap_id)
        return result

    def activate(
        self, cap_id: str, workspace_path: Path, scope: Scope = "workspace"
    ) -> InstallResult:
        target_path = self._resolve_target_path(workspace_path, scope)
        manifest = self._source_registry.get_manifest(cap_id)
        provider = _PROVIDER_MAP.get(manifest.kind) if manifest else None
        if provider is None:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"未知能力: {cap_id}",
            )

        context = self._build_provider_context(workspace_path, scope)
        result = provider.activate(cap_id, target_path, context)
        if result.success:
            self._update_declaration_enabled(target_path, cap_id, True)
        return result

    def deactivate(
        self, cap_id: str, workspace_path: Path, scope: Scope = "workspace"
    ) -> InstallResult:
        target_path = self._resolve_target_path(workspace_path, scope)
        manifest = self._source_registry.get_manifest(cap_id)
        provider = _PROVIDER_MAP.get(manifest.kind) if manifest else None
        if provider is None:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"未知能力: {cap_id}",
            )

        declarations = self._read_declarations(target_path)
        ctx = CapabilityProviderContext(scope=scope)
        if cap_id in declarations and not provider.is_installed(cap_id, target_path, ctx):
            self._remove_declaration(target_path, cap_id)
            return InstallResult(
                success=True,
                capability_id=cap_id,
                message=f"能力 '{cap_id}' 安装内容不存在，已清理声明",
            )

        context = self._build_provider_context(workspace_path, scope)
        result = provider.deactivate(cap_id, target_path, context)
        if result.success:
            if provider.is_installed(cap_id, target_path, ctx):
                self._update_declaration_enabled(target_path, cap_id, False)
            else:
                self._remove_declaration(target_path, cap_id)
        return result

    def verify(self, cap_id: str, workspace_path: Path, scope: Scope = "workspace") -> HealthStatus:
        target_path = self._resolve_target_path(workspace_path, scope)
        manifest = self._source_registry.get_manifest(cap_id)
        provider = _PROVIDER_MAP.get(manifest.kind) if manifest else None
        if provider is None:
            return HealthStatus(
                status=CapabilityStatus.ERROR,
                detail="未知能力类型",
            )
        context = self._build_provider_context(workspace_path, scope)
        return provider.verify(cap_id, target_path, context)

    def verify_scope(
        self, workspace_path: Path, scope: Scope = "workspace"
    ) -> dict[str, HealthStatus]:
        """验活目标作用域所有已启用的能力。"""
        target_path = self._resolve_target_path(workspace_path, scope)
        declarations = self._read_declarations(target_path)
        results: dict[str, HealthStatus] = {}
        ctx = CapabilityProviderContext(scope=scope)
        for cap_id, decl in declarations.items():
            if not decl.enabled:
                continue
            manifest = self._source_registry.get_manifest(cap_id)
            provider = _PROVIDER_MAP.get(manifest.kind) if manifest else None
            if provider is None:
                results[cap_id] = HealthStatus(
                    status=CapabilityStatus.ERROR,
                    detail="未知能力类型",
                )
                continue
            context = self._build_provider_context(workspace_path, scope)
            results[cap_id] = provider.verify(cap_id, target_path, context)
        return results

    # ---- 模板集成 ----

    def apply_template_declaration(
        self,
        workspace_path: Path,
        declarations: list[CapabilityDeclaration],
    ) -> list[InstallResult]:
        """模板创建时批量应用能力声明。"""
        results: list[InstallResult] = []
        for decl in declarations:
            if not decl.auto_activate and not decl.required:
                # 可选且不自动激活：只安装，不激活
                result = self.install(decl.capability_id, workspace_path, decl.config)
                if result.success:
                    self.deactivate(decl.capability_id, workspace_path)
                results.append(result)
            else:
                # 必须项或自动激活：安装并激活
                results.append(self.install(decl.capability_id, workspace_path, decl.config))
        return results

    # ---- 工作区声明读写 ----

    def _read_declarations(self, workspace_path: Path) -> dict[str, WorkspaceCapability]:
        """读取工作区 capabilities.toml。"""
        cap_path = workspace_path / ".aiasys" / "capabilities.toml"
        if not cap_path.exists():
            # 回退：从旧格式自动生成
            return self._migrate_from_legacy(workspace_path)

        try:
            raw: dict[str, Any] = tomllib.loads(cap_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("capabilities.toml 读取失败 %s: %s", cap_path, exc)
            return {}

        caps: dict[str, WorkspaceCapability] = {}
        for cap_id, item in (raw.get("capabilities") or {}).items():
            if not isinstance(item, dict):
                continue
            kind_str = str(item.get("kind", "")).strip()
            try:
                kind = CapabilityKind(kind_str)
            except ValueError:
                kind = CapabilityKind.NATIVE_TOOL
            caps[cap_id] = WorkspaceCapability(
                capability_id=cap_id,
                kind=kind,
                enabled=bool(item.get("enabled", False)),
                source=str(item.get("source", "")).strip(),
                version=str(item.get("version", "")).strip(),
                config=item.get("config") or {},
                installed_at=str(item.get("installed_at", "")).strip(),
            )
        return caps

    def _write_declaration(self, workspace_path: Path, cap: WorkspaceCapability) -> None:
        """写入或更新单条能力声明。"""
        declarations = self._read_declarations(workspace_path)
        declarations[cap.capability_id] = cap
        self._save_declarations(workspace_path, declarations)

    def _remove_declaration(self, workspace_path: Path, cap_id: str) -> None:
        declarations = self._read_declarations(workspace_path)
        declarations.pop(cap_id, None)
        self._save_declarations(workspace_path, declarations)

    def _update_declaration_enabled(self, workspace_path: Path, cap_id: str, enabled: bool) -> None:
        declarations = self._read_declarations(workspace_path)
        if cap_id in declarations:
            declarations[cap_id].enabled = enabled
            self._save_declarations(workspace_path, declarations)

    def _save_declarations(
        self, workspace_path: Path, declarations: dict[str, WorkspaceCapability]
    ) -> None:
        cap_path = workspace_path / ".aiasys" / "capabilities.toml"
        data: dict[str, Any] = {
            "version": "1.0",
            "capabilities": {},
        }
        for cap_id, cap in declarations.items():
            data["capabilities"][cap_id] = {
                "kind": cap.kind.value,
                "enabled": cap.enabled,
                "source": cap.source,
                "version": cap.version,
                "config": cap.config,
                "installed_at": cap.installed_at,
            }
        try:
            cap_path.parent.mkdir(parents=True, exist_ok=True)
            cap_path.write_text(
                tomli_w.dumps(data),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("capabilities.toml 写入失败 %s: %s", cap_path, exc)

    def _migrate_from_legacy(self, workspace_path: Path) -> dict[str, WorkspaceCapability]:
        """从旧格式（.aiasys/skills/ 目录 + mcp_config.json）迁移到统一声明。"""
        declarations: dict[str, WorkspaceCapability] = {}

        # 迁移 Skill
        skills_dir = workspace_path / ".aiasys" / "skills"
        if skills_dir.exists():
            for entry in skills_dir.iterdir():
                if entry.is_dir() and not entry.name.startswith("."):
                    declarations[entry.name] = WorkspaceCapability(
                        capability_id=entry.name,
                        kind=CapabilityKind.SKILL_PACK,
                        enabled=True,
                        source="legacy",
                    )

        # 迁移 MCP
        mcp_path = workspace_path / ".aiasys" / "mcp_config.json"
        if mcp_path.exists():
            try:
                import json

                mcp_data = json.loads(mcp_path.read_text(encoding="utf-8"))
                servers = mcp_data.get("servers", {})
                disabled = set(mcp_data.get("disabled_servers", []))
                for server_name in servers:
                    declarations[server_name] = WorkspaceCapability(
                        capability_id=server_name,
                        kind=CapabilityKind.MCP_SERVER,
                        enabled=server_name not in disabled,
                        source="legacy",
                    )
            except Exception:
                logger.warning("迁移 MCP 配置失败", exc_info=True)

        return declarations

    # ---- 工具方法 ----

    def _infer_source(self, source_dir: Path) -> str:
        """从源目录路径推断来源（builtin / store）。"""
        parts = source_dir.resolve().parts
        if "builtin" in parts:
            return "builtin"
        if "store" in parts:
            return "store"
        return "unknown"

    def _resolve_target_path(self, workspace_path: Path, scope: Scope) -> Path:
        """根据 scope 解析目标路径。"""
        if scope == "global":
            return workspace_path.parent / "global_workspace"
        return workspace_path

    def _build_provider_context(
        self, workspace_path: Path, scope: Scope = "workspace"
    ) -> CapabilityProviderContext:
        """从标准工作区路径推导 provider 上下文。

        注意：当前从路径层级推断 user_id / workspace_id，假设路径符合标准结构。
        非标准路径下推断结果可能错误，未来应从调用方显式传入身份信息。
        """
        try:
            resolved = workspace_path.resolve()
            user_id = resolved.parent.name if resolved.name != "global_workspace" else None
            workspace_id = resolved.name
            return CapabilityProviderContext(
                user_id=user_id or None,
                workspace_id=workspace_id or None,
                scope=scope,
            )
        except Exception:
            return CapabilityProviderContext(scope=scope)


# 单例
_capability_manager: CapabilityManager | None = None


def get_capability_manager() -> CapabilityManager:
    global _capability_manager
    if _capability_manager is None:
        _capability_manager = CapabilityManager()
    return _capability_manager
