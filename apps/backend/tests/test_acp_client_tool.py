"""测试 AIASys ACP tool 的受控入口与上下文投影。"""

from __future__ import annotations

from pathlib import Path

import app.services.agent.runtime_backends.aiasys.tools.acp_client_tool as acp_tool_mod
from app.services.agent.runtime_backends.base import AgentRuntimeEvent


class _FakeAcpClientSession:
    last_init: dict | None = None
    prompt_text: str | None = None
    closed = False

    def __init__(self, *, spec, acp_command, acp_args):
        type(self).last_init = {
            "spec": spec,
            "acp_command": acp_command,
            "acp_args": acp_args,
        }
        type(self).closed = False

    async def prompt(self, user_input, *, merge_wire_messages: bool = False):
        del merge_wire_messages
        type(self).prompt_text = user_input
        yield AgentRuntimeEvent(
            kind="content",
            content_type="text",
            text="external-ok",
        )

    async def close(self):
        type(self).closed = True


class TestAcpClientTool:
    async def test_defaults_to_session_root_and_forwards_mcp_configs(
        self,
        monkeypatch,
        tmp_path,
    ):
        monkeypatch.setattr(
            acp_tool_mod,
            "AcpClientRuntimeSession",
            _FakeAcpClientSession,
        )

        tool = acp_tool_mod.AcpClientTool()
        workspace = tmp_path / "workspace"
        session_root = workspace / "branches" / "branch-1"
        session_root.mkdir(parents=True)
        mcp_configs = [
            {
                "mcpServers": {
                    "workspace-db": {
                        "transport": "streamable-http",
                        "url": "http://127.0.0.1:13003/mcp",
                    }
                }
            }
        ]
        ctx = {
            "workspace": workspace,
            "session_root": session_root,
            "mcp_configs": mcp_configs,
        }

        result = await tool.invoke(
            ctx=ctx,
            agent_command="codex",
            task="检查当前会话里的 TODO",
        )

        assert result.is_error is False
        assert result.content == "external-ok"
        assert _FakeAcpClientSession.prompt_text == "检查当前会话里的 TODO"
        assert _FakeAcpClientSession.closed is True

        assert _FakeAcpClientSession.last_init is not None
        spec = _FakeAcpClientSession.last_init["spec"]
        assert str(spec.work_dir) == str(session_root.resolve())
        assert spec.mcp_configs == mcp_configs
        assert spec.agent_file == Path(session_root.resolve()) / ".acp_agent" / "agent.toml"
        assert _FakeAcpClientSession.last_init["acp_command"] == "codex-acp"
        assert _FakeAcpClientSession.last_init["acp_args"] == []

    async def test_rejects_non_allowlisted_launchers(self):
        tool = acp_tool_mod.AcpClientTool()

        result = await tool.invoke(
            ctx={"session_root": "/tmp"},
            agent_command="bash",
            agent_args=["-lc", "echo unsafe"],
            task="do something",
        )

        assert result.is_error is True
        assert "仅支持" in result.content

    async def test_copilot_accepts_only_default_acp_args(self):
        tool = acp_tool_mod.AcpClientTool()

        result = await tool.invoke(
            ctx={"session_root": "/tmp"},
            agent_command="copilot",
            agent_args=["--stdio"],
            task="do something",
        )

        assert result.is_error is True
        assert "仅支持默认参数" in result.content
