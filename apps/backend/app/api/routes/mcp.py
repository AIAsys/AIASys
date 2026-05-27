"""
MCP 配置管理 API

提供 MCP Server 的 CRUD 和连接测试功能
"""

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import get_current_user
from app.core.config import WORKSPACE_DIR
from app.mcp import get_mcp_manager
from app.mcp.models import EnvField, MCPServerDefinition
from app.models.external_mcp_market import (
    ExternalMCPMarketDetailResponse,
    ExternalMCPMarketListResponse,
    ExternalMCPMarketSource,
    ImportExternalMCPRequest,
    ImportExternalMCPResponse,
)
from app.models.mcp import (
    MCPConnectionStatus,
    MCPServerConfig,
)
from app.models.user import UserInfo
from app.services.llm import get_mcp_config_service
from app.services.mcp_external_market_service import get_external_mcp_market_service


def _definition_to_server_config(definition: MCPServerDefinition) -> MCPServerConfig:
    """将 MCPServerDefinition 转换为 MCPServerConfig。"""
    return MCPServerConfig(
        name=definition.name,
        type=definition.type,
        url=definition.url,
        headers=definition.headers,
        command=definition.command,
        args=definition.args,
        env={},
        enabled=True,
        is_system_default=definition.is_system_default,
        auto_attach_modes=definition.auto_attach_modes,
        description=definition.description,
        timeout_ms=definition.timeout_ms,
    )


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])


class MCPStoreServerResponse(BaseModel):
    """全局仓库 MCP server 响应"""

    name: str
    display_name: str
    type: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    env_schema: dict[str, str] = Field(default_factory=dict)
    env_fields: list[dict] = Field(default_factory=list)
    readme_excerpt: Optional[str] = None
    description: Optional[str] = None
    timeout_ms: int = 30000
    is_system_default: bool = False
    auto_attach_modes: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)


class MCPStoreListResponse(BaseModel):
    """全局仓库 MCP 列表响应"""

    servers: List[MCPStoreServerResponse]
    total: int


class MCPWorkspaceServerResponse(BaseModel):
    """工作区 MCP server 响应"""

    name: str
    display_name: str
    type: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: list[str] = Field(default_factory=list)
    headers: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    env_schema: dict[str, str] = Field(default_factory=dict)
    description: Optional[str] = None
    timeout_ms: int = 30000
    enabled: bool = True
    is_system_default: bool = False
    auto_attach_modes: list[str] = Field(default_factory=list)
    enabled_tools: list[str] = Field(default_factory=list)


class MCPWorkspaceListResponse(BaseModel):
    """工作区 MCP 列表响应"""

    servers: List[MCPWorkspaceServerResponse]
    total: int


class MCPToolInfoResponse(BaseModel):
    """MCP 工具信息"""

    name: str
    description: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """测试连接响应"""

    name: str
    status: str
    tools_count: int = 0
    tools: List[MCPToolInfoResponse] = Field(default_factory=list)
    error_message: Optional[str] = None


class MCPWorkspaceToolsResponse(BaseModel):
    """工作区 MCP server 工具列表响应"""

    server_name: str
    tools: List[MCPToolInfoResponse]
    enabled_tools: List[str] = Field(default_factory=list)


class UpdateEnabledToolsRequest(BaseModel):
    """更新启用工具列表请求"""

    enabled_tools: List[str] = Field(default_factory=list)


@router.get("/external-market/sources", response_model=list[ExternalMCPMarketSource])
async def list_external_mcp_market_sources() -> list[ExternalMCPMarketSource]:
    """获取外部 MCP 市场源列表。"""
    service = get_external_mcp_market_service()
    return service.list_sources()


