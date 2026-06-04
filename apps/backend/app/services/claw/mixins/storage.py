"""Claw 存储路径、配置读写、密钥管理、加密解密 mixin."""

from __future__ import annotations

import contextlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

from app.core.encryption import EncryptionError, encryption_service
from app.services.memory.constants import MEMORY_DIR_NAME
from app.services.workspace_registry import get_workspace_registry_service

from ._common import (
    _CLAW_BINDING_FILE,
    _CLAW_CONFIG_FILE,
    _CLAW_QR_LOGIN_DIR,
    _CLAW_SESSION_KEYS_FILE,
    _utcnow_iso,
)

logger = logging.getLogger(__name__)


class ClawStorageMixin:
    # ==================== 存储路径 ====================

    def _get_user_root(self, user_id: str) -> Path:
        return self.workspace_root / user_id

    def _get_user_config_path(self, user_id: str) -> Path:
        return self._get_user_root(user_id) / ".config" / _CLAW_CONFIG_FILE

    def _get_session_binding_path(self, user_id: str, session_id: str) -> Path:
        return (
            self._get_user_root(user_id) / session_id / ".aiasys" / "session" / _CLAW_BINDING_FILE
        )

    def _get_user_hermes_home(self, user_id: str) -> Path:
        path = self._get_user_root(user_id) / ".claw" / "hermes-home"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_user_qr_login_dir(self, user_id: str) -> Path:
        path = self._get_user_root(user_id) / ".claw" / _CLAW_QR_LOGIN_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_qr_login_flow_path(self, user_id: str, flow_id: str) -> Path:
        return self._get_user_qr_login_dir(user_id) / f"{flow_id}.json"

    def _get_session_keys_path(self, user_id: str) -> Path:
        path = self._get_user_root(user_id) / ".claw" / _CLAW_SESSION_KEYS_FILE
        return path

    def _load_session_keys(self, user_id: str) -> dict[str, str]:
        """加载 session_key → session_id 映射。"""
        path = self._get_session_keys_path(user_id)
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(k): str(v) for k, v in raw.items()}
        except Exception as exc:
            logger.warning("加载 Claw session keys 失败: user=%s error=%s", user_id, exc)
        return {}

    def _save_session_keys(self, user_id: str, mapping: dict[str, str]) -> None:
        path = self._get_session_keys_path(user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(mapping, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _get_session_memory_db_path(self, user_id: str, session_id: str) -> Path:
        return self._get_user_root(user_id) / session_id / MEMORY_DIR_NAME / "sessions.db"

    def _get_session_workspace_root(self, user_id: str, session_id: str) -> Path:
        return get_workspace_registry_service().get_logical_workspace_root(user_id, session_id)

    def _get_effective_workspace_root(self, user_id: str, session_id: str) -> Path:
        """返回当前 session 的 Claw 工作区根目录。"""
        return self._get_session_workspace_root(user_id, session_id)

    def _get_session_claw_inbox_dir(self, user_id: str, session_id: str, platform: str) -> Path:
        from ._common import _CLAW_INBOX_DIR

        path = self._get_effective_workspace_root(user_id, session_id) / _CLAW_INBOX_DIR / platform
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _load_qr_login_record(self, user_id: str, flow_id: str) -> dict[str, Any]:
        path = self._get_qr_login_flow_path(user_id, flow_id)
        if not path.exists():
            raise ValueError("指定的微信扫码登录流程不存在或已失效")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValueError("微信扫码登录流程数据已损坏") from exc
        if not isinstance(payload, dict):
            raise ValueError("微信扫码登录流程数据无效")
        return payload

    def _save_qr_login_record(self, user_id: str, flow_id: str, payload: dict[str, Any]) -> None:
        path = self._get_qr_login_flow_path(user_id, flow_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _delete_qr_login_record(self, user_id: str, flow_id: str) -> None:
        path = self._get_qr_login_flow_path(user_id, flow_id)
        with contextlib.suppress(FileNotFoundError):
            path.unlink()

    def _schedule_runtime_refresh(self, user_id: str) -> None:
        try:
            from app.services.claw_runtime import get_claw_runtime_manager

            get_claw_runtime_manager().schedule_refresh_for_user(user_id)
        except Exception as exc:
            logger.warning("Claw runtime refresh 调度失败: user=%s error=%s", user_id, exc)

    def _build_runtime_timestamp(self) -> str:
        return _utcnow_iso()

    # ==================== 安全辅助 ====================

    def _encrypt_secret(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        return encryption_service.encrypt(value)

    def _decrypt_secret(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        try:
            return encryption_service.decrypt(value)
        except EncryptionError as exc:
            logger.warning("Claw 敏感字段解密失败: %s", exc)
            return None

    def _mask_secret(self, value: Optional[str]) -> Optional[str]:
        if not value:
            return None
        if len(value) <= 4:
            return "*" * len(value)
        return f"{value[:2]}***{value[-2:]}"
