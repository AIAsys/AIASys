"""AiasysRuntimeBackend.create_session() MCP 工具注册集成测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import tomli_w

from app.services.agent.runtime_backends.aiasys.backend import AiasysRuntimeBackend
from app.services.agent.runtime_backends.base import RuntimeSessionCreateSpec


class _FakeConfig:
    def __init__(self):
        self.default_model = "test-model"
        self.fallback_order = []
        self.providers = {
            "test": {
                "protocol": "openai_chat_completions",
                "api_key": "test-key",
                "base_url": "http://localhost",
            }
        }
        self.models = {
            "test-model": {
                "provider": "test",
                "model": "test-model",
                "capabilities": [],
            }
        }
        self.task_models = {}
        self.loop_control = MagicMock()
        self.loop_control.max_context_size = 100000
        self.loop_control.compaction_trigger_ratio = 0.85
        self.loop_control.reserved_context_size = 50000
        self.loop_control.max_preserved_messages = 20
        self.loop_control.max_summary_tokens = 500
        self.loop_control.tool_snip_max_chars = 500


@pytest.fixture
def backend() -> AiasysRuntimeBackend:
    return AiasysRuntimeBackend()


@pytest.fixture
def base_spec(tmp_path: Path) -> RuntimeSessionCreateSpec:
    agent_dir = tmp_path / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)
    agent_file = agent_dir / "agent.toml"
    agent_file.write_text(
        tomli_w.dumps({"agent": {"name": "test-agent", "model": "test-model", "tools": []}}),
        encoding="utf-8",
    )

    return RuntimeSessionCreateSpec(
        session_id="test-session",
        work_dir=tmp_path,
        agent_file=agent_file,
        config=_FakeConfig(),
        skills_dir=None,
        mcp_configs=None,
        yolo=True,
        is_subagent=False,
    )


@pytest.mark.asyncio
async def test_create_session_registers_mcp_tools(backend, base_spec):
    """验证传入 mcp_configs 时，create_session 会注册 MCP 工具。"""
    base_spec.mcp_configs = [
        {
            "mcpServers": {
                "test-server": {"command": "python", "args": ["-c", "pass"]},
            }
        }
    ]

    fake_tool = MagicMock()
    fake_tool.name = "get_time"
    fake_tool.description = "Get time"
    fake_tool.inputSchema = {"type": "object"}

    with (
        patch("app.services.agent.runtime_backends.aiasys.mcp_client.MCPClient") as mock_client_cls,
        patch("app.services.agent.runtime_backends.aiasys.tools.mcp_tool.MCPTool") as mock_tool_cls,
    ):
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.list_tools = AsyncMock(return_value=[fake_tool])
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        mock_tool_instance = MagicMock()
        mock_tool_instance.name = "get_time"
        mock_tool_instance.is_mcp = True
        mock_tool_cls.return_value = mock_tool_instance

        session = await backend.create_session(base_spec)

        mock_client_cls.assert_called_once_with(
            "test-server", {"command": "python", "args": ["-c", "pass"]}
        )
        mock_client.connect.assert_awaited_once()
        mock_client.list_tools.assert_awaited_once()
        mock_tool_cls.assert_called_once()

        # 验证 session 持有 mcp_clients
        assert hasattr(session, "_mcp_clients")
        assert len(session._mcp_clients) == 1

        await session.close()
        mock_client.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_session_skips_failed_mcp_server(backend, base_spec):
    """单个 MCP server 连接失败不应影响会话创建。"""
    base_spec.mcp_configs = [
        {
            "mcpServers": {
                "bad-server": {"command": "nonexistent_binary"},
            }
        }
    ]

    with patch(
        "app.services.agent.runtime_backends.aiasys.mcp_client.MCPClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock(side_effect=RuntimeError("spawn failed"))
        mock_client_cls.return_value = mock_client

        session = await backend.create_session(base_spec)
        assert session is not None
        await session.close()


@pytest.mark.asyncio
async def test_create_session_closes_failed_mcp_client(backend, base_spec):
    """MCP server 注册过程中失败时，应关闭已打开的 client。"""
    base_spec.mcp_configs = [
        {
            "mcpServers": {
                "half-open-server": {"command": "python", "args": ["-c", "pass"]},
            }
        }
    ]

    with patch(
        "app.services.agent.runtime_backends.aiasys.mcp_client.MCPClient"
    ) as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.connect = AsyncMock()
        mock_client.list_tools = AsyncMock(side_effect=RuntimeError("list failed"))
        mock_client.close = AsyncMock()
        mock_client_cls.return_value = mock_client

        session = await backend.create_session(base_spec)

        assert session is not None
        mock_client.connect.assert_awaited_once()
        mock_client.list_tools.assert_awaited_once()
        mock_client.close.assert_awaited_once()
        assert len(session._mcp_clients) == 0
        await session.close()


@pytest.mark.asyncio
async def test_create_session_no_mcp_configs_does_not_crash(backend, base_spec):
    """mcp_configs 为 None 时应正常创建 session。"""
    base_spec.mcp_configs = None
    session = await backend.create_session(base_spec)
    assert session is not None
    assert len(session._mcp_clients) == 0
    await session.close()
