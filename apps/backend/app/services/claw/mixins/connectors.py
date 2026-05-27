"""Claw 连接器读取、微信登录 mixin."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from uuid import uuid4

from app.models.claw import (
    DINGTALK_DEFAULT_BASE_URL,
    FEISHU_DEFAULT_BASE_URL,
    WEIXIN_DEFAULT_BASE_URL,
    ClawConnector,
    ClawPlatformCatalogItem,
)
from app.services.channel import ChannelEntry, get_channel_config

from ._common import (
    _CLAW_BINDING_FILE,
    _CLAW_PLATFORM_CATALOG,
    _SUPPORTED_RUNTIME_PLATFORMS,
    _utcnow_iso,
)

logger = logging.getLogger(__name__)


class ClawConnectorsMixin:
    def _get_channel_config(self, user_id: str):
        return get_channel_config(user_id, workspace_root=self.workspace_root)

    def _channel_to_connector_record(self, entry: ChannelEntry) -> dict[str, Any]:
        account_id = entry.account_id
        token = entry.resolve_token()
        if entry.platform in ("feishu", "dingtalk"):
            account_id = entry.app_id
            token = entry.resolve_app_secret()
        return {
            "connector_id": entry.channel_id,
            "channel_id": entry.channel_id,
            "platform": entry.platform,
            "name": entry.name or entry.channel_id,
            "account_id": account_id,
            "token": token,
            "base_url": entry.base_url,
            "created_at": "",
            "updated_at": "",
            "_source": "channel",
        }

    def _resolve_connector_record_secret(self, record: dict[str, Any]) -> Optional[str]:
        source = str(record.get("_source") or "").strip()
        if source == "channel":
            token = str(record.get("token") or "").strip()
            return token or None
        return None

    def list_platforms(self) -> list[ClawPlatformCatalogItem]:
        return [item.model_copy(deep=True) for item in _CLAW_PLATFORM_CATALOG]

    def get_platform_catalog_item(
        self,
        platform: str,
    ) -> Optional[ClawPlatformCatalogItem]:
        normalized = str(platform or "").strip().lower()
        for item in _CLAW_PLATFORM_CATALOG:
            if item.platform == normalized:
                return item
        return None

    def is_runtime_enabled_platform(self, platform: str) -> bool:
        item = self.get_platform_catalog_item(platform)
        if item is not None:
            return bool(item.runtime_enabled)
        return str(platform or "").strip().lower() in _SUPPORTED_RUNTIME_PLATFORMS

    def _to_public_connector(self, record: dict[str, Any]) -> ClawConnector:
        token = self._resolve_connector_record_secret(record)
        platform = str(record.get("platform") or "weixin").strip().lower() or "weixin"
        base_url = str(record.get("base_url") or "").strip()
        if platform == "weixin":
            base_url = base_url or WEIXIN_DEFAULT_BASE_URL
        elif platform == "feishu":
            base_url = base_url or FEISHU_DEFAULT_BASE_URL
        elif platform == "dingtalk":
            base_url = base_url or DINGTALK_DEFAULT_BASE_URL
        return ClawConnector(
            connector_id=str(record.get("connector_id") or ""),
            channel_id=str(record.get("channel_id") or record.get("connector_id") or ""),
            platform=platform,  # type: ignore[arg-type]
            name=str(record.get("name") or ""),
            account_id=str(record.get("account_id") or ""),
            base_url=base_url,
            has_token=bool(token),
            token_masked=self._mask_secret(token),
            created_at=str(record.get("created_at") or _utcnow_iso()),
            updated_at=str(record.get("updated_at") or _utcnow_iso()),
        )

    def _find_connector_record(
        self,
        user_id: str,
        connector_id: str,
    ) -> Optional[dict[str, Any]]:
        normalized_connector_id = str(connector_id or "").strip()
        channel = self._get_channel_config(user_id).get_channel(normalized_connector_id)
        if channel is not None:
            return self._channel_to_connector_record(channel)
        return None

    def list_connectors(self, user_id: str) -> list[ClawConnector]:
        return [
            self._to_public_connector(self._channel_to_connector_record(channel))
            for channel in self._get_channel_config(user_id).list_channels()
        ]

    def remove_connector_from_all_sessions(self, user_id: str, connector_id: str) -> None:
        """删除频道时级联解绑所有关联的 session。"""
        user_root = self._get_user_root(user_id)
        if not user_root.exists():
            return
        for path in user_root.glob("*/.aiasys/session/" + _CLAW_BINDING_FILE):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if (
                payload.get("connector_id") != connector_id
                and payload.get("channel_id") != connector_id
            ):
                continue
            payload.update(
                {
                    "connector_id": None,
                    "channel_id": None,
                    "chat_id": None,
                    "chat_label": None,
                    "auto_sync_enabled": False,
                    "link_status": "unconfigured",
                    "last_error": "已解绑：关联的频道已删除。",
                    "updated_at": _utcnow_iso(),
                }
            )
            path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def _upsert_weixin_connector_from_login(
        self,
        user_id: str,
        *,
        account_id: str,
        token: str,
        base_url: str,
    ) -> ClawConnector:
        normalized_account_id = account_id.strip()
        now = _utcnow_iso()
        fallback_name = f"微信 {normalized_account_id}"

        channel_config = self._get_channel_config(user_id)
        existing_channel = next(
            (
                channel
                for channel in channel_config.list_channels()
                if channel.platform == "weixin"
                and channel.account_id.strip() == normalized_account_id
            ),
            None,
        )
        channel = ChannelEntry(
            channel_id=(
                existing_channel.channel_id if existing_channel else f"weixin_{uuid4().hex[:12]}"
            ),
            platform="weixin",
            enabled=True,
            name=(
                existing_channel.name
                if existing_channel and existing_channel.name
                else fallback_name
            ),
            account_id=normalized_account_id,
            token=token,
            base_url=base_url,
        )
        channel_config.set_channel(channel)
        record = {
            **self._channel_to_connector_record(channel),
            "created_at": now,
            "updated_at": now,
        }
        connector = self._to_public_connector(record)
        self._schedule_runtime_refresh(user_id)
        return connector
