"""统一能力注册表模型。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class CapabilityKind(str, Enum):
    """能力类型。"""

    NATIVE_TOOL = "native_tool"
    MCP_SERVER = "mcp_server"
    SKILL_PACK = "skill_pack"
    SUBAGENT = "subagent"
    RUNTIME_HELPER = "runtime_helper"


class CapabilityStatus(str, Enum):
    """能力状态。"""

    ACTIVE = "active"
    BETA = "beta"
    PLANNED = "planned"
    DISABLED = "disabled"


class CapabilityEvidenceLevel(str, Enum):
    """能力证据等级。"""

    DECLARED = "declared"
    CONFIG_BACKED = "config_backed"
    RUNTIME_VERIFIED = "runtime_verified"


class CapabilitySecretRequirement(BaseModel):
    """能力依赖的密钥描述。"""

    name: str = Field(..., description="密钥名称")
    location: Literal["header", "env", "config"] = Field(
        ...,
        description="密钥配置位置",
    )
    required: bool = Field(default=True, description="是否必填")
    description: Optional[str] = Field(default=None, description="密钥说明")


class CapabilityHealthcheck(BaseModel):
    """能力健康检查描述。"""

    type: Literal["mcp_connection_test", "runtime_probe", "none"] = Field(
        ...,
        description="健康检查类型",
    )
    target: Optional[str] = Field(default=None, description="检查目标")
    description: Optional[str] = Field(default=None, description="检查说明")


class CapabilityDescriptor(BaseModel):
    """单个能力描述。"""

    capability_id: str = Field(..., description="稳定 capability ID")
    display_name: str = Field(..., description="展示名称")
    kind: CapabilityKind = Field(..., description="能力类型")
    provider: str = Field(..., description="能力提供方")
    category_id: str = Field(..., description="工具功能分类 ID")
    category_label: str = Field(..., description="工具功能分类名称")
    description: Optional[str] = Field(default=None, description="能力说明")
    default_enabled: bool = Field(default=False, description="系统默认是否启用")
    default_modes: List[str] = Field(
        default_factory=list,
        description="在哪些内部场景基线下默认启用；不是能力上限",
    )
    status: CapabilityStatus = Field(default=CapabilityStatus.ACTIVE, description="状态")
    evidence_level: CapabilityEvidenceLevel = Field(
        default=CapabilityEvidenceLevel.DECLARED,
        description="证据等级",
    )
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="配置结构摘要")
    secret_requirements: List[CapabilitySecretRequirement] = Field(
        default_factory=list,
        description="密钥依赖描述",
    )
    healthcheck: Optional[CapabilityHealthcheck] = Field(
        default=None,
        description="健康检查定义",
    )

    @field_validator("default_modes", mode="before")
    @classmethod
    def _normalize_default_modes(cls, value: Optional[List[str]]) -> List[str]:
        if not value:
            return []
        normalized: List[str] = []
        for item in value:
            mode = str(item).strip().lower()
            if mode and mode not in normalized:
                normalized.append(mode)
        return normalized


class ModeCapabilityPreset(BaseModel):
    """内部场景基线的默认工具集合。"""

    mode: str = Field(..., description="内部场景标记")
    capability_ids: List[str] = Field(default_factory=list, description="默认 capability IDs")
    source_config_path: str = Field(..., description="默认 Agent preset / 配置来源")
    notes: Optional[str] = Field(default=None, description="补充说明")


class CapabilityRegistryResponse(BaseModel):
    """能力注册表响应。"""

    analysis_sandbox_mode: str = Field(..., description="analysis 当前预览使用的 sandbox mode")
    capabilities: List[CapabilityDescriptor] = Field(
        default_factory=list,
        description="系统可识别的 capability 列表",
    )
    mode_presets: List[ModeCapabilityPreset] = Field(
        default_factory=list,
        description="按内部场景基线组织的默认工具集合",
    )


class ToolCategorySummary(BaseModel):
    """工具功能分类目录项。"""

    category_id: str = Field(..., description="稳定工具分类 ID")
    display_name: str = Field(..., description="展示名称")
    description: str = Field(default="", description="工具分类说明")
    capability_ids: List[str] = Field(default_factory=list, description="包含的能力 ID")
    tool_names: List[str] = Field(default_factory=list, description="映射到的运行时工具名")
    permission_summary: List[str] = Field(default_factory=list, description="权限摘要")
    runtime_dependencies: List[str] = Field(default_factory=list, description="运行依赖")
    status: CapabilityStatus = Field(default=CapabilityStatus.ACTIVE)


class ToolCategoryRegistryResponse(BaseModel):
    """工具功能分类注册表响应。"""

    categories: List[ToolCategorySummary] = Field(default_factory=list)
    total: int = 0


class IntegrationMarketItem(BaseModel):
    """系统级扩展与集成市场条目。"""

    capability_id: str = Field(..., description="稳定 capability ID")
    display_name: str = Field(..., description="展示名称")
    kind: CapabilityKind = Field(..., description="集成类型")
    provider: str = Field(..., description="提供方")
    description: Optional[str] = Field(default=None, description="集成说明")
    status: CapabilityStatus = Field(
        default=CapabilityStatus.ACTIVE,
        description="条目本身的成熟度状态",
    )
    evidence_level: CapabilityEvidenceLevel = Field(
        default=CapabilityEvidenceLevel.DECLARED,
        description="当前状态证据等级",
    )
    default_modes: List[str] = Field(
        default_factory=list,
        description="默认推荐在哪些 mode 中启用；不是能力上限",
    )
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="配置结构摘要")
    secret_requirements: List[CapabilitySecretRequirement] = Field(
        default_factory=list,
        description="密钥依赖描述",
    )
    healthcheck: Optional[CapabilityHealthcheck] = Field(
        default=None,
        description="健康检查定义",
    )
    available: bool = Field(default=True, description="系统是否识别该集成")
    enabled: bool = Field(default=False, description="当前部署是否显式启用")
    configured: bool = Field(default=False, description="当前部署是否已满足最小配置")
    activation_state: Literal["ready", "needs_secret", "disabled"] = Field(
        default="disabled",
        description="当前部署下的激活状态",
    )
    activation_message: Optional[str] = Field(
        default=None,
        description="当前激活状态说明",
    )


class IntegrationMarketResponse(BaseModel):
    """系统级扩展与集成市场响应。"""

    items: List[IntegrationMarketItem] = Field(
        default_factory=list,
        description="当前系统识别的扩展与集成目录",
    )
    recommended_by_mode: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="各 mode 的默认推荐集成 ID 列表",
    )
    installed_capability_ids: List[str] = Field(
        default_factory=list,
        description="当前部署已显式启用的集成 ID",
    )
    active_capability_ids: List[str] = Field(
        default_factory=list,
        description="当前部署已配置完成、可立即使用的集成 ID",
    )
