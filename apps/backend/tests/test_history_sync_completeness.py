"""
验证 session 重建后 history.json 包含完整的 tool_calls 和 tool 消息。

回归测试：修复前 _persist_message_to_session_history 只保存 assistant 的 content，
不保存 tool_calls，也不持久化 tool 消息，导致 session 重建后 LLM 上下文断裂。
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.session.core import SessionManager
from app.services.session.constants import (
    ACTIVE_SESSION_STATE_DIR_NAME,
    HISTORY_SNAPSHOT_FILE_NAME,
)


@pytest.fixture
def session_manager(tmp_path):
    """创建一个使用临时目录的 SessionManager。"""
    manager = MagicMock(spec=SessionManager)
    manager._get_session_dir = lambda sid, uid: tmp_path / uid / sid
    # 绑定真实方法
    from app.services.session.history import HistoryMixin

    manager._get_history_snapshot_path = HistoryMixin._get_history_snapshot_path.__get__(manager)
    manager._read_history_snapshot = HistoryMixin._read_history_snapshot.__get__(manager)
    manager._write_history_snapshot = HistoryMixin._write_history_snapshot.__get__(manager)
    manager._update_message_count = lambda sid, uid, count: None
    manager.sync_messages_to_history = HistoryMixin.sync_messages_to_history.__get__(manager)
    return manager


def _get_history_path(tmp_path, user_id, session_id):
    return (
        tmp_path
        / user_id
        / session_id
        / ".aiasys"
        / "session"
        / ACTIVE_SESSION_STATE_DIR_NAME
        / HISTORY_SNAPSHOT_FILE_NAME
    )


class TestHistorySyncCompleteness:
    """验证 sync_messages_to_history 写入完整消息，session 重建后能恢复 tool_calls。"""

    def test_sync_preserves_tool_calls_and_tool_messages(self, session_manager, tmp_path):
        """同步后 history.json 应包含 tool_calls 和 tool 消息。"""
        user_id = "test_user"
        session_id = "test_session"

        # 模拟 runtime session 的完整消息列表（含工具调用链）
        messages = [
            {"role": "user", "content": "帮我读文件", "origin": "user"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "ReadFile", "arguments": '{"path": "/tmp/test.txt"}'},
                    }
                ],
                "turn_n": 1,
                "origin": "assistant",
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "file content here",
                "turn_n": 1,
                "origin": "tool",
            },
            {
                "role": "assistant",
                "content": "文件内容是：file content here",
                "turn_n": 1,
                "origin": "assistant",
            },
        ]

        session_manager.sync_messages_to_history(
            session_id=session_id,
            user_id=user_id,
            messages=messages,
        )

        # 读取验证
        history_path = _get_history_path(tmp_path, user_id, session_id)
        assert history_path.exists(), "history.json should exist after sync"

        payload = json.loads(history_path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict)
        assert "messages" in payload
        restored = payload["messages"]

        # 应有 4 条消息
        assert len(restored) == 4

        # 第 2 条是 assistant 且带 tool_calls
        assert restored[1]["role"] == "assistant"
        assert restored[1].get("tool_calls") is not None
        assert len(restored[1]["tool_calls"]) == 1
        assert restored[1]["tool_calls"][0]["id"] == "call_1"

        # 第 3 条是 tool 消息
        assert restored[2]["role"] == "tool"
        assert restored[2]["tool_call_id"] == "call_1"
        assert restored[2]["content"] == "file content here"

    def test_sync_preserves_compaction_snapshot_flag(self, session_manager, tmp_path):
        """同步时应保留已有的 _compaction_snapshot 标记。"""
        user_id = "test_user"
        session_id = "test_session"

        # 先写入一个带压缩标记的 history.json
        history_path = _get_history_path(tmp_path, user_id, session_id)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(
            json.dumps(
                {
                    "_schema_version": 1,
                    "_compaction_snapshot": True,
                    "messages": [{"role": "user", "content": "old"}],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        # 同步新消息
        messages = [
            {"role": "user", "content": "new message"},
            {"role": "assistant", "content": "reply"},
        ]
        session_manager.sync_messages_to_history(
            session_id=session_id,
            user_id=user_id,
            messages=messages,
        )

        # 验证标记保留
        payload = json.loads(history_path.read_text(encoding="utf-8"))
        assert payload.get("_compaction_snapshot") is True
        assert len(payload["messages"]) == 2

    def test_normalize_restored_messages_allows_tool_call_only_assistant(self, tmp_path):
        """_normalize_restored_messages 应接受只有 tool_calls 没有 content 的 assistant 消息。"""
        from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession

        # 构造原始消息列表（模拟从 history.json 读取的数据）
        raw_messages = [
            {"role": "user", "content": "帮我读文件"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "ReadFile", "arguments": "{}"},
                    }
                ],
                "turn_n": 1,
            },
            {
                "role": "tool",
                "tool_call_id": "call_1",
                "content": "result",
                "turn_n": 1,
            },
        ]

        # 调用 _normalize_restored_messages
        # 该方法是实例方法，但我们只需要其逻辑，创建一个最小 mock
        spec = MagicMock()
        spec.work_dir = str(tmp_path)
        spec.is_subagent = False
        spec.memory_enabled = False
        spec.config = MagicMock()
        spec.config.loop_control.max_steps_per_turn = 1
        spec.config.model = MagicMock()
        spec.config.model.max_context_size = 8192
        spec.config.model.context_window = 8192

        # 直接测试规范化逻辑
        # _normalize_restored_messages 不依赖实例状态（除了设置 _session_turn_count）
        session = AiasysRuntimeSession.__new__(AiasysRuntimeSession)
        session._session_turn_count = 0
        restored = session._normalize_restored_messages(raw_messages)

        # 应恢复 3 条消息
        assert len(restored) == 3

        # assistant 消息应保留 tool_calls
        assert restored[1]["role"] == "assistant"
        assert restored[1].get("tool_calls") is not None
        assert len(restored[1]["tool_calls"]) == 1

        # tool 消息应保留 tool_call_id
        assert restored[2]["role"] == "tool"
        assert restored[2]["tool_call_id"] == "call_1"

        # turn_n 应恢复
        assert session._session_turn_count == 1
