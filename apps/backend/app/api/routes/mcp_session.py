"""
会话级 MCP API 路由（简化版）

每个任务独立配置 MCP，不再区分用户级和会话级
"""

import asyncio
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import get_current_user
from app.models.mcp import MCPServerConfig
from app.models.user import UserInfo
from app.services.llm import (
    MCPSessionService,
    get_mcp_session_service,
)

logger = logging.getLogger(__name__)

# 注意：为了避免和 sessions_router 的 /{user_id}/{session_id} 冲突，
# 我们使用 /mcp-session/{session_id} 路径
router = APIRouter(prefix="/mcp-session", tags=["mcp-session"])


# 请求/响应模型
class MCPServerRequest(BaseModel):
    """MCP 服务器配置请求"""

    name: str
    type: str = "streamable-http"
    url: Optional[str] = None
    command: Optional[str] = None
    args: Optional[List[str]] = None
    env: Optional[dict] = None
    headers: Optional[dict] = None
    enabled: bool = True
    description: Optional[str] = None


class MCPServerResponse(BaseModel):
    """MCP 服务器列表响应"""

    servers: List[dict]
    count: int


class ToggleEnabledRequest(BaseModel):
    """切换启用状态请求"""

    enabled: bool


class TestConnectionResponse(BaseModel):
    """测试连接响应"""

    status: str
    tools_count: int = 0
    message: Optional[str] = None


async def _test_session_server_connection(
    server: MCPServerConfig,
) -> TestConnectionResponse:
    """对会话级 MCP 配置执行真实连接测试。"""
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.stdio import StdioServerParameters, stdio_client
    from mcp.client.streamable_http import streamablehttp_client

    timeout_seconds = max(server.timeout_ms / 1000.0, 1.0)

    try:
        if server.type == "streamable-http":
            async with streamablehttp_client(
                server.url,
                headers=server.headers or None,
                timeout=timeout_seconds,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(
                        session.initialize(),
                        timeout=timeout_seconds,
                    )
                    tools = await asyncio.wait_for(
                        session.list_tools(),
                        timeout=timeout_seconds,
                    )
                    return TestConnectionResponse(
                        status="connected",
                        tools_count=len(tools.tools),
                        message="连接成功",
                    )

        if server.type == "sse":
            async with sse_client(
                server.url,
                headers=server.headers or None,
                timeout=timeout_seconds,
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(
                        session.initialize(),
                        timeout=timeout_seconds,
                    )
                    tools = await asyncio.wait_for(
                        session.list_tools(),
                        timeout=timeout_seconds,
                    )
                    return TestConnectionResponse(
                        status="connected",
                        tools_count=len(tools.tools),
                        message="连接成功",
                    )

        if server.type == "stdio":
            if not server.command:
                raise ValueError("STDIO 类型必须提供 command")

            server_params = StdioServerParameters(
                command=server.command,
                args=server.args,
                env=server.env,
            )

            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    await asyncio.wait_for(
                        session.initialize(),
                        timeout=timeout_seconds,
                    )
                    tools = await asyncio.wait_for(
                        session.list_tools(),
                        timeout=timeout_seconds,
                    )
                    return TestConnectionResponse(
                        status="connected",
                        tools_count=len(tools.tools),
                        message="连接成功",
                    )

        raise ValueError(f"不支持的 MCP 类型: {server.type}")
    except asyncio.TimeoutError:
        logger.warning("测试会话级 MCP 连接超时: server=%s", server.name)
        return TestConnectionResponse(
            status="error",
            tools_count=0,
            message="连接超时",
        )
    except Exception as exc:
        logger.error("测试会话级 MCP 连接失败: server=%s error=%s", server.name, exc)
        return TestConnectionResponse(
            status="error",
            tools_count=0,
            message=str(exc),
        )


def get_user_id_from_user(current_user: UserInfo = Depends(get_current_user)) -> str:
    """从认证用户获取用户 ID"""
    return current_user.user_id


@router.get("/{session_id}/servers", response_model=MCPServerResponse)
async def get_session_mcp_servers(
    session_id: str,
    user_id: str = Depends(get_user_id_from_user),
    service: MCPSessionService = Depends(get_mcp_session_service),
):
    """获取会话的 MCP 服务器列表

    包括系统默认和会话级自定义配置
    """
    servers = service.get_session_mcp_servers(user_id, session_id)
    return MCPServerResponse(
        servers=[s.model_dump() for s in servers],
        count=len(servers),
    )


@router.post("/{session_id}/servers")
async def add_session_mcp_server(
    session_id: str,
    request: MCPServerRequest,
    user_id: str = Depends(get_user_id_from_user),
    service: MCPSessionService = Depends(get_mcp_session_service),
):
    """为会话添加 MCP 服务器"""
    server = MCPServerConfig(
        name=request.name,
        type=request.type,
        url=request.url,
        command=request.command,
        args=request.args,
        env=request.env,
        headers=request.headers,
        enabled=request.enabled,
        description=request.description,
    )

    success = service.add_session_mcp_server(user_id, session_id, server)
    if not success:
        raise HTTPException(status_code=400, detail="添加失败，可能是名称重复或系统默认")

    return {"success": True, "message": "添加成功"}


@router.delete("/{session_id}/servers/{server_name}")
async def remove_session_mcp_server(
    session_id: str,
    server_name: str,
    user_id: str = Depends(get_user_id_from_user),
    service: MCPSessionService = Depends(get_mcp_session_service),
):
    """删除会话的 MCP 服务器"""
    success = service.remove_session_mcp_server(user_id, session_id, server_name)
    if not success:
        raise HTTPException(status_code=400, detail="删除失败，不能删除系统默认服务器")

    return {"success": True, "message": "删除成功"}


@router.patch("/{session_id}/servers/{server_name}/enabled")
async def toggle_server_enabled(
    session_id: str,
    server_name: str,
    request: ToggleEnabledRequest,
    user_id: str = Depends(get_user_id_from_user),
    service: MCPSessionService = Depends(get_mcp_session_service),
):
    """切换服务器启用状态"""
    success = service.update_server_enabled(user_id, session_id, server_name, request.enabled)
    if not success:
        raise HTTPException(status_code=400, detail="更新失败")

    return {"success": True, "message": "更新成功"}


@router.post("/{session_id}/servers/{server_name}/test", response_model=TestConnectionResponse)
async def test_mcp_connection(
    session_id: str,
    server_name: str,
    user_id: str = Depends(get_user_id_from_user),
    service: MCPSessionService = Depends(get_mcp_session_service),
):
    """测试会话级 MCP 服务器连接。"""
    # 获取服务器配置
    servers = service.get_session_mcp_servers(user_id, session_id)
    server = next((s for s in servers if s.name == server_name), None)

    if not server:
        raise HTTPException(status_code=404, detail="服务器不存在")

    return await _test_session_server_connection(server)


@router.get("/{session_id}/mcp/sdk-config")
async def get_sdk_config(
    session_id: str,
    user_id: str = Depends(get_user_id_from_user),
    service: MCPSessionService = Depends(get_mcp_session_service),
):
    """获取 SDK 可用的 MCP 配置格式"""
    config = service.get_sdk_config(user_id, session_id)
    return {"config": config}
