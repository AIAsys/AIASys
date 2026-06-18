"""测试 AIASys 原生 Subagent 管理工具（List/Update/Delete）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.core.tool_result import ToolResult
from app.services.agent.runtime_backends.aiasys.tools.delete_subagent_tool import (
    DeleteSubagentTool,
)
from app.services.agent.runtime_backends.aiasys.tools.list_subagents_tool import (
    ListSubagentsTool,
)
from app.services.agent.runtime_backends.aiasys.tools.update_subagent_tool import (
    UpdateSubagentTool,
)
from app.services.agent.subagent_catalog import (
    save_subagent,
    save_subagent_visibility_policy,
)

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


def _create_session_metadata(
    workspace: Path,
    user_id: str,
    session_id: str,
    enabled_expert_role_ids: list[str] | None,
) -> None:
    """在临时工作区下创建会话 metadata.json。"""
    session_dir = workspace / user_id / session_id
    session_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "session_id": session_id,
        "enabled_expert_role_ids": enabled_expert_role_ids,
    }
    (session_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False),
        encoding="utf-8",
    )


class TestListSubagentsTool:
    async def test_list_enabled_experts(self, temp_workspace):
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        # 先创建两个工作区专家
        save_subagent(
            "user1",
            "expert_a",
            {"name": "expert_a", "description": "专家A", "system_prompt": "A"},
            scope="workspace",
        )
        save_subagent(
            "user1",
            "expert_b",
            {"name": "expert_b", "description": "专家B", "system_prompt": "B"},
            scope="workspace",
        )

        result = await tool.invoke(ctx=ctx)
        assert isinstance(result, ToolResult)
        assert result.is_error is False
        # 系统内置角色现在默认即可派发，因此会列出它们；自定义专家未启用不应出现
        assert "expert_a" not in result.content
        assert "expert_b" not in result.content
        assert any(
            name in result.content for name in ("coder", "data_analyst", "researcher", "reviewer")
        )

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="expert_a",
            scope="workspace",
            workspace_id="user1",
            host_selectable=True,
            default_enabled=True,
        )
        save_subagent_visibility_policy(
            user_id="user1",
            role_id="expert_b",
            scope="workspace",
            workspace_id="user1",
            host_selectable=True,
            default_enabled=True,
        )

        result = await tool.invoke(ctx=ctx)
        assert "expert_a" in result.content
        assert "expert_b" in result.content

    async def test_list_respects_enabled_filter(self, temp_workspace):
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "expert_a",
            {"name": "expert_a", "description": "专家A", "system_prompt": "A"},
            scope="workspace",
        )
        save_subagent(
            "user1",
            "expert_b",
            {"name": "expert_b", "description": "专家B", "system_prompt": "B"},
            scope="workspace",
        )

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="expert_a",
            scope="workspace",
            workspace_id="user1",
            host_selectable=True,
            default_enabled=True,
        )

        result = await tool.invoke(ctx=ctx)
        assert "expert_a" in result.content
        assert "expert_b" not in result.content

    async def test_list_respects_session_enabled_expert_role_ids(
        self,
        temp_workspace,
    ):
        """会话 metadata 中显式禁用的专家不应出现在 list_subagents 结果中。"""
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "enabled_expert",
            {
                "name": "enabled_expert",
                "description": "已启用专家",
                "system_prompt": "enabled",
            },
            scope="workspace",
        )
        save_subagent(
            "user1",
            "disabled_expert",
            {
                "name": "disabled_expert",
                "description": "已禁用专家",
                "system_prompt": "disabled",
            },
            scope="workspace",
        )
        save_subagent_visibility_policy(
            user_id="user1",
            role_id="enabled_expert",
            scope="workspace",
            workspace_id="user1",
            host_selectable=True,
            default_enabled=True,
        )
        save_subagent_visibility_policy(
            user_id="user1",
            role_id="disabled_expert",
            scope="workspace",
            workspace_id="user1",
            host_selectable=True,
            default_enabled=True,
        )

        # 会话只启用 enabled_expert
        _create_session_metadata(
            workspace=temp_workspace,
            user_id="user1",
            session_id="sess1",
            enabled_expert_role_ids=["enabled_expert"],
        )

        result = await tool.invoke(ctx=ctx)
        assert "enabled_expert" in result.content
        assert "disabled_expert" not in result.content

    async def test_list_empty_enabled_expert_role_ids_disables_all(
        self,
        temp_workspace,
    ):
        """会话 metadata 中 enabled_expert_role_ids=[] 时应禁用全部专家。"""
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent_visibility_policy(
            user_id="user1",
            role_id="coder",
            scope="global",
            host_selectable=True,
            default_enabled=True,
        )

        _create_session_metadata(
            workspace=temp_workspace,
            user_id="user1",
            session_id="sess1",
            enabled_expert_role_ids=[],
        )

        result = await tool.invoke(ctx=ctx)
        assert "coder" not in result.content
        assert "当前没有可派发的协作专家" in result.content

    async def test_list_null_enabled_expert_role_ids_uses_default(
        self,
        temp_workspace,
    ):
        """会话 metadata 中 enabled_expert_role_ids=null 时应保持默认行为。"""
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        _create_session_metadata(
            workspace=temp_workspace,
            user_id="user1",
            session_id="sess1",
            enabled_expert_role_ids=None,
        )

        result = await tool.invoke(ctx=ctx)
        assert "coder" in result.content

    async def test_list_filter_by_scope(self, temp_workspace):
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "ws_expert",
            {"name": "ws_expert", "description": "工作区", "system_prompt": "w"},
            scope="workspace",
        )
        save_subagent(
            "user1",
            "global_expert",
            {"name": "global_expert", "description": "全局", "system_prompt": "g"},
            scope="global",
        )
        save_subagent_visibility_policy(
            user_id="user1",
            role_id="ws_expert",
            scope="workspace",
            workspace_id="user1",
            host_selectable=True,
            default_enabled=True,
        )
        save_subagent_visibility_policy(
            user_id="user1",
            role_id="global_expert",
            scope="global",
            host_selectable=True,
            default_enabled=True,
        )

        # 只过滤 workspace
        result = await tool.invoke(ctx=ctx, scope="workspace")
        assert "ws_expert" in result.content
        assert "global_expert" not in result.content

    async def test_list_rejects_unknown_scope(self, temp_workspace):
        tool = ListSubagentsTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        result = await tool.invoke(ctx=ctx, scope="project")
        assert result.is_error is True
        assert "不支持的 scope 'project'" in result.content


class TestUpdateSubagentTool:
    async def test_update_workspace_expert(self, temp_workspace):
        tool = UpdateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "my_expert",
            {"name": "my_expert", "description": "旧描述", "system_prompt": "旧提示"},
            scope="workspace",
        )

        result = await tool.invoke(
            ctx=ctx,
            name="my_expert",
            scope="workspace",
            description="新描述",
            system_prompt="新提示",
        )
        assert isinstance(result, ToolResult)
        assert result.is_error is False
        assert "已更新" in result.content

        # 验证已更新
        from app.services.agent.subagent_catalog import load_subagent

        loaded = load_subagent("user1", "my_expert")
        assert loaded["description"] == "新描述"
        assert loaded["system_prompt"] == "新提示"

    async def test_update_global_creates_workspace_override(self, temp_workspace):
        tool = UpdateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        # 更新一个 global 基线专家（coder 是系统预设）
        result = await tool.invoke(
            ctx=ctx,
            name="coder",
            scope="global",
            description="自定义 coder 描述",
        )
        assert isinstance(result, ToolResult)
        assert result.is_error is False
        assert "已更新" in result.content

        # 验证 workspace 级覆盖已创建
        from app.services.agent.subagent_catalog import load_subagent

        loaded = load_subagent("user1", "coder")
        assert loaded is not None
        assert loaded["description"] == "自定义 coder 描述"

    async def test_update_rejects_unavailable_tools(self, temp_workspace):
        tool = UpdateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "my_expert",
            {"name": "my_expert", "description": "旧描述", "system_prompt": "旧提示"},
            scope="workspace",
        )

        result = await tool.invoke(
            ctx=ctx,
            name="my_expert",
            scope="workspace",
            tools=[UNAVAILABLE_TOOL_PATH],
        )

        assert result.is_error is True
        assert "当前运行时不可用" in result.content

    async def test_update_rejects_unknown_scope(self, temp_workspace):
        tool = UpdateSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        result = await tool.invoke(ctx=ctx, name="my_expert", scope="project")

        assert result.is_error is True
        assert "不支持的 scope 'project'" in result.content


class TestDeleteSubagentTool:
    async def test_delete_workspace_expert(self, temp_workspace):
        tool = DeleteSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "to_delete",
            {"name": "to_delete", "description": "删除我", "system_prompt": "d"},
            scope="workspace",
        )

        result = await tool.invoke(ctx=ctx, name="to_delete", scope="workspace")
        assert isinstance(result, ToolResult)
        assert result.is_error is False
        assert "已删除" in result.content

        from app.services.agent.subagent_catalog import load_subagent

        assert load_subagent("user1", "to_delete") is None

    async def test_delete_global_disables_it(self, temp_workspace):
        tool = DeleteSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        save_subagent(
            "user1",
            "global_expert",
            {"name": "global_expert", "description": "全局", "system_prompt": "g"},
            scope="global",
        )

        result = await tool.invoke(ctx=ctx, name="global_expert", scope="global")
        assert isinstance(result, ToolResult)
        assert result.is_error is False

        from app.services.agent.subagent_catalog import load_subagent

        assert load_subagent("user1", "global_expert") is None

    async def test_delete_rejects_unknown_scope(self, temp_workspace):
        tool = DeleteSubagentTool()
        ctx = {"user_id": "user1", "session_id": "sess1"}

        result = await tool.invoke(ctx=ctx, name="my_expert", scope="project")

        assert result.is_error is True
        assert "不支持的 scope 'project'" in result.content
