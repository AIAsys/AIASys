"""Claw 飞书 QR 扫码登录 mixin（Device Flow）。"""

from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from app.models.claw import (
    FEISHU_DEFAULT_BASE_URL,
    ClawConnector,
    ClawQrLoginSession,
    ClawQrLoginStatus,
)

from ._common import _DEFAULT_QR_TIMEOUT_SECONDS, _PLATFORM_LABELS, _utcnow_iso

logger = logging.getLogger(__name__)

_FEISHU_ACCOUNTS_URL = "https://accounts.feishu.cn"
_FEISHU_REGISTRATION_PATH = "/oauth/v1/app/registration"
_FEISHU_ONBOARD_REQUEST_TIMEOUT_S = 10


class ClawFeishuQrLoginMixin:
    """飞书 Device Flow 扫码创建应用并登录。"""

    def _post_feishu_registration(self, base_url: str, body: dict[str, str]) -> dict[str, Any]:
        """POST form-encoded data to Feishu registration endpoint."""
        data = urlencode(body).encode("utf-8")
        req = Request(
            f"{base_url}{_FEISHU_REGISTRATION_PATH}",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=_FEISHU_ONBOARD_REQUEST_TIMEOUT_S) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8") if hasattr(exc, "read") else ""
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(f"Feishu registration HTTP {exc.code}: {raw[:200]}") from exc
        except Exception as exc:
            raise RuntimeError(f"Feishu registration request failed: {exc}") from exc

    def _feishu_init_registration(self, domain: str = "feishu") -> None:
        base_url = _FEISHU_ACCOUNTS_URL if domain == "feishu" else "https://accounts.larksuite.com"
        res = self._post_feishu_registration(base_url, {"action": "init"})
        methods = res.get("supported_auth_methods") or []
        if "client_secret" not in methods:
            raise RuntimeError(
                f"Feishu registration environment does not support client_secret auth. "
                f"Supported: {methods}"
            )

    def _feishu_begin_registration(self, domain: str = "feishu") -> dict[str, Any]:
        base_url = _FEISHU_ACCOUNTS_URL if domain == "feishu" else "https://accounts.larksuite.com"
        res = self._post_feishu_registration(
            base_url,
            {
                "action": "begin",
                "archetype": "PersonalAgent",
                "auth_method": "client_secret",
                "tp": "ob_app",
            },
        )
        device_code = res.get("device_code")
        if not device_code:
            raise RuntimeError("Feishu registration did not return a device_code")
        qr_url = str(res.get("verification_uri_complete", ""))
        if "?" in qr_url:
            qr_url += "&from=aiasys&tp=aiasys"
        else:
            qr_url += "?from=aiasys&tp=aiasys"
        return {
            "device_code": str(device_code),
            "qr_url": qr_url,
            "user_code": str(res.get("user_code", "")),
            "interval": int(res.get("interval", 5)),
            "expire_in": int(res.get("expire_in", 600)),
            "domain": domain,
        }

    async def _feishu_poll_registration(
        self,
        *,
        device_code: str,
        interval: int,
        expire_in: int,
        domain: str = "feishu",
    ) -> Optional[dict[str, Any]]:
        base_url = _FEISHU_ACCOUNTS_URL if domain == "feishu" else "https://accounts.larksuite.com"
        deadline = time.time() + expire_in
        poll_count = 0
        current_domain = domain

        while time.time() < deadline:
            try:
                res = self._post_feishu_registration(
                    base_url,
                    {"action": "poll", "device_code": device_code, "tp": "ob_app"},
                )
            except Exception as exc:
                logger.warning("[Feishu QR] Poll error: %s", exc)
                await asyncio.sleep(interval)
                continue

            poll_count += 1
            tenant_brand = (res.get("user_info") or {}).get("tenant_brand") or (
                res.get("user_info") or {}
            ).get("brand")
            if tenant_brand == "lark":
                current_domain = "lark"

            if "client_id" in res and "client_secret" in res:
                return {
                    "app_id": str(res["client_id"]),
                    "app_secret": str(res["client_secret"]),
                    "domain": current_domain,
                    "open_id": str((res.get("user_info") or {}).get("open_id", "")),
                }

            error = str(res.get("error") or "").strip().lower()
            if error in ("access_denied", "expired_token"):
                logger.warning("[Feishu QR] Registration %s", error)
                return None

            await asyncio.sleep(interval)

        logger.warning("[Feishu QR] Poll timed out after %ds", expire_in)
        return None

    def _upsert_feishu_connector_from_login(
        self,
        user_id: str,
        *,
        app_id: str,
        app_secret: str,
        domain: str = "feishu",
    ) -> ClawConnector:
        from app.services.channel import ChannelEntry

        normalized_app_id = app_id.strip()
        now = _utcnow_iso()
        label = _PLATFORM_LABELS.get("feishu", "飞书")
        fallback_name = f"{label} {normalized_app_id[:16]}"
        base_url = FEISHU_DEFAULT_BASE_URL if domain == "feishu" else "https://open.larksuite.com"

        channel_config = self._get_channel_config(user_id)
        existing_channel = next(
            (
                channel
                for channel in channel_config.list_channels()
                if channel.platform == "feishu" and channel.app_id.strip() == normalized_app_id
            ),
            None,
        )
        channel = ChannelEntry(
            channel_id=(
                existing_channel.channel_id if existing_channel else f"feishu_{uuid4().hex[:12]}"
            ),
            platform="feishu",
            enabled=True,
            name=(
                existing_channel.name
                if existing_channel and existing_channel.name
                else fallback_name
            ),
            account_id=normalized_app_id,
            app_id=normalized_app_id,
            app_secret=app_secret,
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

    async def start_feishu_qr_login(self, user_id: str) -> ClawQrLoginSession:
        self._feishu_init_registration("feishu")
        begin = self._feishu_begin_registration("feishu")

        flow_id = f"fsqr_{uuid4().hex[:16]}"
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=min(begin["expire_in"], _DEFAULT_QR_TIMEOUT_SECONDS))
        ).isoformat()

        flow_record = {
            "flow_id": flow_id,
            "platform": "feishu",
            "status": "wait",
            "qrcode": "",
            "qrcode_url": begin["qr_url"] or None,
            "device_code": begin["device_code"],
            "interval": begin["interval"],
            "expire_in": begin["expire_in"],
            "domain": begin["domain"],
            "created_at": _utcnow_iso(),
            "updated_at": _utcnow_iso(),
            "expires_at": expires_at,
            "message": "请使用飞书扫描上方二维码或打开链接完成授权。",
        }
        self._save_qr_login_record(user_id, flow_id, flow_record)
        return ClawQrLoginSession(
            flow_id=flow_id,
            platform="feishu",
            status="wait",
            qrcode="",
            qrcode_url=begin["qr_url"] or None,
            expires_at=expires_at,
            message="请使用飞书扫描上方二维码或打开链接完成授权。",
        )

    async def poll_feishu_qr_login(self, user_id: str, flow_id: str) -> ClawQrLoginStatus:
        flow_record = self._load_qr_login_record(user_id, flow_id)
        device_code = str(flow_record.get("device_code") or "").strip()
        if not device_code:
            self._delete_qr_login_record(user_id, flow_id)
            raise ValueError("飞书扫码登录流程缺少设备码，请重新开始")

        interval = int(flow_record.get("interval") or 5)
        expire_in = int(flow_record.get("expire_in") or 600)
        domain = str(flow_record.get("domain") or "feishu")

        result = await self._feishu_poll_registration(
            device_code=device_code,
            interval=interval,
            expire_in=expire_in,
            domain=domain,
        )

        if result is None:
            flow_record["status"] = "expired"
            flow_record["updated_at"] = _utcnow_iso()
            flow_record["message"] = "扫码授权超时或已拒绝，请重新开始。"
            self._save_qr_login_record(user_id, flow_id, flow_record)
            return ClawQrLoginStatus(
                flow_id=flow_id,
                platform="feishu",
                status="expired",
                qrcode="",
                qrcode_url=flow_record.get("qrcode_url"),
                expires_at=flow_record.get("expires_at"),
                message="扫码授权超时或已拒绝，请重新开始。",
            )

        connector = self._upsert_feishu_connector_from_login(
            user_id,
            app_id=result["app_id"],
            app_secret=result["app_secret"],
            domain=result["domain"],
        )
        self._delete_qr_login_record(user_id, flow_id)
        return ClawQrLoginStatus(
            flow_id=flow_id,
            platform="feishu",
            status="confirmed",
            qrcode="",
            qrcode_url=flow_record.get("qrcode_url"),
            expires_at=flow_record.get("expires_at"),
            message=f"飞书授权成功，app_id={result['app_id']}",
            connector=connector,
        )
