"""MCP 服务器远程工具的本地代理。"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.aiasys.mcp_client import MCPClient

logger = logging.getLogger(__name__)


class MCPTool(AiasysTool):
    """包装 MCP 服务器远程工具，使其可被 AIASys ToolRegistry 调度。"""

    # 占位 ClassVar，实际值在实例化时通过实例属性覆盖
    name: ClassVar[str] = ""
    description: ClassVar[str] = ""
    parameters: ClassVar[dict[str, Any]] = {}
    is_mcp: ClassVar[bool] = True

    def __init__(
        self,
        *,
        server_name: str,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        mcp_client: MCPClient,
    ) -> None:
        self._server_name = server_name
        self._tool_name = tool_name
        self._mcp_client = mcp_client
        # 实例属性覆盖 ClassVar，供 ToolRegistry 读取
        self.name = tool_name
        self.description = description or f"MCP tool '{tool_name}' from server '{server_name}'"
        self.parameters = (
            dict(input_schema) if input_schema else {"type": "object", "properties": {}}
        )

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        try:
            result = await self._mcp_client.call_tool(self._tool_name, kwargs)
        except Exception as exc:
            logger.warning(
                "MCP tool '%s' (server='%s') 调用失败: %s",
                self._tool_name,
                self._server_name,
                exc,
            )
            return ToolResult(
                content=f"MCP 工具调用失败: {exc}",
                is_error=True,
            )

        # 将 MCP CallToolResult 转换为 AIASys ToolResult
        content_parts: list[str] = []
        for item in result.content or []:
            if hasattr(item, "text"):
                content_parts.append(str(item.text))
            elif hasattr(item, "data"):
                content_parts.append(str(item.data))
            elif hasattr(item, "uri"):
                content_parts.append(str(item.uri))
            else:
                content_parts.append(str(item))

        content = "\n".join(content_parts) if content_parts else ""
        return ToolResult(
            content=content,
            is_error=bool(result.isError),
        )
