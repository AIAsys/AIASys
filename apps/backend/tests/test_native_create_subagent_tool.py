"""测试 AIASys 原生 CreateSubagentTool。"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.aiasys.tools.create_subagent_tool import (
    CreateSubagentTool,
)
from app.services.runtime_tooling import READ_MEDIA_TOOL_PATH

UNAVAILABLE_TOOL_PATH = "app.unavailable_tools.file:ReadFile"


@pytest.fixture
def temp_workspace(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        from app.services.agent import subagent_catalog

        original = subagent_catalog.WORKSPACE_DIR
        tmp_path = Path(tmpdir)
        monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)
        yield tmp_path
        monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", original)


class TestCreateSubagentTool:
    async def test_create_persistent_subagent(self, temp_workspace):
        tool = CreateSubagentTool()
        host_config = {"subagents": {}}
        ctx = {
            "user_id": "user1",
            "session_id": "sess1",
            "agent_config": host_config,
            "allowed_create_subagent_scopes": ["workspace"],
        }

        result = await tool.invoke(
            ctx=ctx,
            name="custom_coder",
            description="自定义代码专家",
            system_prompt="你是一个代码专家...",
            tools=["app.agents.tools.read_media_tool:ReadMediaFile"],
            model="kimi-test",
            scope="workspace",
        )

        assert isinstance(result, ToolResult)
        assert result.is_error is False
        assert "custom_coder" in result.content
        assert "工作区级" in result.content

        # 验证已注入 Host manifest
        assert "custom_coder" in host_config["subagents"]
        assert host_config["subagents"]["custom_coder"]["description"] == "自定义代码专家"
        assert host_config["subagents"]["custom_coder"]["agent_manifest"]["tools"] == [
            READ_MEDIA_TOOL_PATH
        ]

    async def test_reject_unknown_scope(self, temp_workspace):
        tool = CreateSubagentTool()
        host_config = {"subagents": {}}
        ctx = {
            "user_id": "user1",
            "session_id": "sess1",
            "agent_config": host_config,
        }

        result = await tool.invoke(
            ctx=ctx,
            name="temp_analyst",
            description="临时分析师",
            system_prompt="你是一个分析师...",
            scope="project",
        )

        assert result.is_error is True
        assert "不支持的 scope 'project'" in result.content
        assert "temp_analyst" not in host_config["subagents"]

    async def test_reject_invalid_name(self, temp_workspace):
        tool = CreateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1", "agent_config": {}}

        result = await tool.invoke(
            ctx=ctx,
            name="2invalid",
            description="desc",
            system_prompt="prompt",
        )
        assert result.is_error is True
        assert "格式无效" in result.content

    async def test_reject_system_name_conflict(self, temp_workspace):
        tool = CreateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1", "agent_config": {}}

        result = await tool.invoke(
            ctx=ctx,
            name="coder",
            description="desc",
            system_prompt="prompt",
        )
        assert result.is_error is True
        assert "与系统预设角色冲突" in result.content

    async def test_reject_missing_fields(self, temp_workspace):
        tool = CreateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1", "agent_config": {}}

        result = await tool.invoke(ctx=ctx, name="test")
        assert result.is_error is True
        assert "缺少 description" in result.content

    async def test_optional_tools_and_model(self, temp_workspace):
        tool = CreateSubagentTool()
        host_config = {"subagents": {}}
        ctx = {
            "user_id": "user1",
            "session_id": "sess1",
            "agent_config": host_config,
        }

        result = await tool.invoke(
            ctx=ctx,
            name="minimal_agent",
            description="最小配置",
            system_prompt="你是一个最小代理...",
        )

        assert result.is_error is False
        assert "minimal_agent" in host_config["subagents"]
        manifest = host_config["subagents"]["minimal_agent"]["agent_manifest"]
        assert "tools" not in manifest or manifest.get("tools") is None
        assert "model" not in manifest or manifest.get("model") is None

    async def test_rejects_unavailable_tools(self, temp_workspace):
        tool = CreateSubagentTool()
        ctx = {
            "user_id": "user1",
            "session_id": "sess1",
            "agent_config": {"subagents": {}},
        }

        result = await tool.invoke(
            ctx=ctx,
            name="bad_tools_agent",
            description="非法工具测试",
            system_prompt="你是一个测试专家...",
            tools=[UNAVAILABLE_TOOL_PATH],
        )

        assert result.is_error is True
        assert "当前运行时不可用" in result.content

    async def test_rejects_orchestration_tools(self, temp_workspace):
        tool = CreateSubagentTool()
        ctx = {
            "user_id": "user1",
            "session_id": "sess1",
            "agent_config": {"subagents": {}},
        }

        result = await tool.invoke(
            ctx=ctx,
            name="bad_orchestrator",
            description="非法调度工具测试",
            system_prompt="你是一个测试专家...",
            tools=[
                "app.services.agent.runtime_backends.aiasys.tools.task_tool:TaskTool"
            ],
        )

        assert result.is_error is True
        assert "协作节点调度或创建工具" in result.content
