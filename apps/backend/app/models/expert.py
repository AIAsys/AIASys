from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.session import SessionCollaborationPolicy


class ExpertRoleSummary(BaseModel):
    role_id: str = Field(..., description="角色 ID，对应 subagent_type")
    display_name: str = Field(..., description="前端展示名称")
    description: str = Field(..., description="角色说明")
    when_to_use: str = Field(default="", description="主控何时应选择此角色")
    default_model: str | None = Field(default=None, description="角色默认模型")
    tool_policy: Literal["inherit", "allowlist"] = Field(
        default="allowlist",
        description="角色工具策略摘要",
    )
    tool_ids: list[str] = Field(
        default_factory=list,
        description="角色系统上限工具 ID 列表",
    )
    tool_names: list[str] = Field(default_factory=list, description="工具短名称列表")
    tool_count: int = Field(default=0, description="工具数量")
    permissions: list[str] = Field(default_factory=list, description="权限摘要标签")
    capabilities: list[str] = Field(default_factory=list, description="能力摘要标签")
    supports_background: bool = Field(default=True, description="是否支持后台运行")
    agent_file: str = Field(..., description="角色基线 / 配置标识")
    source: Literal["system", "global", "workspace", "custom"] = Field(
        default="system",
        description="目录来源",
    )
    catalog_visible: bool = Field(
        default=True,
        description="是否在协作专家目录中展示",
    )
    host_selectable: bool = Field(
        default=True,
        description="是否允许主控在当前会话中选择和派发",
    )
    default_enabled: bool = Field(
        default=False,
        description="是否已启用到用户默认层或工作区层",
    )
    visibility_source: Literal["system", "global", "workspace"] = Field(
        default="system",
        description="当前可见性策略来源层",
    )
    installed_to_global: bool = Field(
        default=False,
        description="是否已安装到我的默认层",
    )
    installed_to_workspace: bool = Field(
        default=False,
        description="是否已安装到当前工作区层",
    )
    installed_scope: Literal["system", "global", "workspace"] = Field(
        default="system",
        description="当前列表中的安装来源层",
    )
    lock_reason: str | None = Field(
        default=None,
        description="策略被锁定或不可选时的原因",
    )


class SubAgentVisibilitySettings(BaseModel):
    catalog_visible: bool = Field(default=True, description="是否在目录中展示")
    host_selectable: bool = Field(default=True, description="是否允许主控选择")
    default_enabled: bool = Field(default=False, description="是否已启用")
    visibility_source: Literal["system", "global", "workspace"] = Field(
        default="system",
        description="当前生效策略来源",
    )
    lock_reason: str | None = Field(default=None, description="锁定或不可选原因")


class UpdateSubAgentVisibilityRequest(BaseModel):
    catalog_visible: bool | None = Field(default=None, description="是否在目录中展示")
    host_selectable: bool | None = Field(default=None, description="是否允许主控选择")
    default_enabled: bool | None = Field(default=None, description="工作区是否启用")
    lock_reason: str | None = Field(default=None, description="锁定或不可选原因")


class SubAgentVisibilityPolicyResponse(BaseModel):
    role_id: str = Field(..., description="子 Agent / 专家角色 ID")
    scope: Literal["global", "workspace"] = Field(..., description="策略写入作用域")
    workspace_id: str | None = Field(default=None, description="工作区 ID")
    catalog_visible: bool = Field(default=True, description="是否在目录中展示")
    host_selectable: bool = Field(default=True, description="是否允许主控选择")
    default_enabled: bool = Field(default=False, description="是否已启用")
    visibility_source: Literal["system", "global", "workspace"] = Field(
        default="system",
        description="当前生效策略来源",
    )
    lock_reason: str | None = Field(default=None, description="锁定或不可选原因")
    policy: SubAgentVisibilitySettings | None = Field(
        default=None,
        description="生效策略完整对象",
    )


class WorkspaceExpertCatalogResponse(BaseModel):
    workspace_id: str = Field(..., description="工作区 ID")
    profile_name: str = Field(..., description="命中的 system preset / profile 标识")
    roles: list[ExpertRoleSummary] = Field(default_factory=list, description="协作专家目录")


class GlobalExpertCatalogResponse(BaseModel):
    scope: Literal["global"] = Field(default="global", description="用户默认层")
    profile_name: str = Field(..., description="命中的 system preset / profile 标识")
    roles: list[ExpertRoleSummary] = Field(default_factory=list, description="我的默认协作专家目录")


class WorkspaceCollaborationPolicyResponse(BaseModel):
    workspace_id: str = Field(..., description="工作区 ID")
    profile_name: str = Field(..., description="命中的 system preset / profile 标识")
    policy_mode: Literal["workspace"] = Field(
        default="workspace",
        description="工作区级协作专家配置",
    )
    configured_enabled_role_ids: list[str] | None = Field(
        default=None,
        description="工作区显式启用专家列表；为空表示按我的默认继承",
    )
    configured_role_tool_ids: dict[str, list[str]] | None = Field(
        default=None,
        description="工作区显式裁剪的角色工具子集",
    )
    effective_enabled_role_ids: list[str] = Field(
        default_factory=list,
        description="工作区实际启用的可派发角色列表",
    )
    effective_role_tool_ids: dict[str, list[str]] = Field(
        default_factory=dict,
        description="工作区实际生效的角色工具列表",
    )
    available_roles: list[ExpertRoleSummary] = Field(
        default_factory=list,
        description="工作区可见的协作专家目录",
    )
    collaboration_policy: SessionCollaborationPolicy = Field(
        default_factory=SessionCollaborationPolicy,
        description="工作区协作节点运行默认值",
    )
    policy_effect: Literal["next_run_only"] = Field(
        default="next_run_only",
        description="策略生效时机",
    )


