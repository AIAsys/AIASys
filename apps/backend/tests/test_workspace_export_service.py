"""测试 WorkspaceExportService 的对话导出功能。"""

import io
import json
import zipfile
from pathlib import Path

import pytest

from app.services.export.workspace_export_service import WorkspaceExportService


class TestWorkspaceExportConversations:
    """测试工作区导出包含对话记录。"""

    def test_build_archive_without_conversations(self, tmp_path: Path) -> None:
        """不包含对话时，ZIP 内不应有 conversations/ 目录。"""
        ws_dir = tmp_path / "user1" / "ws-1"
        ws_dir.mkdir(parents=True)
        (ws_dir / "hello.txt").write_text("world", encoding="utf-8")

        service = WorkspaceExportService(workspace_root=tmp_path)
        buf, filename = service.build_archive(
            user_id="user1",
            workspace_id="ws-1",
            workspace_meta={"title": "Test"},
            conversation_payloads=[],
            include_conversations=False,
        )

        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "manifest.json" in names
            assert "workspace.json" in names
            assert "conversations.json" in names
            assert "workspace_files/hello.txt" in names
            assert not any(n.startswith("conversations/") for n in names)
        assert filename.startswith("workspace_Test_ws-1")

    def test_build_archive_with_conversations(self, tmp_path: Path) -> None:
        """包含对话时，ZIP 内应有 conversations/{conv_id}.json。"""
        ws_dir = tmp_path / "user1" / "ws-1"
        ws_dir.mkdir(parents=True)
        (ws_dir / "hello.txt").write_text("world", encoding="utf-8")

        # 创建 session 目录和 context.jsonl
        session_dir = ws_dir / ".." / "session-001"
        session_dir.mkdir(parents=True)
        context_file = (
            session_dir / ".aiasys" / "session" / "session-001" / "context.jsonl"
        )
        context_file.parent.mkdir(parents=True)
        messages = [
            {"role": "user", "content": "你好", "timestamp": "2024-01-01T00:00:00Z"},
            {"role": "assistant", "content": "你好！", "timestamp": "2024-01-01T00:00:01Z"},
        ]
        context_file.write_text(
            "\n".join(json.dumps(m, ensure_ascii=False) for m in messages),
            encoding="utf-8",
        )

        service = WorkspaceExportService(workspace_root=tmp_path)
        payloads = [
            {
                "conversation_id": "conv-001",
                "session_id": "session-001",
                "title": "测试对话",
            }
        ]
        buf, _ = service.build_archive(
            user_id="user1",
            workspace_id="ws-1",
            workspace_meta={"title": "Test"},
            conversation_payloads=payloads,
            include_conversations=True,
        )

        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
            assert "conversations/conv-001.json" in names

            data = json.loads(zf.read("conversations/conv-001.json"))
            assert data["_schema_version"] == 1
            assert data["conversation_id"] == "conv-001"
            assert data["message_count"] == 2
            assert len(data["messages"]) == 2
            assert data["messages"][0]["role"] == "user"
            assert data["messages"][1]["role"] == "assistant"

    def test_build_archive_filters_internal_messages(self, tmp_path: Path) -> None:
        """内部 SDK 消息和 system-reminder 应被过滤。"""
        ws_dir = tmp_path / "user1" / "ws-1"
        ws_dir.mkdir(parents=True)

        session_dir = ws_dir / ".." / "session-002"
        session_dir.mkdir(parents=True)
        context_file = (
            session_dir / ".aiasys" / "session" / "session-002" / "context.jsonl"
        )
        context_file.parent.mkdir(parents=True)
        messages = [
            {"role": "user", "content": "你好", "timestamp": "2024-01-01T00:00:00Z"},
            {"role": "_checkpoint", "content": "internal", "timestamp": "2024-01-01T00:00:00Z"},
            {"role": "_usage", "content": "internal", "timestamp": "2024-01-01T00:00:00Z"},
            {"role": "user", "content": "<system-reminder>提醒</system-reminder>", "timestamp": "2024-01-01T00:00:00Z"},
            {"role": "assistant", "content": "收到", "timestamp": "2024-01-01T00:00:01Z"},
        ]
        context_file.write_text(
            "\n".join(json.dumps(m, ensure_ascii=False) for m in messages),
            encoding="utf-8",
        )

        service = WorkspaceExportService(workspace_root=tmp_path)
        payloads = [
            {"conversation_id": "conv-002", "session_id": "session-002", "title": "过滤测试"}
        ]
        buf, _ = service.build_archive(
            user_id="user1",
            workspace_id="ws-1",
            workspace_meta={"title": "Test"},
            conversation_payloads=payloads,
            include_conversations=True,
        )

        with zipfile.ZipFile(buf) as zf:
            data = json.loads(zf.read("conversations/conv-002.json"))
            assert data["message_count"] == 2
            roles = [m["role"] for m in data["messages"]]
            assert roles == ["user", "assistant"]

    def test_build_archive_manifest_entries(self, tmp_path: Path) -> None:
        """manifest.entries 应包含对话文件。"""
        ws_dir = tmp_path / "user1" / "ws-1"
        ws_dir.mkdir(parents=True)

        session_dir = ws_dir / ".." / "session-003"
        session_dir.mkdir(parents=True)
        context_file = (
            session_dir / ".aiasys" / "session" / "session-003" / "context.jsonl"
        )
        context_file.parent.mkdir(parents=True)
        context_file.write_text(
            json.dumps({"role": "user", "content": "hi"}, ensure_ascii=False),
            encoding="utf-8",
        )

        service = WorkspaceExportService(workspace_root=tmp_path)
        payloads = [
            {"conversation_id": "conv-003", "session_id": "session-003", "title": "T"}
        ]
        buf, _ = service.build_archive(
            user_id="user1",
            workspace_id="ws-1",
            workspace_meta={"title": "Test"},
            conversation_payloads=payloads,
            include_conversations=True,
        )

        with zipfile.ZipFile(buf) as zf:
            manifest = json.loads(zf.read("manifest.json"))
            assert manifest["options"]["include_conversations"] is True
            assert "conversations/conv-003.json" in manifest["entries"]
