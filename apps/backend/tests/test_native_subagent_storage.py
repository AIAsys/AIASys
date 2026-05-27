"""测试 AIASys 原生 SubAgentStorage。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from app.services.agent.subagent_storage import SubAgentStorage


@pytest.fixture
def temp_workspace():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestSubAgentStorage:
    def test_create_workspace(self, temp_workspace, monkeypatch):
        from app.services.agent import subagent_storage

        monkeypatch.setattr(
            subagent_storage, "WORKSPACE_DIR", temp_workspace
        )

        storage = SubAgentStorage("user1", "session1", "agent_abc")
        storage.create_workspace(
            parent_tool_call_id="task_123",
            subagent_type="coder",
            description="编写排序算法",
            effective_model="kimi-test",
        )

        assert storage.subagent_dir.exists()
        assert storage.work_dir.exists()
        assert storage.meta_file.exists()
        assert storage.wire_file.exists()
        assert storage.context_file.exists()

        meta = json.loads(storage.meta_file.read_text())
        assert meta["agent_id"] == "agent_abc"
        assert meta["subagent_type"] == "coder"
        assert meta["status"] == "running"
        assert meta["host_session_id"] == "session1"
        assert meta["last_task_id"] == "task_123"
        assert meta["launch_spec"]["effective_model"] == "kimi-test"

        from app.core.database import SessionLocal, SubAgentInstanceORM

        db = SessionLocal()
        try:
            record = db.query(SubAgentInstanceORM).filter_by(agent_id="agent_abc").one()
            assert record.host_session_id == "session1"
            assert record.subagent_type == "coder"
            assert record.status == "running"
        finally:
            db.close()

        wire_lines = storage.wire_file.read_text().strip().split("\n")
        assert len(wire_lines) == 1
        first_line = json.loads(wire_lines[0])
        assert first_line["type"] == "metadata"

    def test_update_status(self, temp_workspace, monkeypatch):
        from app.services.agent import subagent_storage

        monkeypatch.setattr(subagent_storage, "WORKSPACE_DIR", temp_workspace)

        storage = SubAgentStorage("user1", "session1", "agent_abc")
        storage.create_workspace(
            parent_tool_call_id="task_123",
            subagent_type="coder",
        )
        storage.update_status("completed")

        meta = json.loads(storage.meta_file.read_text())
        assert meta["status"] == "completed"
        assert meta["updated_at"] > meta["created_at"]

        from app.core.database import SessionLocal, SubAgentInstanceORM

        db = SessionLocal()
        try:
            record = db.query(SubAgentInstanceORM).filter_by(agent_id="agent_abc").one()
            assert record.status == "completed"
        finally:
            db.close()

    @pytest.mark.asyncio
    async def test_append_wire_event(self, temp_workspace, monkeypatch):
        from app.services.agent import subagent_storage

        monkeypatch.setattr(subagent_storage, "WORKSPACE_DIR", temp_workspace)

        storage = SubAgentStorage("user1", "session1", "agent_abc")
        storage.create_workspace(
            parent_tool_call_id="task_123",
            subagent_type="coder",
        )
        await storage.append_wire_event(
            "ContentPart", {"type": "text", "text": "hello"}, timestamp=1000.0
        )

        lines = storage.wire_file.read_text().strip().split("\n")
        assert len(lines) == 2  # metadata + event
        event = json.loads(lines[1])
        assert event["timestamp"] == 1000.0
        assert event["message"]["type"] == "ContentPart"
        assert event["message"]["payload"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_append_context_message(self, temp_workspace, monkeypatch):
        from app.services.agent import subagent_storage

        monkeypatch.setattr(subagent_storage, "WORKSPACE_DIR", temp_workspace)

        storage = SubAgentStorage("user1", "session1", "agent_abc")
        storage.create_workspace(
            parent_tool_call_id="task_123",
            subagent_type="coder",
        )
        await storage.append_context_message({"role": "user", "content": "hi"})

        lines = storage.context_file.read_text().strip().split("\n")
        assert len(lines) == 1
        msg = json.loads(lines[0])
        assert msg["role"] == "user"

    @pytest.mark.asyncio
    async def test_append_wire_agent_runtime_event(self, temp_workspace, monkeypatch):
        from app.services.agent import subagent_storage

        monkeypatch.setattr(subagent_storage, "WORKSPACE_DIR", temp_workspace)

        storage = SubAgentStorage("user1", "session1", "agent_abc")
        storage.create_workspace(
            parent_tool_call_id="task_123",
            subagent_type="coder",
        )

        await storage.append_wire_agent_runtime_event(
            {"kind": "content", "content_type": "text", "text": "hello world"},
            timestamp=1000.0,
        )
        await storage.append_wire_agent_runtime_event(
            {"kind": "tool_call", "tool_call_id": "tc1", "tool_name": "Shell", "arguments": {}},
            timestamp=1001.0,
        )
        await storage.append_wire_agent_runtime_event(
            {"kind": "tool_result", "tool_call_id": "tc1", "content": "done", "is_error": False},
            timestamp=1002.0,
        )

        lines = storage.wire_file.read_text().strip().split("\n")
        assert len(lines) == 4  # metadata + 3 events

        # 验证 ContentPart 映射
        ev1 = json.loads(lines[1])
        assert ev1["message"]["type"] == "ContentPart"
        assert ev1["message"]["payload"]["type"] == "text"

        # 验证 ToolCall 映射
        ev2 = json.loads(lines[2])
        assert ev2["message"]["type"] == "ToolCall"
        assert ev2["message"]["payload"]["function"]["name"] == "Shell"

        # 验证 ToolResult 映射
        ev3 = json.loads(lines[3])
        assert ev3["message"]["type"] == "ToolResult"
        assert ev3["message"]["payload"]["return_value"]["output"] == "done"
