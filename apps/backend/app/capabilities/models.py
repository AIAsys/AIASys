"""统一能力层模型定义。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CapabilityKind(str, Enum):
    """能力类型。"""

    SKILL_PACK = "skill_pack"
    MCP_SERVER = "mcp_server"
    SUBAGENT = "subagent"
    NATIVE_TOOL = "native_tool"
    RUNTIME_HELPER = "runtime_helper"


class CapabilityStatus(str, Enum):
    """能力在工作区中的状态。"""

    AVAILABLE = "available"  # 源仓库存在，未安装
    INSTALLED = "installed"  # 已复制到工作区，但未激活
    ACTIVE = "active"  # 已配置完成，可工作
    ERROR = "error"  # 安装或验证失败
    DISABLED = "disabled"  # 用户手动禁用


@dataclass(frozen=True)
class CapabilityHealthcheck:
    """能力健康检查定义。"""

    ok: bool
    message: str = ""


@dataclass(frozen=True)
class HealthStatus:
    """能力验活结果。"""

    status: CapabilityStatus
    healthcheck: CapabilityHealthcheck | None = None
    detail: str = ""


@dataclass(frozen=True)
class InstallResult:
    """安装/卸载操作结果。"""

    success: bool
    capability_id: str
    message: str = ""


@dataclass(frozen=True)
class CapabilityManifest:
    """能力源仓库中的元数据（从 manifest.toml 解析）。"""

    capability_id: str
    kind: CapabilityKind
    display_name: str
    description: str = ""
    version: str = "1.0.0"
    author: str = ""
    dependencies: list[str] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    tool_names: list[str] = field(default_factory=list)
    min_platform_version: str = "0.1.0"
    source_dir: str = ""  # 源目录绝对路径


@dataclass
class WorkspaceCapability:
    """工作区中某项能力的实例状态（从 capabilities.toml 读取）。"""

    capability_id: str
    kind: CapabilityKind
    enabled: bool
    source: str = ""  # builtin / store / custom
    version: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    installed_at: str = ""
    error_message: str = ""


@dataclass(frozen=True)
class CapabilityDeclaration:
    """模板中声明的推荐能力项。"""

    capability_id: str
    kind: CapabilityKind
    required: bool = True
    auto_activate: bool = True
    config: dict[str, Any] = field(default_factory=dict)
