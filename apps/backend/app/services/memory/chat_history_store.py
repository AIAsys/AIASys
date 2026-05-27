"""用户级聊天记录索引与检索。"""

from __future__ import annotations

from pathlib import Path

from app.core.config import WORKSPACE_DIR
from app.services.memory.constants import (
    CHAT_HISTORY_DB_FILE_NAME,
    USER_MEMORY_STATE_DIR_RELATIVE_PATH,
)
from app.services.memory.session_db import SessionDB


def get_user_chat_history_db_path(user_dir: Path) -> Path:
    return Path(user_dir) / USER_MEMORY_STATE_DIR_RELATIVE_PATH / CHAT_HISTORY_DB_FILE_NAME


class ChatHistoryStore:
    """维护用户级聊天检索索引。"""

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = Path(workspace_root or WORKSPACE_DIR)

    def _get_user_dir(self, user_id: str) -> Path:
        user_dir = self.workspace_root / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_store(self, user_id: str) -> SessionDB:
        return SessionDB(get_user_chat_history_db_path(self._get_user_dir(user_id)))

    def append_message(
        self,
        *,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        created_at: float | None = None,
    ) -> None:
        self._get_store(user_id).add_message(
            session_id=session_id,
            user_id=user_id,
            role=role,
            content=content,
            created_at=created_at,
        )

    def search_history(
        self,
        *,
        user_id: str,
        query: str,
        limit: int = 8,
        exclude_session_id: str | None = None,
    ) -> list[dict]:
        return self._get_store(user_id).search_sessions(
            query=query,
            limit=limit,
            exclude_session_id=exclude_session_id,
        )

    def read_session(
        self,
        *,
        user_id: str,
        session_id: str,
        limit: int = 30,
    ) -> list[dict]:
        return self._get_store(user_id).get_messages(session_id=session_id, limit=limit)

    def delete_session(self, *, user_id: str, session_id: str) -> None:
        self._get_store(user_id).delete_session(session_id)
