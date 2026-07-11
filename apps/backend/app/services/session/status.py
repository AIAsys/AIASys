"""
会话状态管理 Mixin
"""

import json
import logging
from datetime import datetime
from typing import Optional

from app.utils.path_utils import atomic_write_text

logger = logging.getLogger(__name__)


class StatusMixin:
    """会话状态管理功能"""

    def _derive_status(
        self,
        message_count: int,
        existing_status: Optional[str] = None,
        completed_message_count: Optional[int] = None,
    ) -> str:
        """根据消息数推导会话状态，必要时保留已完成/活跃标记。"""
        if existing_status == "completed":
            if completed_message_count is None:
                return "completed"
            if message_count <= completed_message_count:
                return "completed"
        # 显式标记为 active 的空会话不应被推导为 draft，否则前端新建会话会被列表过滤掉
        if existing_status == "active":
            return "active"
        return "active" if message_count > 0 else "draft"

    def mark_session_completed(self, session_id: str, user_id: str) -> bool:
        """将会话标记为 completed（若会话存在）。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法标记完成: user=%s, session=%s",
                    user_id,
                    session_id,
                )
                return False

            now = datetime.now().isoformat()
            metadata.status = "completed"
            metadata.completed_at = now
            metadata.completed_message_count = metadata.message_count
            metadata.updated_at = now

            session_dir = self._get_session_dir(session_id, user_id)
            meta_path = session_dir / "metadata.json"
            atomic_write_text(
                meta_path,
                json.dumps(metadata.model_dump(), indent=2, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.error(
                "标记会话完成失败: user=%s, session=%s, error=%s",
                user_id,
                session_id,
                e,
            )
            return False

    def mark_session_active(self, session_id: str, user_id: str) -> bool:
        """清除 completed 标记并将会话恢复为 active/draft。"""
        try:
            metadata = self.get_session(session_id, user_id)
            if not metadata:
                logger.warning(
                    "会话元数据不存在，无法恢复活跃: user=%s, session=%s",
                    user_id,
                    session_id,
                )
                return False

            metadata.status = self._derive_status(
                metadata.message_count,
                None,
                None,
            )
            metadata.completed_at = None
            metadata.completed_message_count = None
            metadata.updated_at = datetime.now().isoformat()

            session_dir = self._get_session_dir(session_id, user_id)
            meta_path = session_dir / "metadata.json"
            atomic_write_text(
                meta_path,
                json.dumps(metadata.model_dump(), indent=2, ensure_ascii=False),
            )
            return True
        except Exception as e:
            logger.error(
                "恢复会话活跃失败: user=%s, session=%s, error=%s",
                user_id,
                session_id,
                e,
            )
            return False
