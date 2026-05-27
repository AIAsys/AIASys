"""Claw 钉钉 QR 扫码登录 mixin（Device Flow）。"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

import httpx

from app.models.claw import (
    DINGTALK_DEFAULT_BASE_URL,
    ClawConnector,
    ClawQrLoginSession,
    ClawQrLoginStatus,
)

from ._common import _DEFAULT_QR_TIMEOUT_SECONDS, _PLATFORM_LABELS, _utcnow_iso

logger = logging.getLogger(__name__)

_DINGTALK_REG_BASE = "https://oapi.dingtalk.com"
_DINGTALK_REG_SOURCE = "DING_DWS_CLAW"
_DINGTALK_REQUEST_TIMEOUT_S = 10


class ClawDingTalkQrLoginMixin:
    """钉钉 Device Flow 扫码创建应用并登录。"""

    async def _post_dingtalk_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST JSON to DingTalk endpoint and return parsed response."""
        try:
            async with httpx.AsyncClient(timeout=_DINGTALK_REQUEST_TIMEOUT_S) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                result = resp.json()
        except httpx.HTTPStatusError as exc:
            raw = exc.response.text
            try:
                result = json.loads(raw)
            except json.JSONDecodeError:
                raise RuntimeError(
                    f"DingTalk API HTTP {exc.response.status_code}: {raw[:200]}"
                ) from exc
        except Exception as exc:
            raise RuntimeError(f"DingTalk API request failed: {exc}") from exc

        errcode = result.get("errcode")
        if errcode is not None and errcode != 0:
            errmsg = result.get("errmsg", "unknown error")
            raise RuntimeError(f"DingTalk API error {errcode}: {errmsg}")
        return result

    async def _dingtalk_init_registration(self) -> str:
        res = await self._post_dingtalk_json(
            f"{_DINGTALK_REG_BASE}/app/registration/init",
            {"source": _DINGTALK_REG_SOURCE},
        )
        nonce = str(res.get("nonce") or "").strip()
        if not nonce:
            raise RuntimeError("DingTalk init registration did not return a nonce")
        return nonce

    async def _dingtalk_begin_registration(self, nonce: str) -> dict[str, Any]:
        res = await self._post_dingtalk_json(
            f"{_DINGTALK_REG_BASE}/app/registration/begin",
            {"nonce": nonce},
        )
        device_code = str(res.get("device_code") or "").strip()
        qr_url = str(res.get("verification_uri_complete") or "").strip()
        expires_in = int(res.get("expires_in") or 300)
        if not device_code:
            raise RuntimeError("DingTalk begin registration did not return a device_code")
        if not qr_url:
            raise RuntimeError(
                "DingTalk begin registration did not return a verification_uri_complete"
            )
        return {
            "device_code": device_code,
            "qr_url": qr_url,
            "expires_in": expires_in,
        }

    async def _dingtalk_poll_once(self, *, device_code: str) -> Optional[dict[str, Any]]:
        """Single poll attempt. Returns credentials dict on SUCCESS, None on WAITING.

        Raises RuntimeError on terminal failure (EXPIRED, FAIL, network error).
        """
        try:
            res = await self._post_dingtalk_json(
                f"{_DINGTALK_REG_BASE}/app/registration/poll",
                {"device_code": device_code},
            )
        except Exception as exc:
            raise RuntimeError(f"DingTalk poll request failed: {exc}") from exc

        status = str(res.get("status") or "").upper()
        if status == "SUCCESS":
            client_id = str(res.get("client_id") or "").strip()
            client_secret = str(res.get("client_secret") or "").strip()
            if not client_id or not client_secret:
                raise RuntimeError(
                    "DingTalk authorization succeeded but missing client credentials"
                )
            return {
                "client_id": client_id,
                "client_secret": client_secret,
            }
        if status == "WAITING":
            return None
        if status == "EXPIRED":
            raise RuntimeError("钉钉扫码二维码已过期，请重新开始")
        if status == "FAIL":
            reason = res.get("fail_reason") or "unknown reason"
            raise RuntimeError(f"钉钉授权失败: {reason}")
        raise RuntimeError(f"钉钉授权返回未知状态: {status}")

    def _upsert_dingtalk_connector_from_login(
        self,
        user_id: str,
        *,
        client_id: str,
        client_secret: str,
    ) -> ClawConnector:
        from app.services.channel import ChannelEntry

        normalized_client_id = client_id.strip()
        now = _utcnow_iso()
        label = _PLATFORM_LABELS.get("dingtalk", "钉钉")
        fallback_name = f"{label} {normalized_client_id[:16]}"

        channel_config = self._get_channel_config(user_id)
        existing_channel = next(
            (
                channel
                for channel in channel_config.list_channels()
                if channel.platform == "dingtalk" and channel.app_id.strip() == normalized_client_id
            ),
            None,
        )
        channel = ChannelEntry(
            channel_id=(
                existing_channel.channel_id if existing_channel else f"dingtalk_{uuid4().hex[:12]}"
            ),
            platform="dingtalk",
            enabled=True,
            name=(
                existing_channel.name
                if existing_channel and existing_channel.name
                else fallback_name
            ),
            account_id=normalized_client_id,
            app_id=normalized_client_id,
            app_secret=client_secret,
            base_url=DINGTALK_DEFAULT_BASE_URL,
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

    async def start_dingtalk_qr_login(self, user_id: str) -> ClawQrLoginSession:
        nonce = await self._dingtalk_init_registration()
        begin = await self._dingtalk_begin_registration(nonce)

        flow_id = f"dtqr_{uuid4().hex[:16]}"
        expires_at = (
            datetime.now(timezone.utc)
            + timedelta(seconds=min(begin["expires_in"], _DEFAULT_QR_TIMEOUT_SECONDS))
        ).isoformat()

        flow_record = {
            "flow_id": flow_id,
            "platform": "dingtalk",
            "status": "wait",
            "qrcode": "",
            "qrcode_url": begin["qr_url"],
            "device_code": begin["device_code"],
            "expires_in": begin["expires_in"],
            "created_at": _utcnow_iso(),
            "updated_at": _utcnow_iso(),
            "expires_at": expires_at,
            "message": "请使用钉钉扫描上方二维码或打开链接完成授权。",
        }
        self._save_qr_login_record(user_id, flow_id, flow_record)
        return ClawQrLoginSession(
            flow_id=flow_id,
            platform="dingtalk",
            status="wait",
            qrcode="",
            qrcode_url=begin["qr_url"],
            expires_at=expires_at,
            message="请使用钉钉扫描上方二维码或打开链接完成授权。",
        )

    async def poll_dingtalk_qr_login(self, user_id: str, flow_id: str) -> ClawQrLoginStatus:
        flow_record = self._load_qr_login_record(user_id, flow_id)
        device_code = str(flow_record.get("device_code") or "").strip()
        if not device_code:
            self._delete_qr_login_record(user_id, flow_id)
            raise ValueError("钉钉扫码登录流程缺少设备码，请重新开始")

        expires_in = int(flow_record.get("expires_in") or 300)

        try:
            result = await self._dingtalk_poll_once(device_code=device_code)
        except RuntimeError as exc:
            self._delete_qr_login_record(user_id, flow_id)
            raise

        if result is None:
            # WAITING: front-end will keep polling
            flow_record["status"] = "wait"
            flow_record["updated_at"] = _utcnow_iso()
            flow_record["message"] = "等待用户扫码确认..."
            self._save_qr_login_record(user_id, flow_id, flow_record)
            return ClawQrLoginStatus(
                flow_id=flow_id,
                platform="dingtalk",
                status="wait",
                qrcode="",
                qrcode_url=flow_record.get("qrcode_url"),
                expires_at=flow_record.get("expires_at"),
                message="等待用户扫码确认...",
            )

        connector = self._upsert_dingtalk_connector_from_login(
            user_id,
            client_id=result["client_id"],
            client_secret=result["client_secret"],
        )
        self._delete_qr_login_record(user_id, flow_id)
        return ClawQrLoginStatus(
            flow_id=flow_id,
            platform="dingtalk",
            status="confirmed",
            qrcode="",
            qrcode_url=flow_record.get("qrcode_url"),
            expires_at=flow_record.get("expires_at"),
            message=f"钉钉授权成功，client_id={result['client_id']}",
            connector=connector,
        )
