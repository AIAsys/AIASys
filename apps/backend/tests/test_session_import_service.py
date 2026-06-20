"""测试会话对话导入服务。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from app.services.export import (
    SessionExportService,
    SessionImportError,
    SessionImportService,
)
from app.services.history.session_history_projection import wrap_user_prompt
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService

TEST_USER_ID = "session_import_test_user"
TEST_WORKSPACE_ID = "session_import_test_workspace"


def _build_export_payload(session_id: str, messages: list[dict]) -> bytes:
    payload = {
        "feature": "session_conversation_export",
        "version": 1,
        "exported_at": "2026-06-20T14:27:45.854163",
        "exported_by": TEST_USER_ID,
        "session": {
            "user_id": TEST_USER_ID,
            "session_id": session_id,
            "title": "导入测试",
            "created_at": "2026-06-20T14:25:53.816152",
            "updated_at": "2026-06-20T14:26:13.150498",
            "message_count": len(messages),
            "env_id": "workspace-default",
            "sandbox_mode": "local",
        },
        "messages": messages,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")


def test_import_conversation_creates_session_and_history(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    registry = WorkspaceRegistryService(tmp_path, session_manager=session_manager)
    service = SessionImportService(
        workspace_root=tmp_path,
        session_manager=session_manager,
        registry=registry,
    )

    user_dir = tmp_path / TEST_USER_ID
    workspace_dir = user_dir / TEST_WORKSPACE_ID
    workspace_dir.mkdir(parents=True)
    registry._ensure_workspace_layout(workspace_dir)
    registry._write_conversation_payloads(TEST_USER_ID, TEST_WORKSPACE_ID, [])

    original_session_id = "original_session_123"
    user_prompt = wrap_user_prompt("分析数据")
    messages = [
        {
            "role": "user",
            "content": user_prompt,
            "display_content": "分析数据",
            "origin": "user",
            "turn_n": 1,
            "timestamp": "2026-06-20T14:25:53.816152",
        },
        {
            "role": "assistant",
            "content": "好的，我来分析。",
            "origin": "assistant",
            "turn_n": 1,
            "timestamp": "2026-06-20T14:25:54.816152",
        },
    ]
    payload_bytes = _build_export_payload(original_session_id, messages)

    try:
        summary = service.import_conversation(
            user_id=TEST_USER_ID,
            workspace_id=TEST_WORKSPACE_ID,
            json_bytes=payload_bytes,
        )
        assert summary.workspace_id == TEST_WORKSPACE_ID
        assert summary.title == "导入测试"

        session_id = summary.session_id
        session_dir = user_dir / session_id
        assert session_dir.exists()

        # 验证 history.json
        history_path = session_dir / ".aiasys" / "session" / "_active" / "history.json"
        history_data = json.loads(history_path.read_text(encoding="utf-8"))
        assert history_data["_schema_version"] == 1
        assert len(history_data["messages"]) == 2
        assert history_data["messages"][0]["role"] == "user"
        assert "display_content" not in history_data["messages"][0]

        # 验证 display_history.jsonl
        display_path = session_dir / ".aiasys" / "session" / session_id / "display_history.jsonl"
        display_lines = [
            json.loads(line)
            for line in display_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(display_lines) == 1
        assert display_lines[0]["content"] == "分析数据"
        assert display_lines[0]["transport_content"] == user_prompt

        # 验证 conversations.json
        payloads = registry._read_conversation_payloads(TEST_USER_ID, TEST_WORKSPACE_ID)
        assert len(payloads) == 1
        assert payloads[0]["session_id"] == session_id
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)


def test_import_conversation_rejects_invalid_feature(tmp_path: Path) -> None:
    session_manager = SessionManager(tmp_path)
    registry = WorkspaceRegistryService(tmp_path, session_manager=session_manager)
    service = SessionImportService(
        workspace_root=tmp_path,
        session_manager=session_manager,
        registry=registry,
    )

    payload = json.dumps(
        {"feature": "workspace_export", "version": 1, "messages": []},
        ensure_ascii=False,
    ).encode("utf-8")

    try:
        service.import_conversation(
            user_id=TEST_USER_ID,
            workspace_id=TEST_WORKSPACE_ID,
            json_bytes=payload,
        )
        raise AssertionError("应抛出 SessionImportError")
    except SessionImportError as exc:
        assert "不支持的导出格式" in str(exc)


def test_export_import_round_trip_preserves_messages(tmp_path: Path) -> None:
    """完整验证：创建会话 -> 导出 -> 导入 -> 读取历史一致。"""
    session_manager = SessionManager(tmp_path)
    export_service = SessionExportService(session_manager)
    registry = WorkspaceRegistryService(tmp_path, session_manager=session_manager)
    import_service = SessionImportService(
        workspace_root=tmp_path,
        session_manager=session_manager,
        registry=registry,
    )

    user_dir = tmp_path / TEST_USER_ID
    src_workspace_dir = user_dir / "src_workspace"
    src_workspace_dir.mkdir(parents=True)
    dst_workspace_dir = user_dir / "dst_workspace"
    dst_workspace_dir.mkdir(parents=True)
    registry._ensure_workspace_layout(src_workspace_dir)
    registry._ensure_workspace_layout(dst_workspace_dir)
    registry._write_conversation_payloads(TEST_USER_ID, "src_workspace", [])
    registry._write_conversation_payloads(TEST_USER_ID, "dst_workspace", [])

    original_session_id = "original_session_123"
    user_prompt = wrap_user_prompt("分析数据")
    original_messages = [
        {
            "role": "user",
            "content": user_prompt,
            "display_content": "分析数据",
            "origin": "user",
            "turn_n": 1,
            "timestamp": "2026-06-20T14:25:53.816152",
        },
        {
            "role": "assistant",
            "content": "好的，我来分析。",
            "origin": "assistant",
            "turn_n": 1,
            "timestamp": "2026-06-20T14:25:54.816152",
        },
        {
            "role": "_checkpoint",
            "content": "internal",
            "timestamp": "2026-06-20T14:25:55.816152",
        },
    ]

    session_manager.create_session(
        session_id=original_session_id,
        user_id=TEST_USER_ID,
        title="往返测试",
        workspace_id="src_workspace",
    )
    session_manager.sync_messages_to_history(
        session_id=original_session_id,
        user_id=TEST_USER_ID,
        messages=original_messages,
    )

    try:
        # 1. 导出
        export_body, _ = export_service.build_conversation_export(
            user_id=TEST_USER_ID,
            session_id=original_session_id,
            exported_by=TEST_USER_ID,
        )
        export_payload = json.loads(export_body.decode("utf-8"))
        assert export_payload["feature"] == "session_conversation_export"
        assert len(export_payload["messages"]) == 2  # _checkpoint 被过滤
        assert export_payload["messages"][0]["display_content"] == "分析数据"

        # 2. 导入到另一个工作区
        summary = import_service.import_conversation(
            user_id=TEST_USER_ID,
            workspace_id="dst_workspace",
            json_bytes=export_body,
        )
        imported_session_id = summary.session_id
        assert summary.workspace_id == "dst_workspace"

        # 3. 验证 history.json
        imported_session_dir = user_dir / imported_session_id
        history_path = imported_session_dir / ".aiasys" / "session" / "_active" / "history.json"
        history_data = json.loads(history_path.read_text(encoding="utf-8"))
        assert len(history_data["messages"]) == 2
        assert history_data["messages"][0]["role"] == "user"
        assert history_data["messages"][0]["content"] == user_prompt
        assert "display_content" not in history_data["messages"][0]

        # 4. 验证 display_history.jsonl
        display_path = (
            imported_session_dir / ".aiasys" / "session" / imported_session_id / "display_history.jsonl"
        )
        display_lines = [
            json.loads(line)
            for line in display_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(display_lines) == 1
        assert display_lines[0]["content"] == "分析数据"

        # 5. 再次导出导入后的会话，验证内容一致
        re_export_body, _ = export_service.build_conversation_export(
            user_id=TEST_USER_ID,
            session_id=imported_session_id,
            exported_by=TEST_USER_ID,
        )
        re_export_payload = json.loads(re_export_body.decode("utf-8"))
        assert len(re_export_payload["messages"]) == 2
        assert re_export_payload["messages"][0]["content"] == user_prompt
        assert re_export_payload["messages"][0]["display_content"] == "分析数据"
    finally:
        shutil.rmtree(user_dir, ignore_errors=True)