class GlobalCollaborationPolicyResponse(BaseModel):
    scope: Literal["global"] = Field(default="global", description="用户默认层")
    profile_name: str = Field(..., description="命中的 system preset / profile 标识")
    policy_mode: Literal["global"] = Field(
        default="global",
        description="用户默认协作专家配置",
    )
    configured_enabled_role_ids: list[str] | None = Field(
        default=None,
        description="我的默认显式启用专家列表；为空表示未启用市场专家",
    )
    configured_role_tool_ids: dict[str, list[str]] | None = Field(
        default=None,
        description="全局显式裁剪的角色工具子集",
    )
    effective_enabled_role_ids: list[str] = Field(
        default_factory=list,
        description="我的默认实际启用的可派发专家列表",
    )
    effective_role_tool_ids: dict[str, list[str]] = Field(
        default_factory=dict,
        description="我的默认实际生效的专家工具列表",
    )
    available_roles: list[ExpertRoleSummary] = Field(
        default_factory=list,
        description="用户默认层可见的协作专家目录",
    )
    collaboration_policy: SessionCollaborationPolicy = Field(
        default_factory=SessionCollaborationPolicy,
        description="用户默认协作节点运行默认值",
    )
    policy_effect: Literal["next_run_only"] = Field(
        default="next_run_only",
        description="策略生效时机",
    )


class UpdateWorkspaceCollaborationPolicyRequest(BaseModel):
    enabled_role_ids: list[str] | None = Field(
        default=None,
        description="启用专家列表；传 null 表示继承上层默认",
    )
    role_tool_ids: dict[str, list[str]] | None = Field(
        default=None,
        description="角色工具子集；传 null 表示全部角色继承各自系统上限工具",
    )
    collaboration_policy: SessionCollaborationPolicy | None = Field(
        default=None,
        description="工作区协作节点运行默认值；不传表示保持不变",
    )


class EnableBuiltinExpertRequest(BaseModel):
    role_id: str = Field(..., description="系统提供的协作专家 ID")


class SessionExpertPolicyResponse(BaseModel):
    session_id: str = Field(..., description="会话 ID")
    profile_name: str = Field(..., description="命中的 system preset / profile 标识")
    policy_mode: Literal["inherit_all", "custom"] = Field(
        default="inherit_all",
        description="启用策略模式",
    )
    configured_enabled_role_ids: list[str] | None = Field(
        default=None,
        description="显式保存的启用专家列表；为空表示继承上层启用结果",
    )
    configured_role_tool_ids: dict[str, list[str]] | None = Field(
        default=None,
        description="显式保存的角色工具子集；为空表示所有角色继承各自系统上限工具",
    )
    effective_enabled_role_ids: list[str] = Field(
        default_factory=list,
        description="当前实际生效的启用专家列表",
    )
    effective_role_tool_ids: dict[str, list[str]] = Field(
        default_factory=dict,
        description="当前实际生效的角色工具列表（已叠加系统上限和任务级子集）",
    )
    available_roles: list[ExpertRoleSummary] = Field(
        default_factory=list,
        description="当前兼容投影可见的协作专家目录",
    )
    collaboration_policy: SessionCollaborationPolicy = Field(
        default_factory=SessionCollaborationPolicy,
        description="当前会话协作节点运行策略",
    )
    policy_effect: Literal["next_run_only"] = Field(
        default="next_run_only",
        description="策略生效时机",
    )


class CreateExpertRequest(BaseModel):
    name: str = Field(..., description="子 Agent 标识名（英文开头，仅字母数字下划线连字符）")
    description: str = Field(..., description="一句话描述，用于 UI 展示和 Task 工具选择")
    system_prompt: str = Field(..., description="完整的系统提示词（角色定义和指令）")
    model: str | None = Field(default=None, description="模型 ID（可选，默认继承 Host 配置）")
    tools: list[str] | None = Field(default=None, description="可用工具路径列表（可选）")
    scope: Literal["global", "workspace"] = Field(
        default="workspace",
        description="作用域：global=用户默认层，workspace=工作区级跨会话复用",
    )


class UpdateExpertRequest(BaseModel):
    description: str | None = Field(default=None, description="一句话描述")
    system_prompt: str | None = Field(default=None, description="完整的系统提示词")
    model: str | None = Field(default=None, description="模型 ID")
    tools: list[str] | None = Field(default=None, description="可用工具路径列表")


class ExpertDetailResponse(BaseModel):
    name: str = Field(..., description="子 Agent 标识名")
    description: str = Field(default="", description="一句话描述")
    system_prompt: str = Field(default="", description="完整的系统提示词")
    model: str | None = Field(default=None, description="模型 ID")
    tools: list[str] | None = Field(default=None, description="可用工具路径列表")
    scope: str = Field(..., description="作用域")
    source: str = Field(default="custom", description="来源：custom=用户创建，system=系统预设")
