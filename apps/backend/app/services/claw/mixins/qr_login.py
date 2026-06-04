"""Claw 统一 QR 登录分发 mixin（微信 / 飞书 / 钉钉）。"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from app.models.claw import (
    WEIXIN_DEFAULT_BASE_URL,
    ClawConnector,
    ClawQrLoginSession,
    ClawQrLoginStatus,
)

from ._common import _DEFAULT_QR_TIMEOUT_SECONDS, _utcnow_iso

logger = logging.getLogger(__name__)


class ClawQrLoginMixin:
    # ---------- 通用分发入口 ----------

    async def start_qr_login(
        self,
        user_id: str,
        *,
        platform: str,
        bot_type: str = "3",
    ) -> ClawQrLoginSession:
        p = platform.strip().lower()
        if p == "weixin":
            return await self.start_weixin_qr_login(user_id, bot_type=bot_type)
        if p == "feishu":
            return await self.start_feishu_qr_login(user_id)
        if p == "dingtalk":
            return await self.start_dingtalk_qr_login(user_id)
        raise ValueError(f"不支持扫码登录的平台: {platform}")

    async def poll_qr_login(
        self,
        user_id: str,
        flow_id: str,
        *,
        platform: str,
    ) -> ClawQrLoginStatus:
        p = platform.strip().lower()
        if p == "weixin":
            return await self.poll_weixin_qr_login(user_id, flow_id)
        if p == "feishu":
            return await self.poll_feishu_qr_login(user_id, flow_id)
        if p == "dingtalk":
            return await self.poll_dingtalk_qr_login(user_id, flow_id)
        raise ValueError(f"不支持扫码登录的平台: {platform}")

    # ---------- 微信 ----------

    def _build_qr_login_status(
        self,
        flow_record: dict[str, Any],
        *,
        status: Optional[str] = None,
        message: Optional[str] = None,
        connector: Optional[ClawConnector] = None,
    ) -> ClawQrLoginStatus:
        resolved_status = str(status or flow_record.get("status") or "wait").strip() or "wait"
        return ClawQrLoginStatus(
            flow_id=str(flow_record.get("flow_id") or ""),
            platform=str(flow_record.get("platform") or "weixin"),
            status=resolved_status,  # type: ignore[arg-type]
            qrcode=str(flow_record.get("qrcode") or ""),
            qrcode_url=str(flow_record.get("qrcode_url") or "").strip() or None,
            expires_at=str(flow_record.get("expires_at") or "").strip() or None,
            message=(
                message
                if message is not None
                else str(flow_record.get("message") or "").strip() or None
            ),
            connector=connector,
        )

    async def _weixin_qr_api_get(
        self,
        user_id: str,
        *,
        base_url: str,
        endpoint: str,
    ) -> dict[str, Any]:
        with self._hermes_import_scope(user_id):
            weixin_module = importlib.import_module("gateway.platforms.weixin")
            aiohttp_module = getattr(weixin_module, "aiohttp", None)
            if not getattr(weixin_module, "AIOHTTP_AVAILABLE", False) or aiohttp_module is None:
                raise RuntimeError("微信扫码运行时缺少 aiohttp 依赖")
            async with aiohttp_module.ClientSession(trust_env=True) as session:
                result = await weixin_module._api_get(
                    session,
                    base_url=base_url,
                    endpoint=endpoint,
                    timeout_ms=getattr(weixin_module, "QR_TIMEOUT_MS", 35_000),
                )
        if not isinstance(result, dict):
            raise RuntimeError("微信二维码接口返回了无效数据")
        return result

    async def _fetch_weixin_qr_code(
        self,
        user_id: str,
        *,
        bot_type: str,
    ) -> dict[str, Any]:
        return await self._weixin_qr_api_get(
            user_id,
            base_url=WEIXIN_DEFAULT_BASE_URL,
            endpoint=f"ilink/bot/get_bot_qrcode?bot_type={bot_type}",
        )

    async def start_weixin_qr_login(
        self,
        user_id: str,
        *,
        bot_type: str = "3",
    ) -> ClawQrLoginSession:
        qr_response = await self._fetch_weixin_qr_code(user_id, bot_type=bot_type)
        qrcode_value = str(qr_response.get("qrcode") or "").strip()
        qrcode_url = str(qr_response.get("qrcode_img_content") or "").strip()
        if not qrcode_value:
            raise RuntimeError("微信二维码响应缺少 qrcode")

        flow_id = f"wxqr_{uuid4().hex[:16]}"
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=_DEFAULT_QR_TIMEOUT_SECONDS)
        ).isoformat()
        flow_record = {
            "flow_id": flow_id,
            "platform": "weixin",
            "status": "wait",
            "qrcode": qrcode_value,
            "qrcode_url": qrcode_url or None,
            "bot_type": bot_type.strip() or "3",
            "current_base_url": WEIXIN_DEFAULT_BASE_URL,
            "refresh_count": 0,
            "created_at": _utcnow_iso(),
            "updated_at": _utcnow_iso(),
            "expires_at": expires_at,
            "message": "请打开二维码链接并使用微信扫码。",
        }
        self._save_qr_login_record(user_id, flow_id, flow_record)
        return ClawQrLoginSession(
            flow_id=flow_id,
            platform="weixin",
            status="wait",
            qrcode=qrcode_value,
            qrcode_url=qrcode_url or None,
            expires_at=expires_at,
            message="请打开二维码链接并使用微信扫码。",
        )

    async def poll_weixin_qr_login(
        self,
        user_id: str,
        flow_id: str,
    ) -> ClawQrLoginStatus:
        flow_record = self._load_qr_login_record(user_id, flow_id)
        qrcode_value = str(flow_record.get("qrcode") or "").strip()
        if not qrcode_value:
            self._delete_qr_login_record(user_id, flow_id)
            raise ValueError("微信扫码登录流程缺少二维码信息，请重新开始")

        current_base_url = (
            str(flow_record.get("current_base_url") or "").strip() or WEIXIN_DEFAULT_BASE_URL
        )
        status_response = await self._weixin_qr_api_get(
            user_id,
            base_url=current_base_url,
            endpoint=f"ilink/bot/get_qrcode_status?qrcode={qrcode_value}",
        )
        raw_status = str(status_response.get("status") or "wait").strip() or "wait"

        if raw_status == "scaned_but_redirect":
            redirect_host = str(status_response.get("redirect_host") or "").strip()
            if redirect_host:
                flow_record["current_base_url"] = f"https://{redirect_host}"
            flow_record["status"] = "scaned"
            flow_record["updated_at"] = _utcnow_iso()
            flow_record["message"] = "已扫码，正在等待微信确认。"
            self._save_qr_login_record(user_id, flow_id, flow_record)
            return self._build_qr_login_status(
                flow_record,
                status="scaned",
                message="已扫码，正在等待微信确认。",
            )

        if raw_status == "expired":
            refresh_count = int(flow_record.get("refresh_count") or 0) + 1
            if refresh_count > 3:
                self._delete_qr_login_record(user_id, flow_id)
                flow_record["refresh_count"] = refresh_count
                flow_record["status"] = "expired"
                flow_record["message"] = "二维码已多次过期，请重新开始登录。"
                return self._build_qr_login_status(
                    flow_record,
                    status="expired",
                    message="二维码已多次过期，请重新开始登录。",
                )

            qr_response = await self._fetch_weixin_qr_code(
                user_id,
                bot_type=str(flow_record.get("bot_type") or "3"),
            )
            qrcode_value = str(qr_response.get("qrcode") or "").strip()
            if not qrcode_value:
                raise RuntimeError("微信二维码刷新失败：缺少 qrcode")
            flow_record.update(
                {
                    "status": "wait",
                    "qrcode": qrcode_value,
                    "qrcode_url": str(qr_response.get("qrcode_img_content") or "").strip() or None,
                    "current_base_url": WEIXIN_DEFAULT_BASE_URL,
                    "refresh_count": refresh_count,
                    "updated_at": _utcnow_iso(),
                    "expires_at": (
                        datetime.now(timezone.utc) + timedelta(seconds=_DEFAULT_QR_TIMEOUT_SECONDS)
                    ).isoformat(),
                    "message": "二维码已刷新，请重新扫码。",
                }
            )
            self._save_qr_login_record(user_id, flow_id, flow_record)
            return self._build_qr_login_status(
                flow_record,
                status="wait",
                message="二维码已刷新，请重新扫码。",
            )

        if raw_status == "confirmed":
            account_id = str(status_response.get("ilink_bot_id") or "").strip()
            token = str(status_response.get("bot_token") or "").strip()
            base_url = str(status_response.get("baseurl") or WEIXIN_DEFAULT_BASE_URL).strip()
            if not account_id or not token:
                raise RuntimeError("微信扫码已确认，但返回的凭据不完整")
            connector = self._upsert_weixin_connector_from_login(
                user_id,
                account_id=account_id,
                token=token,
                base_url=base_url or WEIXIN_DEFAULT_BASE_URL,
            )
            self._delete_qr_login_record(user_id, flow_id)
            flow_record.update(
                {
                    "status": "confirmed",
                    "updated_at": _utcnow_iso(),
                    "message": f"微信连接成功，account_id={account_id}",
                }
            )
            return self._build_qr_login_status(
                flow_record,
                status="confirmed",
                message=f"微信连接成功，account_id={account_id}",
                connector=connector,
            )

        if raw_status == "scaned":
            flow_record["status"] = "scaned"
            flow_record["updated_at"] = _utcnow_iso()
            flow_record["message"] = "已扫码，请在微信里确认。"
            self._save_qr_login_record(user_id, flow_id, flow_record)
            return self._build_qr_login_status(
                flow_record,
                status="scaned",
                message="已扫码，请在微信里确认。",
            )

        flow_record["status"] = "wait"
        flow_record["updated_at"] = _utcnow_iso()
        flow_record["message"] = "等待扫码。"
        self._save_qr_login_record(user_id, flow_id, flow_record)
        return self._build_qr_login_status(
            flow_record,
            status="wait",
            message="等待扫码。",
        )
