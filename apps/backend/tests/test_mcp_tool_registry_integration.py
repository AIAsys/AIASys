"""MCP 工具接入 ToolRegistry 的集成测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry
from app.services.agent.runtime_backends.aiasys.tools.mcp_tool import MCPTool
from app.agents.tools.file_tools import WriteFile
from app.agents.tools.shell_tool import Shell


class _FakeMCPClient:
    def __init__(self):
        self.call_tool = AsyncMock()


def _make_mcp_tool(name: str, description: str = "") -> MCPTool:
    return MCPTool(
        server_name="test-server",
        tool_name=name,
        description=description,
        input_schema={"type": "object"},
        mcp_client=_FakeMCPClient(),
    )


class BuiltinToolStub:
    name = "ReadFile"
    description = "Read a file"
    parameters = {"type": "object", "properties": {}}
    is_mcp = False

    async def invoke(self, ctx: dict | None = None, **kwargs: Any) -> Any:
        return None


def test_registry_sorts_builtin_before_mcp():
    registry = ToolRegistry()
    registry.register(BuiltinToolStub())
    registry.register(_make_mcp_tool("remote_lookup"))
    registry.register(_make_mcp_tool("get_time"))

    schemas = registry.get_openai_schema()
    names = [s["function"]["name"] for s in schemas]

    assert names == ["ReadFile", "get_time", "remote_lookup"]


def test_registry_mcp_conflict_auto_rename():
    """MCP 工具与内置工具同名时自动加 mcp_ 前缀。"""
    registry = ToolRegistry()
    registry.register(BuiltinToolStub())
    mcp_tool = _make_mcp_tool("ReadFile")
    registry.register(mcp_tool)

    assert mcp_tool.name == "mcp_ReadFile"
    schemas = registry.get_openai_schema()
    names = [s["function"]["name"] for s in schemas]
    assert "ReadFile" in names
    assert "mcp_ReadFile" in names


def test_registry_mcp_tools_grouped_at_end():
    """即使先注册 MCP 工具，排序后 builtin 仍在前面。"""
    registry = ToolRegistry()
    registry.register(_make_mcp_tool("z_last"))
    registry.register(_make_mcp_tool("a_first_mcp"))
    registry.register(BuiltinToolStub())

    schemas = registry.get_openai_schema()
    names = [s["function"]["name"] for s in schemas]

    # builtin 在前，MCP 在后，各自按字母序
    assert names == ["ReadFile", "a_first_mcp", "z_last"]


def test_registry_get_tool_returns_mcp_tool():
    registry = ToolRegistry()
    mcp_tool = _make_mcp_tool("get_time")
    registry.register(mcp_tool)

    retrieved = registry.get_tool("get_time")
    assert retrieved is mcp_tool
    assert getattr(retrieved, "is_mcp", False) is True


def test_registry_mcp_schema_contains_parameters():
    registry = ToolRegistry()
    mcp_tool = MCPTool(
        server_name="s",
        tool_name="calc",
        description="Calculate something",
        input_schema={
            "type": "object",
            "properties": {"x": {"type": "number"}, "y": {"type": "number"}},
            "required": ["x", "y"],
        },
        mcp_client=_FakeMCPClient(),
    )
    registry.register(mcp_tool)

    schemas = registry.get_openai_schema()
    calc_schema = next(s for s in schemas if s["function"]["name"] == "calc")
    params = calc_schema["function"]["parameters"]
    assert params["type"] == "object"
    assert "x" in params["properties"]
    assert "y" in params["properties"]


def test_registry_keeps_core_runtime_named_tools_non_deferred():
    registry = ToolRegistry()
    registry.register(WriteFile())
    registry.register(Shell())
    registry.register(_make_mcp_tool("custom_remote_lookup"))

    non_deferred, deferred = registry.get_openai_schemas_split()
    non_deferred_names = {s["function"]["name"] for s in non_deferred}
    deferred_names = {s["function"]["name"] for s in deferred}

    assert "WriteFile" in non_deferred_names
    assert "Shell" in non_deferred_names
    assert "WriteFile" not in deferred_names
    assert "Shell" not in deferred_names
    assert "custom_remote_lookup" in deferred_names