@router.get("/external-market/items", response_model=ExternalMCPMarketListResponse)
async def list_external_mcp_market_items(
    source_id: str,
    search: Optional[str] = None,
    page_number: int = 1,
    page_size: int = 20,
) -> ExternalMCPMarketListResponse:
    """获取外部 MCP 市场条目列表。"""
    service = get_external_mcp_market_service()
    try:
        return await service.list_items(
            source_id=source_id,
            search=search,
            page_number=page_number,
            page_size=page_size,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.get("/external-market/detail", response_model=ExternalMCPMarketDetailResponse)
async def get_external_mcp_market_item_detail(
    source_id: str,
    item_id: str,
) -> ExternalMCPMarketDetailResponse:
    """获取外部 MCP 市场条目详情。"""
    service = get_external_mcp_market_service()
    try:
        return await service.get_item_detail(source_id=source_id, item_id=item_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc


@router.post("/external-market/import", response_model=ImportExternalMCPResponse)
async def import_external_mcp_market_item(
    request: ImportExternalMCPRequest,
    current_user: UserInfo = Depends(get_current_user),
) -> ImportExternalMCPResponse:
    """将外部 MCP 市场条目导入到当前用户的 MCP 配置中。"""
    external_market_service = get_external_mcp_market_service()
    config_service = get_mcp_config_service()
    try:
        imported_servers = await external_market_service.build_import_configs(
            source_id=request.source_id,
            item_id=request.item_id,
            enabled=request.enabled,
            env_overrides=request.env_overrides,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Operation failed") from exc
    except Exception as exc:
        logger.error(
            "导入外部 MCP 市场条目失败: source=%s item=%s",
            request.source_id,
            request.item_id,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Internal server error") from exc

    # 获取详情以保留 env_fields 和 readme_excerpt
    try:
        detail = await external_market_service.get_item_detail(
            source_id=request.source_id,
            item_id=request.item_id,
        )
        env_fields = detail.env_fields
        readme_excerpt = detail.readme_excerpt
    except Exception:
        env_fields = []
        readme_excerpt = None

    mgr = get_mcp_manager()
    for server in imported_servers:
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
                for f in env_fields
            ],
            readme_excerpt=readme_excerpt,
            description=server.description,
            timeout_ms=server.timeout_ms,
        )
        result = mgr.save_store_server(current_user.user_id, definition, force=True)
        if not result.success:
            raise HTTPException(status_code=400, detail=result.message)

    imported_names = [server.name for server in imported_servers]
    return ImportExternalMCPResponse(
        source_id=request.source_id,
        item_id=request.item_id,
        imported_names=imported_names,
        imported_servers=imported_servers,
        message=f"已导入 {len(imported_names)} 个 MCP 配置到“我的 MCP”",
    )


async def _test_mcp_server_connection(
    *,
    server_name: str,
    server_config: MCPServerConfig,
    workspace_id: Optional[str] = None,
    current_user: Optional[UserInfo] = None,
) -> TestConnectionResponse:
    """测试 MCP Server 连接

    实际连接到 MCP Server，检查可用性和工具列表。
    如果提供了 workspace_id，成功后会缓存工具列表到工作区。
    """
    import asyncio

    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    # 测试连接
    try:
        tools_list: List[MCPToolInfoResponse] = []

        if server_config.type == "streamable-http":
            # HTTP 连接测试（Streamable HTTP 返回 3 个值：read, write, get_session_id）
            async with streamablehttp_client(
                server_config.url,
                headers=server_config.headers or None,
                timeout=max(server_config.timeout_ms / 1000.0, 1.0),
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=10.0)
                    tools = await asyncio.wait_for(session.list_tools(), timeout=10.0)
                    tools_list = [
                        MCPToolInfoResponse(name=t.name, description=t.description)
                        for t in (tools.tools or [])
                    ]

        elif server_config.type == "sse":
            # SSE 连接测试
            async with sse_client(
                server_config.url,
                headers=server_config.headers or None,
                timeout=max(server_config.timeout_ms / 1000.0, 1.0),
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=10.0)
                    tools = await asyncio.wait_for(session.list_tools(), timeout=10.0)
                    tools_list = [
                        MCPToolInfoResponse(name=t.name, description=t.description)
                        for t in (tools.tools or [])
                    ]

        elif server_config.type == "stdio":
            # STDIO 连接测试（仅验证配置）
            # STDIO 需要实际启动进程，这里只做基本验证
            if not server_config.command:
                raise ValueError("STDIO 类型必须提供 command")

            # 尝试启动进程并获取工具列表
            server_params = StdioServerParameters(
                command=server_config.command, args=server_config.args, env=server_config.env
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(session.initialize(), timeout=10.0)
                    tools = await asyncio.wait_for(session.list_tools(), timeout=10.0)
                    tools_list = [
                        MCPToolInfoResponse(name=t.name, description=t.description)
                        for t in (tools.tools or [])
                    ]

        # 缓存工具列表到工作区
        if workspace_id and current_user:
            mgr = get_mcp_manager()
            workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id
            mgr.cache_server_tools(
                workspace_path,
                server_name,
                [{"name": t.name, "description": t.description} for t in tools_list],
            )

        return TestConnectionResponse(
            name=server_name,
            status="connected",
            tools_count=len(tools_list),
            tools=tools_list,
        )

    except asyncio.TimeoutError:
        logger.warning(f"连接 MCP Server {server_name} 超时")
        return TestConnectionResponse(name=server_name, status="error", error_message="连接超时")
    except ExceptionGroup as e:
        logger.error(f"连接 MCP Server {server_name} 失败: {e}")
        from app.services.agent.runtime_backends.aiasys.mcp_client import (
            _summarize_base_exception,
        )

        detail = _summarize_base_exception(e)
        detail_lower = detail.lower()
        if "401" in detail or "unauthorized" in detail_lower:
            friendly = "连接被拒绝：需要认证（401 Unauthorized）。请检查该 MCP 的环境变量或 Headers 配置是否正确。"
        elif "403" in detail or "forbidden" in detail_lower:
            friendly = "连接被拒绝：权限不足（403 Forbidden）。请检查访问权限。"
        elif "404" in detail or "not found" in detail_lower:
            friendly = "连接失败：服务未找到（404 Not Found）。请检查 URL 是否正确。"
        elif "timeout" in detail_lower or "timed out" in detail_lower:
            friendly = "连接超时。请检查网络或 URL 是否可达。"
        elif "dns" in detail_lower or "name resolution" in detail_lower:
            friendly = "无法解析主机名。请检查 URL 是否正确。"
        elif "ssl" in detail_lower or "certificate" in detail_lower:
            friendly = "SSL 证书验证失败。请检查 URL 或证书配置。"
        elif "connection refused" in detail_lower:
            friendly = "连接被拒绝。服务可能未运行或端口未开放。"
        else:
            friendly = detail
        return TestConnectionResponse(
            name=server_name,
            status="error",
            error_message=friendly,
        )
    except Exception as e:
        logger.error(f"连接 MCP Server {server_name} 失败: {e}")
        return TestConnectionResponse(name=server_name, status="error", error_message=str(e))


@router.post("/store/{server_name}/test", response_model=TestConnectionResponse)
async def test_mcp_store_connection(
    server_name: str,
    current_user: UserInfo = Depends(get_current_user),
) -> TestConnectionResponse:
    """测试我的默认 MCP 仓库中的 server。"""
    service = get_mcp_config_service()
    server_config = service.get_server_config(current_user.user_id, server_name)

    if not server_config:
        raise HTTPException(
            status_code=404,
            detail="MCP Server not found",
        )

    return await _test_mcp_server_connection(
        server_name=server_name,
        server_config=server_config,
        current_user=current_user,
    )


@router.get("/status")
async def get_mcp_status(
    current_user: UserInfo = Depends(get_current_user),
) -> List[MCPConnectionStatus]:
    """获取所有 MCP Server 的连接状态"""
    mgr = get_mcp_manager()
    definitions = mgr.list_store_servers(current_user.user_id)

    statuses = []
    for definition in definitions:
        status = MCPConnectionStatus(
            name=definition.name,
            status="configured",
            tools_count=0,
            is_system_default=definition.is_system_default,
        )
        statuses.append(status)

    return statuses


# ===== 全局 MCP 仓库 API =====


@router.get("/store", response_model=MCPStoreListResponse)
async def list_mcp_store(
    current_user: UserInfo = Depends(get_current_user),
) -> MCPStoreListResponse:
    """返回全局 MCP 仓库中的所有 server 定义。"""
    mgr = get_mcp_manager()
    servers = mgr.list_store_servers(current_user.user_id)
    return MCPStoreListResponse(
        servers=[
            MCPStoreServerResponse(
                name=s.name,
                display_name=s.display_name,
                type=s.type,
                url=s.url,
                command=s.command,
                args=s.args or [],
                headers=s.headers or {},
                env=s.env or {},
                env_schema=s.env_schema or {},
                env_fields=[
                    {
                        "name": f.name,
                        "required": f.required,
                        "description": f.description,
                        "default_value": f.default_value,
                    }
                    for f in (s.env_fields or [])
                ],
                readme_excerpt=s.readme_excerpt,
                description=s.description,
                timeout_ms=s.timeout_ms,
                is_system_default=s.is_system_default,
                auto_attach_modes=s.auto_attach_modes or [],
                enabled_tools=s.enabled_tools or [],
            )
            for s in servers
        ],
        total=len(servers),
    )


@router.post("/store")
async def add_mcp_store_server(
    server_config: MCPServerConfig,
    current_user: UserInfo = Depends(get_current_user),
):
    """添加或更新全局 MCP 仓库中的 server 定义。"""
    mgr = get_mcp_manager()
    definition = MCPServerDefinition(
        name=server_config.name,
        display_name=server_config.name,
        type=server_config.type,
        url=server_config.url,
        headers=server_config.headers or {},
        command=server_config.command,
        args=server_config.args or [],
        description=server_config.description,
        timeout_ms=server_config.timeout_ms,
    )
    result = mgr.save_store_server(current_user.user_id, definition, force=True)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"success": True, "message": result.message}


@router.delete("/store/{server_name}")
async def delete_mcp_store_server(
    server_name: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """从全局 MCP 仓库删除 server 定义。"""
    mgr = get_mcp_manager()
    result = mgr.remove_store_server(server_name, current_user.user_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return {"success": True, "message": result.message}


class UpdateStoreEnvRequest(BaseModel):
    env: dict[str, str] = Field(default_factory=dict, description="环境变量键值对")


@router.put("/store/{server_name}/env")
async def update_mcp_store_env(
    server_name: str,
    request: UpdateStoreEnvRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新全局 MCP 仓库中 server 的环境变量。"""
    mgr = get_mcp_manager()
    result = mgr.set_store_server_env(current_user.user_id, server_name, request.env)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"success": True, "message": result.message}


# ===== 工作区 MCP 配置 API =====


@router.get("/workspaces/{workspace_id}", response_model=MCPWorkspaceListResponse)
async def list_workspace_mcp_servers(
    workspace_id: str,
    scope: str = "effective",
    current_user: UserInfo = Depends(get_current_user),
) -> MCPWorkspaceListResponse:
    """返回工作区的 MCP server 配置。

    Args:
        scope: "effective" 返回三层合并后的生效配置（默认）；
               "workspace" 返回仅工作区配置中的 server。
    """
    mgr = get_mcp_manager()
    workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id

    if scope == "workspace":
        config = mgr._load_workspace_config(workspace_path)
        servers = list(config.servers.values())
    else:
        servers = mgr.list_effective_servers(workspace_path)

    return MCPWorkspaceListResponse(
        servers=[
            MCPWorkspaceServerResponse(
                name=s.name,
                display_name=s.display_name,
                type=s.type,
                url=s.url,
                command=s.command,
                args=s.args or [],
                headers=s.headers or {},
                env=s.env or {},
                env_schema=s.env_schema or {},
                description=s.description,
                timeout_ms=s.timeout_ms,
                enabled=True,
                is_system_default=s.is_system_default,
                auto_attach_modes=s.auto_attach_modes or [],
                enabled_tools=s.enabled_tools or [],
            )
            for s in servers
        ],
        total=len(servers),
    )


@router.post("/workspaces/{workspace_id}/servers/{server_name}")
async def add_workspace_mcp_server(
    workspace_id: str,
    server_name: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """将全局 server 复制到工作区配置。"""
    mgr = get_mcp_manager()
    workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id
    definition = mgr.get_server_definition(server_name, current_user.user_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="MCP Server not found in global store")
    result = mgr.save_workspace_server(workspace_path, definition)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"success": True, "message": result.message}


@router.delete("/workspaces/{workspace_id}/servers/{server_name}")
async def remove_workspace_mcp_server(
    workspace_id: str,
    server_name: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """从工作区配置中删除 server。"""
    mgr = get_mcp_manager()
    workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id
    result = mgr.remove_workspace_server(server_name, workspace_path)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"success": True, "message": result.message}


@router.get(
    "/workspaces/{workspace_id}/servers/{server_name}/tools",
    response_model=MCPWorkspaceToolsResponse,
)
async def get_workspace_mcp_server_tools(
    workspace_id: str,
    server_name: str,
    current_user: UserInfo = Depends(get_current_user),
):
    """获取工作区 MCP server 的工具列表（含缓存和启用状态）。"""
    mgr = get_mcp_manager()
    workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id

    cached_tools = mgr.get_cached_server_tools(workspace_path, server_name)
    enabled_tools = mgr.get_workspace_server_enabled_tools(server_name, workspace_path)

    return MCPWorkspaceToolsResponse(
        server_name=server_name,
        tools=[
            MCPToolInfoResponse(name=t["name"], description=t.get("description"))
            for t in cached_tools
        ],
        enabled_tools=enabled_tools,
    )


@router.post(
    "/workspaces/{workspace_id}/servers/{server_name}/test",
    response_model=TestConnectionResponse,
)
async def test_workspace_mcp_server_connection(
    workspace_id: str,
    server_name: str,
    current_user: UserInfo = Depends(get_current_user),
) -> TestConnectionResponse:
    """测试工作区生效 MCP server，并缓存工具列表到工作区。"""
    mgr = get_mcp_manager()
    workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id
    server_config = None
    for definition in mgr.list_effective_servers(workspace_path):
        if definition.name == server_name:
            server_config = _definition_to_server_config(definition)
            break

    if server_config is None:
        raise HTTPException(
            status_code=404,
            detail="MCP Server not found",
        )

    return await _test_mcp_server_connection(
        server_name=server_name,
        server_config=server_config,
        workspace_id=workspace_id,
        current_user=current_user,
    )


@router.put("/workspaces/{workspace_id}/servers/{server_name}/tools")
async def update_workspace_mcp_server_enabled_tools(
    workspace_id: str,
    server_name: str,
    request: UpdateEnabledToolsRequest,
    current_user: UserInfo = Depends(get_current_user),
):
    """更新工作区 MCP server 的启用工具列表。"""
    mgr = get_mcp_manager()
    workspace_path = Path(WORKSPACE_DIR) / current_user.user_id / workspace_id
    result = mgr.set_workspace_server_enabled_tools(
        server_name, workspace_path, request.enabled_tools
    )
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return {"success": True, "message": result.message}
