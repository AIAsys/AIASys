"""
会话历史管理 Mixin
"""

import json
import logging
from pathlib import Path
from typing import List

from app.utils.path_utils import atomic_write_text

logger = logging.getLogger(__name__)


class HistoryMixin:
    """会话历史管理功能"""

    def _get_history_snapshot_path(self, session_dir: Path) -> Path:
        """返回历史快照文件路径"""
        from app.services.session.constants import (
            ACTIVE_SESSION_STATE_DIR_NAME,
            HISTORY_SNAPSHOT_FILE_NAME,
        )

        return (
            session_dir
            / ".aiasys/session"
            / ACTIVE_SESSION_STATE_DIR_NAME
            / HISTORY_SNAPSHOT_FILE_NAME
        )

    def _read_history_snapshot(self, session_dir: Path) -> list[dict]:
        """读取当前历史快照信封格式。"""
        history_path = self._get_history_snapshot_path(session_dir)
        if history_path.exists():
            try:
                data = json.loads(history_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    messages = data.get("messages") or []
                    if isinstance(messages, list):
                        return messages
            except Exception:
                pass
        return []

    def _write_history_snapshot(self, session_dir: Path, messages: list[dict]) -> Path:
        """写入历史快照信封格式。"""
        history_path = self._get_history_snapshot_path(session_dir)
        history_path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict = {"_schema_version": 1, "messages": messages}
        # 保留压缩快照标记，避免 SessionManager 追加消息后 UI 历史接口丢失压缩状态。
        if history_path.exists():
            try:
                existing = json.loads(history_path.read_text(encoding="utf-8"))
                if isinstance(existing, dict) and existing.get("_compaction_snapshot"):
                    payload["_compaction_snapshot"] = True
            except Exception:
                pass
        atomic_write_text(
            history_path,
            json.dumps(payload, indent=2, ensure_ascii=False),
        )
        return history_path

    def add_message(
        self,
        session_id: str,
        user_id: str,
        message,
    ):
        """添加消息到会话历史"""
        session_dir = self._get_session_dir(session_id, user_id)

        # 读取现有历史
        history = self._read_history_snapshot(session_dir)

        # 添加新消息
        if hasattr(message, "model_dump"):
            history.append(message.model_dump())
        elif isinstance(message, dict):
            history.append(message)
        else:
            raise TypeError(f"Unsupported history message type: {type(message)!r}")

        # 保存历史
        self._write_history_snapshot(session_dir, history)

        # 更新消息计数
        self._update_message_count(session_id, user_id, len(history))

    def get_history(self, session_id: str, user_id: str) -> List[dict]:
        """获取会话历史"""
        session_dir = self._get_session_dir(session_id, user_id)
        return self._read_history_snapshot(session_dir)

    def sync_messages_to_history(self, session_id: str, user_id: str, messages: list[dict]) -> None:
        """用完整消息列表覆写 history.json 快照。

        用于执行完成后将 runtime session 的完整消息（含 tool_calls 和 tool 消息）
        同步到持久化历史，确保 session 重建后 LLM 上下文完整。
        保留已有的 _compaction_snapshot 标记。
        """
        session_dir = self._get_session_dir(session_id, user_id)
        self._write_history_snapshot(session_dir, messages)
        self._update_message_count(session_id, user_id, len(messages))
