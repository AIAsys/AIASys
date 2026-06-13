"""协作专家（子 Agent）管理工具。

提供 Agent 发现、安装和配置系统专家/自定义专家的能力：
- ListSystemExperts: 列出当前工作区可见的专家目录
- InstallExpert: 将系统内置专家安装到当前工作区或我的默认
- ConfigureExpert: 启用/禁用或配置已安装专家
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_session_id, current_user_id, current_workspace


class ListSystemExpertsParams(BaseModel):
    """ListSystemExperts 参数。"""

    query: str = Field(
        default="",
        description="按名称或描述过滤的关键词。为空时返回全部。",
    )


class InstallExpertParams(BaseModel):
    """InstallExpert 参数。"""

    name: str = Field(description="专家角色 ID，如 data_analyst、coder、researcher")
    scope: str = Field(
        default="workspace",
        description="安装目标：workspace（当前工作区）或 global（我的默认）",
    )


class ConfigureExpertParams(BaseModel):
    """ConfigureExpert 参数。"""

    name: str = Field(description="专家角色 ID")
    scope: str = Field(
        default="workspace",
        description="配置目标：workspace（当前工作区）或 global（我的默认）",
    )
    enabled: bool = Field(
        default=True,
        description="true 表示启用该专家到当前会话候选；false 表示禁用但不卸载",
    )
    catalog_visible: bool | None = Field(
        default=None,
        description="是否在专家目录中展示。不传则保持原值。",
    )
    host_selectable: bool | None = Field(
        default=None,
        description="是否允许主控选择该专家。不传则保持原值。",
    )


def _resolve_user_workspace(
    ctx: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """从当前上下文解析 user_id 和 workspace_id。

    优先通过 session_id 到 workspace_registry 查询真实 workspace_id；
    回退到 current_workspace 路径的最后一个目录名。
    """
    user_id = current_user_id.get()
    if not user_id:
        raise ValueError("当前上下文未设置用户 ID")

    workspace_id: str | None = None

    # 1. 优先用 ctx / contextvar 中的 session_id 反查 workspace_id
    ctx = ctx or {}
    session_id = ctx.get("session_id") or current_session_id.get()
    if session_id:
        from app.services.workspace_registry import get_workspace_registry_service

        workspace_id = get_workspace_registry_service().find_workspace_id_by_session_id(
            user_id, str(session_id)
        )

    # 2. 回退到 current_workspace 路径名
    if not workspace_id:
        workspace_path = current_workspace.get()
        if workspace_path is not None:
            workspace_id = workspace_path.name

    if not workspace_id:
        raise ValueError("当前上下文缺少工作区 ID")

    return user_id, workspace_id


class ListSystemExperts(AiasysTool):
    """列出当前工作区可见的系统专家和自定义专家目录。"""

    name: str = "ListSystemExperts"
    risk_level: str = "readonly"
    effect_scope: str = "session"
    side_effect: bool = False
    description: str = """列出当前工作区可用的协作专家（子 Agent）目录。

返回信息包括：
- role_id: 专家角色 ID
- display_name: 展示名称
- description: 专家描述
- source: system / global / workspace
- installed_to_global: 是否已安装到我的默认
- installed_to_workspace: 是否已安装到当前工作区
- default_enabled: 是否默认启用
- capabilities: 能力标签

使用场景：
- 用户问"有哪些专家可以用"时
- 安装专家前查看候选列表时
- 配置专家前确认专家状态时

注意：本工具列出的是专家目录，不是 Skill。不要与 ListSkills / SearchStoreSkills 混淆。
"""
    params: type[BaseModel] = ListSystemExpertsParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ListSystemExpertsParams.model_validate(kwargs)

        try:
            user_id, workspace_id = _resolve_user_workspace(ctx)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        from app.services.expert_roles import get_workspace_expert_catalog

        try:
            catalog = get_workspace_expert_catalog(
                user_id=user_id,
                workspace_id=workspace_id,
            )
        except Exception as exc:
            return ToolResult(content=f"读取专家目录失败: {exc}", is_error=True)

        query = params.query.strip().lower() if params.query else ""
        roles = []
        for role in catalog.roles:
            if query:
                haystack = f"{role.role_id} {role.display_name} {role.description} {' '.join(role.capabilities)}".lower()
                if query not in haystack:
                    continue
            roles.append(
                {
                    "role_id": role.role_id,
                    "display_name": role.display_name,
                    "description": role.description,
                    "when_to_use": role.when_to_use,
                    "source": role.source,
                    "installed_scope": role.installed_scope,
                    "installed_to_global": role.installed_to_global,
                    "installed_to_workspace": role.installed_to_workspace,
                    "default_enabled": role.default_enabled,
                    "host_selectable": role.host_selectable,
                    "catalog_visible": role.catalog_visible,
                    "capabilities": role.capabilities,
                    "tool_count": role.tool_count,
                }
            )

        return ToolResult(
            content=f"当前工作区可见专家共 {len(roles)} 个",
            artifacts=[{"experts": roles}],
        )


class InstallExpert(AiasysTool):
    """将系统内置专家安装到当前工作区或我的默认。"""

    name: str = "InstallExpert"
    risk_level: str = "medium"
    effect_scope: str = "workspace"
    side_effect: bool = True
    description: str = """将系统内置专家安装到当前工作区或我的默认。

