"""Claw 消息过滤、存储 mixin."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from app.services.memory import SessionDB

from ._common import _utcnow_iso

logger = logging.getLogger(__name__)


class ClawMessagesMixin:
    def _is_system_reminder_message(self, message: dict[str, Any]) -> bool:
        if message.get("role") != "user":
            return False
        content = message.get("content")
        if not isinstance(content, str):
            return False
        return content.strip().startswith("<system-reminder>")

    def _visible_history_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            message
            for message in messages
            if message.get("role") not in ("_checkpoint", "_usage", "_system_prompt")
            and not self._is_system_reminder_message(message)
        ]

    def _extract_assistant_text(self, payload: Any) -> str:
        if isinstance(payload, str):
            return payload.strip()
        if isinstance(payload, list):
            parts: list[str] = []
            for item in payload:
                if not isinstance(item, dict):
                    continue
                item_type = str(item.get("type") or "").strip().lower()
                if item_type == "think":
                    continue
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
            return "".join(parts).strip()
        return ""

    def _extract_last_assistant_visible_text(
        self,
        messages: list[dict[str, Any]],
    ) -> tuple[str, Optional[str]]:
        for message in reversed(self._visible_history_messages(messages)):
            if message.get("role") != "assistant":
                continue
            content = message.get("display_content", message.get("content"))
            text = self._extract_assistant_text(content)
            if text:
                timestamp = str(message.get("timestamp") or "").strip() or None
                return text, timestamp
        return "", None

    def _build_digest(self, text: str) -> Optional[str]:
        stripped = text.strip()
        if not stripped:
            return None
        return hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:16]

    def _load_session_db_messages(
        self,
        user_id: str,
        session_id: str,
        *,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        db_path = self._get_session_memory_db_path(user_id, session_id)
        if not db_path.exists():
            return []
        try:
            return SessionDB(db_path).get_messages(session_id, limit=limit)
        except Exception as exc:
            logger.warning(
                "Claw 读取 SessionDB 历史失败，回退 snapshot: user=%s session=%s error=%s",
                user_id,
                session_id,
                exc,
            )
            return []

    def _extract_last_assistant_visible_text_from_session_db(
        self,
        user_id: str,
        session_id: str,
    ) -> tuple[str, Optional[str]]:
        messages = self._load_session_db_messages(user_id, session_id, limit=50)
        for message in reversed(messages):
            if str(message.get("role") or "").strip() != "assistant":
                continue
            text = self._extract_assistant_text(message.get("content"))
            if not text:
                continue
            created_at = message.get("created_at")
            timestamp: Optional[str] = None
            if isinstance(created_at, (int, float)):
                timestamp = datetime.fromtimestamp(
                    float(created_at),
                    tz=timezone.utc,
                ).isoformat()
            return text, timestamp
        return "", None
