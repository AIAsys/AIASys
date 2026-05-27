"""Claw Gateway 会话管理 mixin."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class ClawGatewayMixin:
    def list_gateway_sessions(self, user_id: str) -> list[dict[str, Any]]:
        """
        列出该用户的所有 Gateway Sessions（按 session_keys.json 映射）。
        """
        mapping = self._load_session_keys(user_id)
        results: list[dict[str, Any]] = []
        for session_key, session_id in mapping.items():
            meta = self.session_manager.get_session(session_id, user_id)
            if meta is None:
                continue
            parts = session_key.split(":", 2)
            platform = parts[0] if len(parts) > 0 else ""
            chat_type = parts[1] if len(parts) > 1 else ""
            chat_id = parts[2] if len(parts) > 2 else ""
            binding = self.get_session_binding(user_id, session_id)
            results.append(
                {
                    "session_id": session_id,
                    "session_key": session_key,
                    "platform": platform,
                    "chat_type": chat_type,
                    "chat_id": chat_id,
                    "title": meta.title,
                    "status": meta.status,
                    "message_count": meta.message_count,
                    "created_at": meta.created_at,
                    "updated_at": meta.updated_at,
                    "connector_id": binding.connector_id if binding else None,
                    "link_status": binding.link_status if binding else None,
                    "auto_sync_enabled": binding.auto_sync_enabled if binding else False,
                }
            )
        # 按创建时间倒序
        results.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return results