参数：
- name: 专家角色 ID（如 data_analyst、coder、researcher、reviewer）
- scope: workspace（当前工作区，默认）或 global（我的默认）

使用场景：
- 用户明确要求安装某个专家时
- 当前任务需要某个专家能力，且该专家尚未安装时
- 想让某个专家成为我的默认配置时，选择 global

注意：
- 只能安装系统内置专家（ListSystemExperts 中 source=system 的角色）
- 安装后该专家会出现在当前工作区的已安装列表中
- 安装不等于启用；安装后通常默认启用，可用 ConfigureExpert 调整
"""
    params: type[BaseModel] = InstallExpertParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = InstallExpertParams.model_validate(kwargs)

        try:
            user_id, workspace_id = _resolve_user_workspace(ctx)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        name = params.name.strip()
        if not name:
            return ToolResult(content="name 参数不能为空", is_error=True)

        scope = params.scope.strip().lower() if params.scope else "workspace"
        if scope not in {"workspace", "global"}:
            return ToolResult(
                content="scope 必须是 workspace 或 global",
                is_error=True,
            )

        if scope == "workspace" and not workspace_id:
            return ToolResult(
                content="当前上下文缺少工作区 ID，无法安装到 workspace",
                is_error=True,
            )

        from app.services.agent.subagent_catalog import (
            enable_builtin_subagent_to_scope,
            is_system_subagent_name,
            load_subagent,
        )

        if not is_system_subagent_name(name):
            return ToolResult(
                content=f"'{name}' 不是系统内置专家，无法通过 InstallExpert 安装。",
                is_error=True,
            )

        try:
            enable_builtin_subagent_to_scope(
                user_id=user_id,
                name=name,
                scope=scope,
                workspace_id=workspace_id,
            )
            manifest = load_subagent(
                user_id=user_id,
                name=name,
                workspace_id=workspace_id,
            )
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)
        except Exception as exc:
            return ToolResult(content=f"安装专家失败: {exc}", is_error=True)

        if manifest is None:
            return ToolResult(content="安装后读取专家配置失败", is_error=True)

        return ToolResult(
            content=f"专家 '{name}' 已成功安装到 {scope}",
            artifacts=[
                {
                    "name": name,
                    "scope": scope,
                    "description": manifest.get("description", ""),
                    "model": manifest.get("model"),
                    "source": str(
                        manifest.get("_source") or manifest.get("source") or "builtin"
                    ),
                }
            ],
        )


class ConfigureExpert(AiasysTool):
    """启用、禁用或配置已安装的专家（不卸载）。"""

    name: str = "ConfigureExpert"
    risk_level: str = "medium"
    effect_scope: str = "workspace"
    side_effect: bool = True
    description: str = """配置已安装专家的启用状态和可见性。

参数：
- name: 专家角色 ID
- scope: workspace（当前工作区，默认）或 global（我的默认）
- enabled: true（启用）或 false（禁用但不卸载）
- catalog_visible: 是否在专家目录中展示（可选）
- host_selectable: 是否允许主控选择（可选）

使用场景：
- 用户想让某个专家在当前会话中不出现时，传 enabled=false
- 用户想重新启用之前禁用的专家时，传 enabled=true
- 调整专家在目录中的可见性和可选性

注意：
- 只能配置已安装的专家（未安装的专家请先调用 InstallExpert）
- 本工具不会卸载或删除专家配置
- 禁用后专家仍会保留在已安装列表中
"""
    params: type[BaseModel] = ConfigureExpertParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ConfigureExpertParams.model_validate(kwargs)

        try:
            user_id, workspace_id = _resolve_user_workspace(ctx)
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)

        name = params.name.strip()
        if not name:
            return ToolResult(content="name 参数不能为空", is_error=True)

        scope = params.scope.strip().lower() if params.scope else "workspace"
        if scope not in {"workspace", "global"}:
            return ToolResult(
                content="scope 必须是 workspace 或 global",
                is_error=True,
            )

        if scope == "workspace" and not workspace_id:
            return ToolResult(
                content="当前上下文缺少工作区 ID，无法配置 workspace 专家",
                is_error=True,
            )

        from app.services.agent.subagent_catalog import (
            is_subagent_installed_to_scope,
            save_subagent_visibility_policy,
        )

        if not is_subagent_installed_to_scope(
            user_id=user_id,
            name=name,
            scope=scope,
            workspace_id=workspace_id,
        ):
            return ToolResult(
                content=f"专家 '{name}' 尚未安装到 {scope}，请先调用 InstallExpert 安装。",
                is_error=True,
            )

        try:
            settings = save_subagent_visibility_policy(
                user_id=user_id,
                role_id=name,
                scope=scope,
                workspace_id=workspace_id,
                default_enabled=params.enabled,
                catalog_visible=params.catalog_visible,
                host_selectable=params.host_selectable,
            )
        except ValueError as exc:
            return ToolResult(content=str(exc), is_error=True)
        except Exception as exc:
            return ToolResult(content=f"配置专家失败: {exc}", is_error=True)

        return ToolResult(
            content=f"专家 '{name}' 在 {scope} 的配置已更新",
            artifacts=[
                {
                    "name": name,
                    "scope": scope,
                    "default_enabled": settings.default_enabled,
                    "catalog_visible": settings.catalog_visible,
                    "host_selectable": settings.host_selectable,
                }
            ],
        )
