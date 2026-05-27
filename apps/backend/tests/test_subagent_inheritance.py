"""测试子 Agent 继承模型（工具继承、fork_turns、workspace 共享、禁止嵌套）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession
from app.services.agent.runtime_backends.aiasys.tool_registry import ToolRegistry
from app.services.agent.runtime_backends.aiasys.tools.task_tool import (
    AgentTool,
    TaskTool,
    _find_subagent_manifest,
)
from app.services.agent.runtime_backends.base import AgentRuntimeEvent, RuntimeSessionCreateSpec
from app.services.agent.models.llm_config import AiasysLlmConfig, LoopControl


class FakeLlmClient:
    async def chat_stream(self, messages, tools, temperature, max_tokens, request_options=None):
        del request_options
        yield MagicMock(
            delta=MagicMock(content="hello", reasoning_content="", tool_calls=[]),
            finish_reason="stop",
            usage=None,
        )


def _make_spec(**kwargs) -> RuntimeSessionCreateSpec:
    defaults = {
        "work_dir": Path(tempfile.mkdtemp(prefix="aiasys_test_")),
        "session_id": "test_session",
        "config": AiasysLlmConfig(
            default_model="gpt-4",
            providers={},
            models={},
            loop_control=LoopControl(max_steps_per_turn=10),
            fallback_order=[],
        ),
        "agent_file": Path("/tmp/fake.toml"),
        "skills_dir": None,
        "mcp_configs": None,
        "yolo": True,
    }
    defaults.update(kwargs)
    return RuntimeSessionCreateSpec(**defaults)


class TestForkTurns:
    """测试 fork_turns 对话历史继承。"""

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_fork_turns_none_inherits_all(self, mock_load_config):
        """fork_turns=None 时继承所有 Host 消息（除去 system）。"""
        mock_load_config.return_value = {}
        host_messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
        ]
        spec = _make_spec(is_subagent=True, fork_turns=None, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        roles = [m["role"] for m in session.messages]
        # 第一个是 system prompt（空），后面是继承的 user/assistant 消息
        assert "user" in roles
        assert "system" not in roles[1:]
        # 所有 user/assistant 消息都被继承
        user_count = sum(1 for m in session.messages if m.get("role") == "user")
        assert user_count == 2

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_fork_turns_zero_inherits_none(self, mock_load_config):
        """fork_turns=0 时不继承任何 Host 消息。"""
        mock_load_config.return_value = {}
        host_messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
        ]
        spec = _make_spec(is_subagent=True, fork_turns=0, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        roles = [m["role"] for m in session.messages]
        assert "user" not in roles
        assert "assistant" not in roles

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_fork_turns_n_inherits_last_n(self, mock_load_config):
        """fork_turns=N 时继承最后 N 轮 user/assistant 对话。"""
        mock_load_config.return_value = {}
        host_messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "reply3"},
        ]
        spec = _make_spec(is_subagent=True, fork_turns=2, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        contents = [m.get("content", "") for m in session.messages]
        # 应该只继承 msg2/reply2 和 msg3/reply3（最后 2 轮）
        assert "msg1" not in contents
        assert "reply1" not in contents
        assert "msg2" in contents
        assert "msg3" in contents

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_fork_turns_ignores_system_prompt(self, mock_load_config):
        """fork_messages 中的 system prompt 不会被继承到子 Agent。"""
        mock_load_config.return_value = {}
        host_messages = [
            {"role": "system", "content": "host_system"},
            {"role": "user", "content": "msg1"},
        ]
        spec = _make_spec(is_subagent=True, fork_turns=None, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        for m in session.messages:
            if m.get("role") == "system":
                assert m.get("content") != "host_system"

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_non_subagent_ignores_fork_messages(self, mock_load_config):
        """非子 Agent（Host session）不继承 fork_messages。"""
        mock_load_config.return_value = {}
        host_messages = [
            {"role": "user", "content": "msg1"},
        ]
        spec = _make_spec(is_subagent=False, fork_turns=None, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        contents = [m.get("content", "") for m in session.messages]
        assert "msg1" not in contents

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_fork_turns_exceeds_message_count(self, mock_load_config):
        """fork_turns 超过可用轮数时继承全部。"""
        mock_load_config.return_value = {}
        host_messages = [
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
        ]
        spec = _make_spec(is_subagent=True, fork_turns=10, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        contents = [m.get("content", "") for m in session.messages]
        assert "msg1" in contents
        assert "reply1" in contents

    @patch.object(AiasysRuntimeSession, "_load_or_build_system_prompt")
    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_fork_turns_drops_incomplete_tool_call_tail(self, mock_load_config, mock_load_prompt):
        """末尾未闭合的 assistant tool_calls 不应被继承给子 Agent。"""
        mock_load_config.return_value = {}
        mock_load_prompt.return_value = ""
        host_messages = [
            {"role": "user", "content": "msg1"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "tool-1",
                        "type": "function",
                        "function": {"name": "Task", "arguments": "{\"subagent_name\":\"worker\"}"},
                    }
                ],
            },
        ]
        spec = _make_spec(is_subagent=True, fork_turns=None, fork_messages=host_messages)
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        assert len(session.messages) == 1
        assert session.messages[0]["role"] == "user"
        assert session.messages[0]["content"] == "msg1"


class TestToolContextPropagation:
    """测试 _tool_context() 正确传递 messages 和 parent_registry。"""

    @patch.object(AiasysRuntimeSession, "_load_or_build_system_prompt")
    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_tool_context_includes_messages(self, mock_load_config, mock_load_prompt):
        """_tool_context() 应该包含当前 messages 列表。"""
        mock_load_config.return_value = {}
        mock_load_prompt.return_value = ""
        spec = _make_spec()
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)
        session.messages.append({"role": "user", "content": "hello"})

        ctx = session._tool_context()
        assert "messages" in ctx
        assert ctx["messages"] == session.messages
        assert ctx["messages"][0]["content"] == "hello"

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    def test_tool_context_includes_parent_registry(self, mock_load_config):
        """_tool_context() 应该包含当前 tool_registry 作为 parent_registry。"""
        mock_load_config.return_value = {}
        spec = _make_spec()
        registry = ToolRegistry()
        session = AiasysRuntimeSession(spec, FakeLlmClient(), registry)

        ctx = session._tool_context()
        assert "parent_registry" in ctx
        assert ctx["parent_registry"] is registry


def test_find_subagent_manifest_supports_materialized_toml(tmp_path: Path) -> None:
    toml_path = tmp_path / "worker.toml"
    toml_path.write_text(
        "\n".join(
            [
                'version = 1',
                '',
                '[agent]',
                'name = "worker"',
                'system_prompt = "你是执行专家"',
                'tools = []',
            ]
        ),
        encoding="utf-8",
    )

    manifest = _find_subagent_manifest(
        {
            "subagents": {
                "worker": {
                    "description": "执行专家",
                    "path": str(toml_path),
                }
            }
        },
        "worker",
    )

    assert manifest is not None
    assert manifest["name"] == "worker"
    assert manifest["system_prompt"] == "你是执行专家"


class TestTaskToolRuntimeEnablement:
    """测试 TaskTool 兜底运行时查找遵守协作专家启用策略。"""

    @pytest.fixture
    def temp_workspace(self, monkeypatch):
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.services.agent import subagent_catalog

            tmp_path = Path(tmpdir)
            monkeypatch.setattr(subagent_catalog, "WORKSPACE_DIR", tmp_path)
            yield tmp_path

    @pytest.mark.asyncio
    async def test_fallback_rejects_persisted_expert_when_not_enabled(
        self,
        temp_workspace,
    ):
        from app.services.agent.subagent_catalog import save_subagent

        save_subagent(
            user_id="u1",
            name="persisted_worker",
            manifest={
                "name": "persisted_worker",
                "description": "已保存但未启用",
                "system_prompt": "worker",
            },
            scope="workspace",
            workspace_id="u1",
        )

        results = []
        async for item in TaskTool().invoke_stream(
            {
                "user_id": "u1",
                "session_id": "s1",
                "workspace": temp_workspace,
                "session_root": temp_workspace,
                "agent_config": {"subagents": {}},
                "llm_config": MagicMock(),
                "messages": [],
                "parent_registry": ToolRegistry(),
            },
            subagent_name="persisted_worker",
            prompt="run",
        ):
            results.append(item)

        assert results
        assert results[-1].is_error is True
        assert "未启用到我的默认或当前工作区" in results[-1].content

    @pytest.mark.asyncio
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._materialize_subagent_toml")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend")
    async def test_fallback_allows_persisted_expert_after_workspace_enablement(
        self,
        mock_backend_cls,
        mock_materialize,
        mock_storage_cls,
        temp_workspace,
    ):
        from app.services.agent.subagent_catalog import (
            save_subagent,
            save_subagent_visibility_policy,
        )

        save_subagent(
            user_id="u1",
            name="persisted_worker",
            manifest={
                "name": "persisted_worker",
                "description": "已启用专家",
                "system_prompt": "worker",
            },
            scope="workspace",
            workspace_id="u1",
        )
        save_subagent_visibility_policy(
            user_id="u1",
            role_id="persisted_worker",
            scope="workspace",
            workspace_id="u1",
            host_selectable=True,
            default_enabled=True,
        )

        mock_materialize.return_value = Path("/tmp/fake.toml")
        mock_storage = MagicMock()
        mock_storage.append_context_message = AsyncMock()
        mock_storage.append_wire_agent_runtime_event = AsyncMock()
        mock_storage.update_status = Mock()
        mock_storage_cls.return_value = mock_storage
        mock_storage.subagent_dir = Path("/fake")
        mock_session = AsyncMock()
        mock_session.prompt = MagicMock(return_value=async_gen([]))
        mock_backend = MagicMock()
        mock_backend.create_session = AsyncMock(return_value=mock_session)
        mock_backend_cls.return_value = mock_backend

        results = []
        async for item in TaskTool().invoke_stream(
            {
                "user_id": "u1",
                "session_id": "s1",
                "workspace": temp_workspace,
                "session_root": temp_workspace,
                "agent_config": {"subagents": {}},
                "llm_config": MagicMock(),
                "messages": [],
                "parent_registry": ToolRegistry(),
            },
            subagent_name="persisted_worker",
            prompt="run",
        ):
            results.append(item)

        assert results
        assert results[-1].is_error is False
        assert mock_backend.create_session.called


class TestSubagentWorkspaceSharing:
    """测试子 Agent 共享 Host workspace。"""

    @pytest.mark.asyncio
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._materialize_subagent_toml")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._find_subagent_manifest")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend")
    async def test_subagent_uses_host_session_root(
        self, mock_backend_cls, mock_find, mock_materialize, mock_storage_cls
    ):
        """子 Agent 的 work_dir 应该是 Host 的 session_root，而不是独立的子目录。"""
        mock_find.return_value = {
            "name": "coder",
            "system_prompt": "You are a coder",
        }
        mock_materialize.return_value = Path("/tmp/fake.toml")

        mock_storage = MagicMock()
        mock_storage.append_context_message = AsyncMock()
        mock_storage.append_wire_agent_runtime_event = AsyncMock()
        mock_storage.update_status = Mock()
        mock_storage_cls.return_value = mock_storage
        mock_storage.subagent_dir = Path("/fake/subagent_dir")

        mock_session = AsyncMock()
        mock_session.prompt = MagicMock(return_value=async_gen([]))
        mock_backend = MagicMock()
        mock_backend.create_session = AsyncMock(return_value=mock_session)
        mock_backend_cls.return_value = mock_backend

        tool = AgentTool()
        host_session_root = Path("/host/workspace")
        ctx = {
            "user_id": "u1",
            "session_id": "s1",
            "workspace": host_session_root,
            "session_root": host_session_root,
            "agent_config": {
                "subagents": {
                    "coder": {
                        "description": "coder agent",
                        "agent_manifest": {"name": "coder", "system_prompt": "You are a coder"},
                    }
                }
            },
            "llm_config": MagicMock(),
            "messages": [],
            "parent_registry": ToolRegistry(),
        }

        results = []
        async for item in tool.invoke_stream(ctx, subagent_name="coder", prompt="write code"):
            results.append(item)

        # 验证 create_session 被调用时 work_dir 是 Host 的 session_root
        call_args = mock_backend.create_session.call_args
        spec = call_args.kwargs.get("spec") or call_args[0][0]
        # work_dir 应该是 WorkspacePath(session_root)
        assert str(spec.work_dir) == str(host_session_root)


class TestSubagentNestingProhibition:
    """测试子 Agent 禁止再创建子 Agent。"""

    @pytest.mark.asyncio
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._materialize_subagent_toml")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._find_subagent_manifest")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend")
    async def test_subagent_spec_has_is_subagent_true(
        self, mock_backend_cls, mock_find, mock_materialize, mock_storage_cls
    ):
        """TaskTool 创建子 Agent 时，spec.is_subagent 必须为 True。"""
        mock_find.return_value = {"name": "coder"}
        mock_materialize.return_value = Path("/tmp/fake.toml")

        mock_storage = MagicMock()
        mock_storage.append_context_message = AsyncMock()
        mock_storage.append_wire_agent_runtime_event = AsyncMock()
        mock_storage.update_status = Mock()
        mock_storage_cls.return_value = mock_storage
        mock_storage.subagent_dir = Path("/fake")

        mock_session = AsyncMock()
        mock_session.prompt = MagicMock(return_value=async_gen([]))
        mock_backend = MagicMock()
        mock_backend.create_session = AsyncMock(return_value=mock_session)
        mock_backend_cls.return_value = mock_backend

        tool = AgentTool()
        ctx = {
            "user_id": "u1",
            "session_id": "s1",
            "workspace": Path("/host"),
            "session_root": Path("/host"),
            "agent_config": {
                "subagents": {
                    "coder": {
                        "description": "",
                        "agent_manifest": {"name": "coder"},
                    }
                }
            },
            "llm_config": MagicMock(),
            "messages": [],
            "parent_registry": ToolRegistry(),
        }

        async for _ in tool.invoke_stream(ctx, subagent_name="coder", prompt="test"):
            pass

        spec = mock_backend.create_session.call_args.kwargs.get("spec") or mock_backend.create_session.call_args[0][0]
        assert spec.is_subagent is True

    @pytest.mark.asyncio
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._materialize_subagent_toml")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._find_subagent_manifest")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend")
    async def test_task_tool_carries_agent_path_and_nested_depth(
        self, mock_backend_cls, mock_find, mock_materialize, mock_storage_cls
    ):
        """manifest 中的 agent_max_depth 不再放开协作节点递归派发。"""
        mock_find.return_value = {"name": "coder", "agent_max_depth": 2}
        mock_materialize.return_value = Path("/tmp/fake.toml")

        mock_storage = MagicMock()
        mock_storage.append_context_message = AsyncMock()
        mock_storage.append_wire_agent_runtime_event = AsyncMock()
        mock_storage.update_status = Mock()
        mock_storage_cls.return_value = mock_storage
        mock_storage.subagent_dir = Path("/fake")

        mock_session = AsyncMock()
        mock_session.prompt = MagicMock(return_value=async_gen([]))
        mock_backend = MagicMock()
        mock_backend.create_session = AsyncMock(return_value=mock_session)
        mock_backend_cls.return_value = mock_backend

        tool = AgentTool()
        ctx = {
            "user_id": "u1",
            "session_id": "s1",
            "host_session_id": "host-s1",
            "workspace": Path("/host"),
            "session_root": Path("/host"),
            "agent_path": "/root",
            "agent_config": {
                "subagents": {
                    "coder": {
                        "description": "",
                        "agent_manifest": {"name": "coder", "agent_max_depth": 2},
                    }
                }
            },
            "llm_config": MagicMock(),
            "messages": [],
            "parent_registry": ToolRegistry(),
        }

        async for _ in tool.invoke_stream(ctx, subagent_name="coder", prompt="test"):
            pass

        spec = mock_backend.create_session.call_args.kwargs.get("spec") or mock_backend.create_session.call_args[0][0]
        assert spec.host_session_id == "host-s1"
        assert spec.agent_path.startswith("/root/coder_")
        assert spec.agent_max_depth == 1
        assert spec.allow_subagent_spawn is False
        assert mock_storage.create_workspace.call_args.kwargs["agent_path"].startswith("/root/coder_")
        assert mock_storage.create_workspace.call_args.kwargs["depth"] == 1

    @pytest.mark.asyncio
    async def test_task_tool_rejects_depth_limit_before_creating_storage(self):
        """超过 agent_max_depth 时不创建子 Agent 存储。"""
        tool = AgentTool()
        ctx = {
            "user_id": "u1",
            "session_id": "s1",
            "workspace": Path("/host"),
            "session_root": Path("/host"),
            "agent_path": "/root/worker_1",
            "agent_max_depth": 1,
            "agent_config": {
                "subagents": {
                    "reviewer": {
                        "description": "",
                        "agent_manifest": {"name": "reviewer"},
                    }
                }
            },
            "llm_config": MagicMock(),
            "messages": [],
            "parent_registry": ToolRegistry(),
        }

        results = []
        with patch(
            "app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage"
        ) as mock_storage_cls:
            async for item in tool.invoke_stream(
                ctx,
                subagent_name="reviewer",
                prompt="review",
            ):
                results.append(item)

        assert results
        assert results[-1].is_error is True
        assert "嵌套深度" in results[-1].content
        mock_storage_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_tool_rejects_session_max_threads_before_creating_storage(self):
        """会话协作策略的 max_threads 会阻止继续派发。"""
        tool = AgentTool()
        ctx = {
            "user_id": "u1",
            "session_id": "s1",
            "host_session_id": "host-s1",
            "workspace": Path("/host"),
            "session_root": Path("/host"),
            "agent_path": "/root",
            "collaboration_policy": {
                "max_depth": 1,
                "max_threads": 1,
                "allow_nested_spawn": False,
            },
            "agent_config": {
                "subagents": {
                    "reviewer": {
                        "description": "",
                        "agent_manifest": {"name": "reviewer"},
                    }
                }
            },
            "llm_config": MagicMock(),
            "messages": [],
            "parent_registry": ToolRegistry(),
        }

        results = []
        with (
            patch(
                "app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage"
            ) as mock_storage_cls,
            patch(
                "app.services.agent.runtime_backends.aiasys.tools.task_tool.get_subagent_registry"
            ) as mock_get_registry,
        ):
            mock_registry = MagicMock()
            mock_registry.count_active_for_host.return_value = 1
            mock_registry.try_register = AsyncMock(return_value=False)
            mock_get_registry.return_value = mock_registry
            async for item in tool.invoke_stream(
                ctx,
                subagent_name="reviewer",
                prompt="review",
            ):
                results.append(item)

        assert results
        assert results[-1].is_error is True
        assert "并发数已达到上限 1" in results[-1].content
        mock_registry.count_active_for_host.assert_called_once_with("host-s1")
        mock_storage_cls.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.SubAgentStorage")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._materialize_subagent_toml")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool._find_subagent_manifest")
    @patch("app.services.agent.runtime_backends.aiasys.tools.task_tool.AiasysRuntimeBackend")
    async def test_task_tool_persists_dispatch_and_final_reply_into_context(
        self, mock_backend_cls, mock_find, mock_materialize, mock_storage_cls
    ):
        """TaskTool 应把主控派发 prompt 和子 Agent 最终回复写入 context.jsonl。"""
        mock_find.return_value = {"name": "worker"}
        mock_materialize.return_value = Path("/tmp/fake.toml")

        mock_storage = MagicMock()
        mock_storage.append_context_message = AsyncMock()
        mock_storage.append_wire_agent_runtime_event = AsyncMock()
        mock_storage.update_status = Mock()
        mock_storage_cls.return_value = mock_storage
        mock_storage.subagent_dir = Path("/fake")

        mock_session = AsyncMock()
        mock_session.prompt = MagicMock(
            return_value=async_gen(
                [
                    AgentRuntimeEvent(
                        kind="content",
                        content_type="text",
                        text="一致性复测完成",
                    )
                ]
            )
        )
        mock_backend = MagicMock()
        mock_backend.create_session = AsyncMock(return_value=mock_session)
        mock_backend_cls.return_value = mock_backend

        tool = AgentTool()
        ctx = {
            "user_id": "u1",
            "session_id": "s1",
            "workspace": Path("/host"),
            "session_root": Path("/host"),
            "_tool_call_id": "task-call-1",
            "agent_config": {
                "subagents": {
                    "worker": {
                        "description": "",
                        "agent_manifest": {"name": "worker"},
                    }
                }
            },
            "llm_config": MagicMock(),
            "messages": [],
            "parent_registry": ToolRegistry(),
        }

        async for _ in tool.invoke_stream(
            ctx,
            subagent_name="worker",
            prompt="只回复：一致性复测完成",
            description="worker 一致性复测",
        ):
            pass

        assert mock_storage.create_workspace.call_args.kwargs["parent_tool_call_id"] == "task-call-1"
        assert mock_storage.append_context_message.call_args_list[0].args[0] == {
            "role": "user",
            "content": "只回复：一致性复测完成",
            "parent_tool_call_id": "task-call-1",
        }
        assert mock_storage.append_context_message.call_args_list[-1].args[0] == {
            "role": "assistant",
            "content": "一致性复测完成",
            "parent_tool_call_id": "task-call-1",
        }


class TestToolPolicyInheritance:
    """测试 _iter_tool_paths 的工具继承策略。"""

    def test_inherit_merges_manifest_and_builtin_tools(self):
        """inherit 策略合并 manifest tools + builtin tools。"""
        from app.services.agent.runtime_backends.aiasys.backend import _iter_tool_paths

        manifest = {"tools": ["app.agents.tools.read_tool:ReadFile"]}
        paths = _iter_tool_paths(manifest)

        # 至少包含 manifest 中声明的工具
        assert any("ReadFile" in p for p in paths)

    def test_allowlist_uses_only_manifest_tools(self):
        """allowlist 策略只使用 manifest 中显式声明的 tools。"""
        from app.services.agent.runtime_backends.aiasys.backend import _iter_tool_paths
        from app.services.agent.runtime_backends.base import RuntimeSessionCreateSpec

        manifest = {"tools": ["app.agents.tools.read_tool:ReadFile"]}
        spec = _make_spec(tool_policy="allowlist")
        paths = _iter_tool_paths(manifest, spec=spec)

        # 只应包含 manifest 中的工具
        assert all("ReadFile" in p or p == "" for p in paths)
        # 不应包含 builtin 工具（除非也在 manifest 中）

    def test_denylist_excludes_specified_tools(self):
        """denylist 策略继承所有工具但排除 exclude_tools。"""
        from app.services.agent.runtime_backends.aiasys.backend import _iter_tool_paths
        from app.services.agent.runtime_backends.base import RuntimeSessionCreateSpec

        manifest = {
            "tools": [],
            "exclude_tools": ["app.agents.tools.read_tool:ReadFile"],
        }
        spec = _make_spec(tool_policy="denylist")
        paths = _iter_tool_paths(manifest, spec=spec)

        # 不应包含被排除的工具
        assert not any("ReadFile" in p for p in paths)

    def test_default_policy_is_inherit(self):
        """默认 tool_policy 为 inherit。"""
        from app.services.agent.runtime_backends.aiasys.backend import _iter_tool_paths

        manifest = {"tools": []}
        paths_without_spec = _iter_tool_paths(manifest)
        paths_with_inherit = _iter_tool_paths(manifest, spec=_make_spec(tool_policy="inherit"))

        assert paths_without_spec == paths_with_inherit


class TestSubagentNoNesting:
    """测试子 Agent 不注册父 Agent 调度工具。"""

    @patch.object(AiasysRuntimeSession, "_load_agent_config")
    @patch("app.services.agent.runtime_backends.aiasys.backend.create_llm_client")
    @patch("app.services.agent.runtime_backends.aiasys.backend._resolve_provider_entry")
    @patch("app.services.agent.runtime_backends.aiasys.backend._resolve_model_entry")
    @patch("app.services.agent.runtime_backends.aiasys.backend._resolve_model_id")
    @patch("app.services.agent.runtime_backends.aiasys.backend._load_agent_manifest")
    async def test_subagent_registry_excludes_task_tools(
        self,
        mock_load_manifest,
        mock_resolve_model_id,
        mock_resolve_model_entry,
        mock_resolve_provider,
        mock_create_client,
        mock_load_config,
    ):
        """is_subagent=True 时 registry 不应包含 Task/Agent/CreateSubagent 工具。"""
        mock_load_manifest.return_value = {"tools": [], "model": "gpt-4"}
        mock_resolve_model_id.return_value = "gpt-4"
        mock_resolve_model_entry.return_value = {"model": "gpt-4", "provider": "openai", "api_key": "test"}
        mock_resolve_provider.return_value = ("openai", {"api_key": "test"})
        mock_create_client.return_value = MagicMock()
        mock_load_config.return_value = {}

        from app.services.agent.runtime_backends.aiasys.backend import AiasysRuntimeBackend

        backend = AiasysRuntimeBackend()
        spec = _make_spec(is_subagent=True)

        with patch(
            "app.services.agent.runtime_backends.aiasys.backend._instantiate_tool",
            return_value=MagicMock(name="FakeTool"),
        ):
            session = await backend.create_session(spec)

        schemas = session._tool_registry.get_openai_schema()
        tool_names = [s.get("function", {}).get("name") for s in schemas]

        assert "Task" not in tool_names
        assert "Agent" not in tool_names
        assert "CreateSubagent" not in tool_names


async def async_gen(items):
    for item in items:
        yield item
