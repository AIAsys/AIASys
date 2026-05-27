"""MCP 客户端封装，桥接官方 mcp SDK 与 AIASys ToolRegistry。"""

from __future__ import annotations

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, Tool

logger = logging.getLogger(__name__)


def _summarize_base_exception(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        parts = [
            _summarize_base_exception(sub_exc)
            for sub_exc in exc.exceptions
            if not isinstance(sub_exc, GeneratorExit)
        ]
        return "; ".join(part for part in parts if part) or str(exc)
    return str(exc).strip() or type(exc).__name__


def _is_sdk_cancel_scope_error(exc: BaseException) -> bool:
    if isinstance(exc, asyncio.CancelledError):
        return "cancel scope" in str(exc).lower()
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_sdk_cancel_scope_error(sub_exc) for sub_exc in exc.exceptions)
    return False


def _import_streamablehttp_client() -> Any:
    """延迟导入 streamable-http client，避免启动时硬依赖。"""
    try:
        from mcp.client.streamable_http import streamablehttp_client

        return streamablehttp_client
    except ImportError as exc:
        logger.warning("streamable-http client 不可用: %s", exc)
        return None


class MCPClient:
    """单个 MCP 服务器的客户端连接。

    使用 AsyncExitStack 管理 stdio_client / ClientSession 的嵌套生命周期，
    支持在 session 存活期间保持连接打开。
    """

    def __init__(self, server_name: str, server_config: dict[str, Any]) -> None:
        self._server_name = server_name
        self._server_config = dict(server_config)
        self._session: ClientSession | None = None
        self._exit_stack = AsyncExitStack()

    @property
    def server_name(self) -> str:
        return self._server_name

    async def connect(self) -> None:
        """建立与 MCP 服务器的连接并初始化 session。"""
        transport = self._server_config.get("transport", "stdio")
        command = self._server_config.get("command")

        try:
            if command is not None or transport == "stdio":
                await self._connect_stdio()
            else:
                await self._connect_http()

            if self._session is None:
                raise RuntimeError(f"MCP server '{self._server_name}' 连接失败")

            await self._session.initialize()
            logger.info("MCP server '%s' 已连接", self._server_name)
        except BaseExceptionGroup as exc:
            await self.close()
            raise RuntimeError(
                f"MCP server '{self._server_name}' 连接失败: " f"{_summarize_base_exception(exc)}"
            ) from exc
        except asyncio.CancelledError as exc:
            await self.close()
            if _is_sdk_cancel_scope_error(exc):
                raise RuntimeError(
                    f"MCP server '{self._server_name}' 连接失败: "
                    f"{_summarize_base_exception(exc)}"
                ) from exc
            raise
        except Exception:
            await self.close()
            raise

    async def _connect_stdio(self) -> None:
        command = self._server_config.get("command")
        if not command:
            raise ValueError(f"MCP server '{self._server_name}' stdio 模式缺少 command")

        params = StdioServerParameters(
            command=command,
            args=list(self._server_config.get("args") or []),
            env=self._server_config.get("env"),
        )

        timeout = self._server_config.get("timeout")
        timeout_ms = self._server_config.get("timeout_ms")
        timeout_seconds = 30.0
        if timeout is not None:
            timeout_seconds = float(timeout)
        elif timeout_ms is not None:
            timeout_seconds = float(timeout_ms) / 1000.0

        read_stream, write_stream = await asyncio.wait_for(
            self._exit_stack.enter_async_context(stdio_client(params)),
            timeout=timeout_seconds,
        )
        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

    async def _connect_http(self) -> None:
        url = self._server_config.get("url")
        if not url:
            raise ValueError(f"MCP server '{self._server_name}' HTTP 模式缺少 url")

        server_type = (
            self._server_config.get("type")
            or self._server_config.get("transport")
            or "streamable-http"
        )

        timeout = self._server_config.get("timeout")
        timeout_ms = self._server_config.get("timeout_ms")
        timeout_seconds = None
        if timeout is not None:
            timeout_seconds = float(timeout)
        elif timeout_ms is not None:
            timeout_seconds = float(timeout_ms) / 1000.0

        headers = self._server_config.get("headers")

        if server_type in ("streamable-http", "streamable_http"):
            streamablehttp_client = _import_streamablehttp_client()
            if streamablehttp_client is None:
                raise RuntimeError(
                    f"MCP server '{self._server_name}' 需要 streamable-http 支持，但相关依赖不可用"
                )
            transport_streams = await self._exit_stack.enter_async_context(
                streamablehttp_client(url, headers=headers, timeout=timeout_seconds)
            )
            read_stream, write_stream = transport_streams[:2]
        elif server_type == "sse":
            from mcp.client.sse import sse_client

            transport_streams = await self._exit_stack.enter_async_context(
                sse_client(url, headers=headers, timeout=timeout_seconds)
            )
            read_stream, write_stream = transport_streams[:2]
        else:
            raise ValueError(
                f"MCP server '{self._server_name}' 不支持的 HTTP transport 类型: {server_type}"
            )

        self._session = await self._exit_stack.enter_async_context(
            ClientSession(read_stream, write_stream)
        )

    async def list_tools(self) -> list[Tool]:
        """获取 MCP 服务器提供的工具列表。"""
        if self._session is None:
            raise RuntimeError("MCP client 未连接，请先调用 connect()")
        result = await self._session.list_tools()
        return list(result.tools or [])

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> CallToolResult:
        """调用指定 MCP 工具。"""
        if self._session is None:
            raise RuntimeError("MCP client 未连接，请先调用 connect()")
        return await asyncio.wait_for(
            self._session.call_tool(name, arguments or {}),
            timeout=timeout if timeout is not None else 60.0,
        )

    async def close(self) -> None:
        """关闭连接，清理资源。"""
        try:
            await self._exit_stack.aclose()
        except BaseExceptionGroup as exc:
            logger.warning(
                "MCP server '%s' 关闭连接时出错: %s",
                self._server_name,
                _summarize_base_exception(exc),
            )
        except asyncio.CancelledError as exc:
            if not _is_sdk_cancel_scope_error(exc):
                raise
            logger.warning(
                "MCP server '%s' 关闭连接时出错: %s",
                self._server_name,
                _summarize_base_exception(exc),
            )
        except Exception as exc:
            logger.warning("MCP server '%s' 关闭连接时出错: %s", self._server_name, exc)
        finally:
            self._session = None
            self._exit_stack = AsyncExitStack()
