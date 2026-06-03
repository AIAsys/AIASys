"""MCP 管理工具。

提供 MCP Server 的发现和安装能力。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult


class ListMCPServersParams(BaseModel):
    """ListMCPServers 参数。"""

    scope: str = Field(
        default="store",
        description="查询范围：store（全局仓库，默认）或 workspace（当前工作区已安装）",
    )


class ListMCPServers(AiasysTool):
    """列出 MCP Server。"""

    name: str = "ListMCPServers"
    description: str = """列出 MCP Server。

参数：
- scope: 查询范围，store（全局仓库，默认）或 workspace（当前工作区已安装）

返回内容：
- name: Server 名称
- display_name: 显示名称
- type: 类型（stdio / sse / http）
- description: 描述
- is_system_default: 是否为系统默认

使用场景：
- 查看系统中有哪些 MCP Server 可用
- 查看当前工作区已安装了哪些 MCP Server
"""
    params: type[BaseModel] = ListMCPServersParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = ListMCPServersParams.model_validate(kwargs)

        from app.mcp import get_mcp_manager

        mgr = get_mcp_manager()
        scope = params.scope.strip().lower() if params.scope else "store"

        if scope == "workspace":
            user_id = str(ctx.get("user_id") or "").strip() if ctx else ""
            workspace_path = ctx.get("workspace") if ctx else None
            if not user_id or not workspace_path:
                return ToolResult(
                    content="workspace 范围查询需要会话上下文，当前暂只支持 store 范围。",
                    is_error=True,
                )
            try:
                servers = mgr.list_effective_servers(Path(str(workspace_path)))
                items = []
                for s in servers:
                    items.append(
                        {
                            "name": s.name,
                            "display_name": s.display_name,
                            "type": s.type,
                            "description": s.description,
                            "is_system_default": s.is_system_default,
                        }
                    )
                return ToolResult(
                    content=f"当前工作区共有 {len(items)} 个已安装的 MCP Server",
                    artifacts=[{"servers": items}],
                )
            except Exception as exc:
                return ToolResult(content=f"列出工作区 MCP Server 失败: {exc}", is_error=True)

        try:
            servers = mgr.list_store_servers("__system__")
            items = []
            for s in servers:
                items.append(
                    {
                        "name": s.name,
                        "display_name": s.display_name,
                        "type": s.type,
                        "description": s.description,
                        "is_system_default": s.is_system_default,
                    }
                )
            return ToolResult(
                content=f"MCP 仓库中共有 {len(items)} 个 Server",
                artifacts=[{"servers": items}],
            )
        except Exception as exc:
            return ToolResult(content=f"列出 MCP Server 失败: {exc}", is_error=True)


class SearchMCPMarketParams(BaseModel):
    """SearchMCPMarket 参数。"""

    query: str = Field(description="搜索关键词，例如 weather、天气、github")
    source_id: str = Field(
        default="modelscope",
        description="市场源 ID，默认 modelscope（ModelScope 市场），也可指定 aiasys（AIASys 精选）",
    )


class SearchMCPMarket(AiasysTool):
    """搜索外部 MCP 市场。"""

    name: str = "SearchMCPMarket"
    description: str = """在外部 MCP 市场中搜索可用的 MCP Server。

参数：
- query: 搜索关键词（例如 weather、天气、github）
- source_id: 市场源 ID，默认 modelscope

返回内容：
- item_id: 条目唯一 ID
- display_name: 显示名称
- publisher: 发布者
- description: 描述
- tags: 标签列表

使用场景：
- 用户想找一个特定功能的 MCP Server 但本地仓库没有
- 需要查看外部市场有哪些可用服务

