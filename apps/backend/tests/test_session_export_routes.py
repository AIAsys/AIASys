from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

from app.services.export import SessionExportService
from app.services.history.session_execution_journal import SessionExecutionJournal
from app.services.session import SessionManager

TEST_USER_ID = "session_export_test_user"
TEST_SESSION_ID = "session_export_test_session"


def test_session_export_routes_respect_scope_and_skip_sensitive_files(
    tmp_path: Path,
) -> None:
    session_manager = SessionManager(tmp_path)
    session_export_service = SessionExportService(session_manager)
    user_dir = tmp_path / TEST_USER_ID
    session_dir = user_dir / TEST_SESSION_ID
    shutil.rmtree(user_dir, ignore_errors=True)

    history_messages = [
        {
            "role": "user",
            "content": "[执行契约]\n\n[USER_TASK]\n请导出会话",
            "display_content": "请导出会话",
            "timestamp": "2026-03-18T00:40:00",
            "origin": "user",
            "turn_n": 1,
        },
        {
            "role": "assistant",
            "content": [{"type": "text", "text": "好的，开始整理。"}],
            "timestamp": "2026-03-18T00:40:05",
            "origin": "assistant",
            "turn_n": 1,
        },
        {
            "role": "_checkpoint",
            "content": "internal",
            "timestamp": "2026-03-18T00:40:06",
        },
    ]

    session_manager.create_session(
        session_id=TEST_SESSION_ID,
        user_id=TEST_USER_ID,
        title="导出测试",
    )
    session_manager.sync_messages_to_history(
        session_id=TEST_SESSION_ID,
        user_id=TEST_USER_ID,
        messages=history_messages,
    )
    try:
        (session_dir / "analysis.md").write_text("# report\n", encoding="utf-8")
        (session_dir / "notes.txt").write_text("done\n", encoding="utf-8")
        (session_dir / "config.local.json").write_text(
            '{"api_key":"should_not_leak"}',
            encoding="utf-8",
        )

        legacy_dir = session_dir / "workspace"
        legacy_dir.mkdir(exist_ok=True)
        (legacy_dir / "legacy.csv").write_text("a,b\n1,2\n", encoding="utf-8")

        conversation_body, _download_filename = session_export_service.build_conversation_export(
            user_id=TEST_USER_ID,
            session_id=TEST_SESSION_ID,
            exported_by=TEST_USER_ID,
        )
        conversation_payload = json.loads(conversation_body.decode("utf-8"))
        assert conversation_payload["session"]["session_id"] == TEST_SESSION_ID
        assert [item["role"] for item in conversation_payload["messages"]] == [
            "user",
            "assistant",
        ]
        assert conversation_payload["messages"][0]["display_content"] == "请导出会话"

        workspace_body, _download_filename = session_export_service.build_workspace_archive(
            user_id=TEST_USER_ID,
            session_id=TEST_SESSION_ID,
            exported_by=TEST_USER_ID,
        )
        with zipfile.ZipFile(workspace_body) as zip_file:
            names = set(zip_file.namelist())
            assert "manifest.json" in names
            assert "workspace_manifest.json" in names
            assert "workspace/analysis.md" in names
            assert "workspace/notes.txt" in names
            assert "workspace/legacy.csv" not in names
            assert "conversation.json" not in names
            assert "workspace/config.local.json" not in names

            manifest = json.loads(zip_file.read("manifest.json").decode("utf-8"))
            assert manifest["scope"] == "workspace"
            assert "config.local.json" in manifest["guards"]["excluded_sensitive_files"]

        bundle_body, _download_filename = session_export_service.build_bundle_archive(
            user_id=TEST_USER_ID,
            session_id=TEST_SESSION_ID,
            exported_by=TEST_USER_ID,
        )
        with zipfile.ZipFile(bundle_body) as zip_file:
            names = set(zip_file.namelist())
            assert "conversation.json" in names
            assert "workspace/analysis.md" in names
            assert "workspace/legacy.csv" not in names
            assert "workspace/config.local.json" not in names

            conversation_from_zip = json.loads(zip_file.read("conversation.json").decode("utf-8"))
            assert conversation_from_zip[0]["display_content"] == "请导出会话"
            assert "[执行契约]" in conversation_from_zip[0]["content"]
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)


def test_export_backfills_cleared_tool_results_from_execution_journal(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    session_export_service = SessionExportService(session_manager)
    user_dir = tmp_path / TEST_USER_ID
    session_dir = user_dir / TEST_SESSION_ID
    shutil.rmtree(user_dir, ignore_errors=True)

    tool_call_id = "chatcmpl-tool-abc123"
    history_messages = [
        {
            "role": "user",
            "content": "[执行契约]\n\n[USER_TASK]\n运行代码",
            "timestamp": "2026-03-18T00:40:00",
            "origin": "user",
            "turn_n": 1,
        },
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {"name": "LocalIPythonBox", "arguments": '{"code": "print(1)"}'},
                }
            ],
            "timestamp": "2026-03-18T00:40:01",
            "origin": "assistant",
            "turn_n": 1,
        },
        {
            "role": "tool",
            "content": f"[已清理: tool 结果 {tool_call_id}]",
            "tool_call_id": tool_call_id,
            "timestamp": "2026-03-18T00:40:02",
            "origin": "tool",
            "turn_n": 1,
        },
    ]

    session_manager.create_session(
        session_id=TEST_SESSION_ID,
        user_id=TEST_USER_ID,
        title="tool回填测试",
    )
    session_manager.sync_messages_to_history(
        session_id=TEST_SESSION_ID,
        user_id=TEST_USER_ID,
        messages=history_messages,
    )

    journal = SessionExecutionJournal(session_dir, TEST_SESSION_ID)
    journal.append_record(
        code="print(1)",
        started_at="2026-03-18T00:40:01",
        finished_at="2026-03-18T00:40:02",
        status="completed",
        stdout="1\n",
        request_id=tool_call_id,
        tool_name="LocalIPythonBox",
    )

    try:
        conversation_body, _ = session_export_service.build_conversation_export(
            user_id=TEST_USER_ID,
            session_id=TEST_SESSION_ID,
            exported_by=TEST_USER_ID,
        )
        conversation_payload = json.loads(conversation_body.decode("utf-8"))
        tool_messages = [m for m in conversation_payload["messages"] if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["content"] == "1\n"
        assert tool_messages[0].get("_tool_result_backfilled") is True
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
