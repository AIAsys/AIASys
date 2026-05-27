"""测试 ACP client session 对 AIASys runtime 上下文的透传。"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.workspace_path import WorkspacePath
from app.services.agent.models.llm_config import AiasysLlmConfig, LoopControl
from app.services.agent.runtime_backends.base import RuntimeSessionCreateSpec
from app.services.agent.runtime_backends.acp_client.session import (
    AcpClientRuntimeSession,
    _build_mcp_servers_payload,
)


def _write_stub_acp_server(script_path: Path) -> None:
    script_path.write_text(
        "\n".join(
            [
                "from __future__ import annotations",
                "",
                "import json",
                "import sys",
                "from pathlib import Path",
                "",
                "capture_path = Path(sys.argv[1])",
                "session_id = 'stub-acp-session'",
                "",
                "for raw in sys.stdin:",
                "    msg = json.loads(raw)",
                "    method = msg.get('method')",
                "    message_id = msg.get('id')",
                "    if method == 'initialize':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message_id, 'result': {'protocolVersion': 1}}) + '\\n')",
                "        sys.stdout.flush()",
                "        continue",
                "    if method == 'session/new':",
                "        capture_path.write_text(json.dumps(msg.get('params') or {}, ensure_ascii=False), encoding='utf-8')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message_id, 'result': {'sessionId': session_id}}) + '\\n')",
                "        sys.stdout.flush()",
                "        continue",
                "    if method == 'session/prompt':",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'method': 'session/update', 'params': {'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'text': 'stub-ok'}}}}) + '\\n')",
                "        sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': message_id, 'result': {'stopReason': 'end_turn'}}) + '\\n')",
                "        sys.stdout.flush()",
            ]
        ),
        encoding="utf-8",
    )


class TestAcpClientRuntimeSession:
    def test_build_mcp_servers_payload_merges_runtime_blocks(self):
        payload = _build_mcp_servers_payload(
            [
                {"mcpServers": {"db": {"url": "http://127.0.0.1:13003/mcp"}}},
                {"mcp_servers": {"search": {"command": "npx", "args": ["-y", "server"]}}},
                {"invalid": True},
            ]
        )

        assert payload == {
            "db": {"url": "http://127.0.0.1:13003/mcp"},
            "search": {"command": "npx", "args": ["-y", "server"]},
        }

    async def test_session_new_receives_mcp_servers(self, tmp_path):
        capture_path = tmp_path / "session-new.json"
        script_path = tmp_path / "stub_acp_server.py"
        _write_stub_acp_server(script_path)

        spec = RuntimeSessionCreateSpec(
            work_dir=WorkspacePath(str(tmp_path)),
            session_id="acp-session-1",
            config=AiasysLlmConfig(
                default_model="",
                providers={},
                models={},
                loop_control=LoopControl(),
            ),
            agent_file=tmp_path / "agent.toml",
            skills_dir=None,
            mcp_configs=[
                {
                    "mcpServers": {
                        "workspace-db": {
                            "transport": "streamable-http",
                            "url": "http://127.0.0.1:13003/mcp",
                        }
                    }
                }
            ],
            yolo=False,
        )
        session = AcpClientRuntimeSession(
            spec=spec,
            acp_command="python3",
            acp_args=[str(script_path), str(capture_path)],
        )

        try:
            events = [event async for event in session.prompt("hello acp")]
        finally:
            await session.close()

        assert [event.text for event in events if event.text] == ["stub-ok"]
        payload = json.loads(capture_path.read_text(encoding="utf-8"))
        assert payload["cwd"] == str(tmp_path.resolve())
        assert payload["mcpServers"] == {
            "workspace-db": {
                "transport": "streamable-http",
                "url": "http://127.0.0.1:13003/mcp",
            }
        }
