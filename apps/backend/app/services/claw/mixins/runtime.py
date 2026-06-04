"""Claw 运行时绑定 mixin."""

from __future__ import annotations

import logging
from typing import Optional

from app.models.claw import SessionClawBinding

from ._common import _CLAW_BINDING_FILE, _utcnow_iso

logger = logging.getLogger(__name__)


class ClawRuntimeMixin:
    def resolve_connector_secret(
        self,
        user_id: str,
        connector_id: str,
    ) -> Optional[dict[str, str]]:
        record = self._find_connector_record(user_id, connector_id)
        if record is None:
            return None
        token = self._resolve_connector_record_secret(record)
        if not token:
            return None
        platform = str(record.get("platform") or "weixin").strip().lower() or "weixin"
        base_url = str(record.get("base_url") or "").strip()
        if platform == "weixin":
            from app.models.claw import WEIXIN_DEFAULT_BASE_URL

            base_url = base_url or WEIXIN_DEFAULT_BASE_URL
        elif platform == "feishu":
            from app.models.claw import FEISHU_DEFAULT_BASE_URL

            base_url = base_url or FEISHU_DEFAULT_BASE_URL
        return {
            "connector_id": str(record.get("connector_id") or ""),
            "channel_id": str(record.get("channel_id") or record.get("connector_id") or ""),
            "platform": platform,
            "account_id": str(record.get("account_id") or "").strip(),
            "token": token,
            "base_url": base_url,
        }

    def list_running_bindings(
        self, user_id: str, *, gateway_only: bool = False
    ) -> list[SessionClawBinding]:
        user_root = self._get_user_root(user_id)
        if not user_root.exists():
            return []

        bindings: list[SessionClawBinding] = []
        for path in user_root.glob("*/.aiasys/session/" + _CLAW_BINDING_FILE):
            session_id = path.parent.parent.parent.name
            # Claw 已对齐普通工作区，不再按 source 过滤 session；gateway_only 保留参数兼容
            _ = gateway_only
            binding = self.get_session_binding(user_id, session_id)
            if (
                binding.connector_id
                and binding.connector is not None
                and binding.auto_sync_enabled
                and binding.link_status == "running"
            ):
                bindings.append(binding)
        return sorted(bindings, key=lambda item: item.updated_at, reverse=True)

    def claim_runtime_chat_binding(
        self,
        user_id: str,
        session_id: str,
        *,
        connector_id: str,
        chat_id: str,
        chat_label: Optional[str] = None,
    ) -> SessionClawBinding:
        payload = self._load_session_binding_record(user_id, session_id)
        current_connector_id = str(payload.get("connector_id") or "").strip()
        current_channel_id = str(payload.get("channel_id") or current_connector_id).strip()
        if current_channel_id != connector_id:
            raise ValueError("当前 session 的频道与 runtime channel 不一致")
        if not chat_id.strip():
            raise ValueError("自动认领 chat_id 失败：chat_id 为空")

        payload.update(
            {
                "connector_id": connector_id,
                "channel_id": connector_id,
                "chat_id": chat_id.strip(),
                "chat_label": str(chat_label or payload.get("chat_label") or "").strip() or None,
                "auto_sync_enabled": True,
                "link_status": "running",
                "last_error": None,
                "updated_at": _utcnow_iso(),
            }
        )
        self._save_session_binding_record(user_id, session_id, payload)
        binding = self.get_session_binding(user_id, session_id)
        self._schedule_runtime_refresh(user_id)
        return binding