注意：如果本地仓库已有满足需求的 Server，优先使用 ListMCPServers。
"""
    params: type[BaseModel] = SearchMCPMarketParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = SearchMCPMarketParams.model_validate(kwargs)

        from app.services.mcp_external_market_service import get_external_mcp_market_service

        service = get_external_mcp_market_service()
        try:
            result = await service.list_items(
                source_id=params.source_id,
                search=params.query,
                page_number=1,
                page_size=20,
            )
            items = []
            for item in result.items:
                items.append(
                    {
                        "item_id": item.item_id,
                        "display_name": item.display_name,
                        "publisher": item.publisher,
                        "description": item.description,
                        "tags": item.tags,
                        "categories": item.categories,
                    }
                )
            if not items:
                return ToolResult(
                    content=f"在 {params.source_id} 市场中未找到匹配 '{params.query}' 的 MCP Server。",
                    artifacts=[{"items": []}],
                )
            return ToolResult(
                content=f"在 {params.source_id} 市场中找到 {len(items)} 个匹配结果：",
                artifacts=[{"items": items}],
            )
        except Exception as exc:
            return ToolResult(content=f"搜索 MCP 市场失败: {exc}", is_error=True)


class InstallMCPServerParams(BaseModel):
    """InstallMCPServer 参数。"""

    name: str = Field(
        default="", description="本地仓库中的 MCP Server 名称（ListMCPServers 返回的 name 字段）"
    )
    item_id: str = Field(
        default="", description="外部市场条目 ID（SearchMCPMarket 返回的 item_id）"
    )
    source_id: str = Field(default="modelscope", description="外部市场源 ID，默认 modelscope")


class InstallMCPServer(AiasysTool):
    """安装 MCP Server 到当前工作区。"""

    name: str = "InstallMCPServer"
    description: str = """将指定的 MCP Server 安装到当前工作区。

参数（二选一）：
- name: 本地仓库中的 MCP Server 名称（ListMCPServers 返回的 name 字段）
- item_id: 外部市场条目 ID（SearchMCPMarket 返回的 item_id）
- source_id: 外部市场源 ID，配合 item_id 使用，默认 modelscope

使用场景：
- 用户要求安装某个 MCP Server 时
- Agent 发现需要某个 MCP 能力时

安装后该 Server 的工具会出现在当前工作区的可用工具列表中。
"""
    params: type[BaseModel] = InstallMCPServerParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = InstallMCPServerParams.model_validate(kwargs)

        # 外部市场导入
        if params.item_id:
            from app.mcp import get_mcp_manager
            from app.mcp.models import EnvField, MCPServerDefinition
            from app.services.mcp_external_market_service import get_external_mcp_market_service

            service = get_external_mcp_market_service()
            mgr = get_mcp_manager()
            try:
                configs = await service.build_import_configs(
                    source_id=params.source_id,
                    item_id=params.item_id,
                    enabled=True,
                )
                if not configs:
                    return ToolResult(
                        content=f"外部 MCP 条目 '{params.item_id}' 暂不支持导入。",
                        is_error=True,
                    )

                # 获取详情以保留 env_fields
                detail = await service.get_item_detail(
                    source_id=params.source_id,
                    item_id=params.item_id,
                )

                imported_names = []
                for server in configs:
                    definition = MCPServerDefinition(
                        name=server.name,
                        display_name=server.name,
                        type=server.type,
                        url=server.url,
                        headers=server.headers or {},
                        command=server.command,
                        args=server.args or [],
                        env=server.env or {},
                        env_fields=[
                            EnvField(
                                name=f.name,
                                required=f.required,
                                description=f.description,
                                default_value=f.default_value,
                            )
                            for f in detail.env_fields
                        ],
                        readme_excerpt=detail.readme_excerpt,
                        description=server.description,
                    )
                    result = mgr.save_store_server("__system__", definition, force=True)
                    if result.success:
                        imported_names.append(server.name)

                return ToolResult(
                    content=f"已导入 {len(imported_names)} 个 MCP Server：{', '.join(imported_names)}",
                    artifacts=[{"imported_names": imported_names}],
                )
            except Exception as exc:
                return ToolResult(content=f"导入 MCP Server 失败: {exc}", is_error=True)

        # 本地仓库安装
        if params.name:
            from app.mcp import get_mcp_manager

            mgr = get_mcp_manager()
            try:
                servers = mgr.list_store_servers("__system__")
                target = None
                for s in servers:
                    if s.name == params.name.strip():
                        target = s
                        break

                if target is None:
                    return ToolResult(
                        content=f"MCP Server '{params.name}' 不存在于仓库中。请先用 ListMCPServers 查看可用列表，或用 SearchMCPMarket 搜索外部市场。",
                        is_error=True,
                    )

                return ToolResult(
                    content=f"MCP Server '{target.display_name or target.name}' 已找到。实际安装需要通过工作区配置界面完成。",
                    artifacts=[
                        {
                            "name": target.name,
                            "display_name": target.display_name,
                            "type": target.type,
                            "description": target.description,
                        }
                    ],
                )
            except Exception as exc:
                return ToolResult(content=f"安装 MCP Server 失败: {exc}", is_error=True)

        return ToolResult(
            content="请提供 name（本地仓库）或 item_id（外部市场）参数。",
            is_error=True,
        )
