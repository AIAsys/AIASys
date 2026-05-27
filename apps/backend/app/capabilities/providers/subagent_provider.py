"""子 Agent 类型能力 Provider。

安装/卸载动作：生成 TOML 配置 + 更新 visibility/collaboration policy。
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
from app.services.agent.subagent_catalog import (
    delete_subagent,
    save_subagent,
    save_subagent_visibility_policy,
)

logger = logging.getLogger(__name__)

SUBAGENT_CONFIG_DIR = ".aiasys/agent_config/subagents"


class SubagentProvider(CapabilityProvider):
    """子 Agent 能力 Provider。

    install    = 读取 manifest + prompt.md，生成 TOML 写入工作区/全局
    uninstall  = 删除 TOML + 清理 visibility policy
    activate   = 更新 visibility policy 和 collaboration policy
    deactivate = 反向操作
    verify     = 检查 TOML 完整性 + 模型可用性
    """

    def resolve_manifest(self, source_dir: Path) -> CapabilityManifest | None:
        manifest_path = source_dir / "manifest.toml"
        if not manifest_path.exists():
            return None
        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            logger.warning("Subagent manifest 解析失败 %s: %s", manifest_path, exc)
            return None

        cap_id = str(raw.get("capability_id", source_dir.name)).strip()
        if not cap_id:
            return None

        return CapabilityManifest(
            capability_id=cap_id,
            kind=CapabilityKind.SUBAGENT,
            display_name=str(raw.get("display_name", cap_id)).strip(),
            description=str(raw.get("description", "")).strip(),
            version=str(raw.get("version", "1.0.0")).strip(),
            author=str(raw.get("author", "")).strip(),
            dependencies=[],
            config_schema=raw.get("config_schema") or {},
            tool_names=[str(t).strip() for t in (raw.get("tools") or []) if str(t).strip()],
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
        user_id, workspace_id = self._require_workspace_context(context, workspace_path)
        if not user_id or not workspace_id:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message="无法解析工作区上下文",
            )

        manifest_path = source_dir / "manifest.toml"
        if not manifest_path.exists():
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message="manifest.toml 不存在",
            )

        try:
            raw: dict[str, Any] = tomllib.loads(manifest_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"manifest 解析失败: {exc}",
            )

        # 读取 prompt.md
        prompt_text = ""
        prompt_path = source_dir / "prompt.md"
        if prompt_path.exists():
            prompt_text = prompt_path.read_text(encoding="utf-8")

        manifest: dict[str, Any] = {
            "name": cap_id,
            "display_name": str(raw.get("display_name", cap_id)).strip(),
            "description": str(raw.get("description", "")).strip(),
            "system_prompt": prompt_text,
        }
        model = raw.get("model") or (raw.get("config_schema") or {}).get("model", {}).get("default")
        if model:
            manifest["model"] = model
        if raw.get("tools"):
            manifest["tools"] = list(raw["tools"])

        # 合并用户自定义 config
        if config:
            manifest.update(config)

        target_scope = context.scope if context else "workspace"
        try:
            save_subagent(
                user_id=user_id,
                name=cap_id,
                manifest=manifest,
                scope=target_scope,
                workspace_id=workspace_id,
                source="builtin",
                status="active",
            )
        except Exception as exc:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"TOML 写入失败: {exc}",
            )

        save_subagent_visibility_policy(
            user_id=user_id,
            role_id=cap_id,
            scope=target_scope,
            workspace_id=workspace_id,
            catalog_visible=True,
            host_selectable=True,
            default_enabled=True,
        )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"子 Agent '{cap_id}' 已安装",
        )

    def uninstall(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        user_id, workspace_id = self._require_workspace_context(context, workspace_path)
        if not user_id or not workspace_id:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message="无法解析工作区上下文",
            )
        target_scope = context.scope if context else "workspace"
        try:
            deleted = delete_subagent(
                user_id=user_id,
                name=cap_id,
                scope=target_scope,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"删除子 Agent 配置失败: {exc}",
            )

        if not deleted:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"子 Agent '{cap_id}' 未安装",
            )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"子 Agent '{cap_id}' 已卸载",
        )

    def activate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        user_id, workspace_id = self._require_workspace_context(context, workspace_path)
        if not user_id or not workspace_id:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message="无法解析工作区上下文",
            )
        if not self._toml_path(cap_id, workspace_path).exists():
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"子 Agent '{cap_id}' 未安装",
            )

        target_scope = context.scope if context else "workspace"
        save_subagent_visibility_policy(
            user_id=user_id,
            role_id=cap_id,
            scope=target_scope,
            workspace_id=workspace_id,
            catalog_visible=True,
            host_selectable=True,
            default_enabled=True,
        )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"子 Agent '{cap_id}' 已激活",
        )

    def deactivate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        user_id, workspace_id = self._require_workspace_context(context, workspace_path)
        if not user_id or not workspace_id:
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message="无法解析工作区上下文",
            )
        if not self._toml_path(cap_id, workspace_path).exists():
            return InstallResult(
                success=False,
                capability_id=cap_id,
                message=f"子 Agent '{cap_id}' 未安装",
            )
        target_scope = context.scope if context else "workspace"
        save_subagent_visibility_policy(
            user_id=user_id,
            role_id=cap_id,
            scope=target_scope,
            workspace_id=workspace_id,
            catalog_visible=True,
            host_selectable=False,
            default_enabled=False,
        )

        return InstallResult(
            success=True,
            capability_id=cap_id,
            message=f"子 Agent '{cap_id}' 已禁用",
        )

    def verify(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> HealthStatus:
        toml_path = self._toml_path(cap_id, workspace_path)
        if not toml_path.exists():
            return HealthStatus(
                status=CapabilityStatus.AVAILABLE,
                detail="未安装",
            )

        try:
            data: dict[str, Any] = tomllib.loads(toml_path.read_text(encoding="utf-8")) or {}
        except Exception as exc:
            return HealthStatus(
                status=CapabilityStatus.ERROR,
                detail=f"TOML 解析失败: {exc}",
            )

        manifest = data.get("agent") if isinstance(data.get("agent"), dict) else data
        prompt_path_raw = str(manifest.get("system_prompt_path") or "").strip()
        prompt_path = (
            Path(prompt_path_raw) if prompt_path_raw else self._prompt_path(cap_id, workspace_path)
        )
        if prompt_path_raw and not prompt_path.is_absolute():
            prompt_path = toml_path.parent / prompt_path
        if not prompt_path.exists():
            return HealthStatus(
                status=CapabilityStatus.ERROR,
                detail="缺少 system prompt 文件",
            )

        # 检查 visibility policy 状态
        policy = self._load_visibility_policy(workspace_path)
        roles = policy.get("roles", {})
        role_policy = roles.get(cap_id, {})
        if not role_policy.get("host_selectable", False):
            return HealthStatus(
                status=CapabilityStatus.DISABLED,
                detail="已禁用",
            )

        return HealthStatus(
            status=CapabilityStatus.ACTIVE,
            detail="正常",
        )

    def is_installed(
        self, cap_id: str, workspace_path: Path, context: CapabilityProviderContext | None = None
    ) -> bool:
        return self._toml_path(cap_id, workspace_path).exists()

    # ---- 内部方法 ----

    def _agent_config_dir(self, workspace_path: Path) -> Path:
        return workspace_path / SUBAGENT_CONFIG_DIR

    def _toml_path(self, cap_id: str, workspace_path: Path) -> Path:
        return self._agent_config_dir(workspace_path) / f"{cap_id}.toml"

    def _prompt_path(self, cap_id: str, workspace_path: Path) -> Path:
        return self._agent_config_dir(workspace_path) / f"{cap_id}_prompt.md"

    def _load_visibility_policy(self, workspace_path: Path) -> dict[str, Any]:
        policy_path = workspace_path / ".aiasys" / "agent_config" / "collaboration_roles.json"
        if not policy_path.exists():
            return {"roles": {}}
        try:
            import json

            return json.loads(policy_path.read_text(encoding="utf-8")) or {"roles": {}}
        except Exception:
            return {"roles": {}}

    def _require_workspace_context(
        self,
        context: CapabilityProviderContext | None,
        workspace_path: Path,
    ) -> tuple[str | None, str | None]:
        if context and context.user_id and context.workspace_id:
            return context.user_id, context.workspace_id
        try:
            resolved = workspace_path.resolve()
            return resolved.parent.name or None, resolved.name or None
        except Exception:
            return None, None
