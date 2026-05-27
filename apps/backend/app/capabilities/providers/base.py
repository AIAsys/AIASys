"""CapabilityProvider 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from app.capabilities.models import (
    CapabilityManifest,
    HealthStatus,
    InstallResult,
)

Scope = Literal["global", "workspace"]


@dataclass(frozen=True)
class CapabilityProviderContext:
    """Provider 执行时可选上下文。"""

    user_id: str | None = None
    workspace_id: str | None = None
    scope: Scope = "workspace"


class CapabilityProvider(ABC):
    """能力类型 Provider 抽象基类。

    每种能力类型（skill_pack / mcp_server / subagent）需要实现此接口，
    供 CapabilityManager 统一调用。
    """

    @abstractmethod
    def resolve_manifest(self, source_dir: Path) -> CapabilityManifest | None:
        """从源目录解析 manifest。"""

    def _resolve_target_path(
        self, cap_id: str, workspace_path: Path, context: CapabilityProviderContext | None
    ) -> Path:
        """根据 scope 解析目标路径。global 时使用 global_workspace。"""
        scope = context.scope if context else "workspace"
        if scope == "global":
            return workspace_path.parent / "global_workspace"
        return workspace_path

    @abstractmethod
    def install(
        self,
        cap_id: str,
        workspace_path: Path,
        source_dir: Path,
        config: dict[str, Any] | None = None,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        """将能力从源目录安装到目标作用域。"""

    @abstractmethod
    def uninstall(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        """从目标作用域卸载能力。"""

    @abstractmethod
    def activate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        """激活已安装的能力（使其可用）。"""

    @abstractmethod
    def deactivate(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> InstallResult:
        """禁用已激活的能力（保留安装文件）。"""

    @abstractmethod
    def verify(
        self,
        cap_id: str,
        workspace_path: Path,
        context: CapabilityProviderContext | None = None,
    ) -> HealthStatus:
        """验活能力，返回当前健康状态。"""

    def is_installed(
        self, cap_id: str, workspace_path: Path, context: CapabilityProviderContext | None = None
    ) -> bool:
        """检查能力是否已安装到目标作用域（子类可覆盖）。"""
        return False
