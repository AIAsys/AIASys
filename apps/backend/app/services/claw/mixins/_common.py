"""Shared constants and helpers for Claw service mixins."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models.claw import ClawPlatformCatalogItem

_CLAW_CONFIG_FILE = "claw-connectors.json"
_CLAW_BINDING_FILE = "claw-binding.json"
_CLAW_QR_LOGIN_DIR = "qr-login"
_CLAW_SESSION_KEYS_FILE = "session-keys.json"
_DEFAULT_QR_TIMEOUT_SECONDS = 480
_SUPPORTED_RUNTIME_PLATFORMS = {"weixin", "feishu", "dingtalk"}
_CLAW_INBOX_DIR = "claw-inbox"
_OUTBOUND_WORKSPACE_REF_RE = re.compile(r"/workspace/[^\s\"')>]+")
_OUTBOUND_AIASYS_FILE_RE = re.compile(
    r":::aiasys-file\{[^}]*src=(?P<quote>[\"'])(?P<path>/workspace/[^\"']+)(?P=quote)[^}]*\}",
    re.IGNORECASE,
)
_OUTBOUND_MARKDOWN_IMAGE_RE = re.compile(r"!\[(?P<label>[^\]]*)\]\((?P<path>/workspace/[^)\s]+)\)")
_OUTBOUND_MARKDOWN_LINK_RE = re.compile(r"\[(?P<label>[^\]]+)\]\((?P<path>/workspace/[^)\s]+)\)")
_PLATFORM_LABELS: dict[str, str] = {
    "weixin": "微信",
    "feishu": "飞书",
    "dingtalk": "钉钉",
}
_CLAW_PLATFORM_CATALOG: tuple[ClawPlatformCatalogItem, ...] = (
    ClawPlatformCatalogItem(
        platform="weixin",
        display_name="微信",
        description="扫码登录后即可把当前会话与单聊或群聊绑定，支持双向消息回流。",
        support_status="ready",
        runtime_enabled=True,
        supports_inbound=True,
        supports_outbound=True,
        supports_typing=True,
        supports_inbound_files=True,
        supports_outbound_files=True,
        supports_qr_login=True,
        transport="长轮询",
        entry_hint="扫码登录 / 自动认领首个聊天",
        auth_fields=["token", "base_url"],
        default_priority=100,
        notes="当前默认优先平台。",
    ),
    ClawPlatformCatalogItem(
        platform="feishu",
        display_name="飞书",
        description="通过飞书开放平台长连接接入，适合团队群和机器人应用。",
        support_status="ready",
        runtime_enabled=True,
        supports_inbound=True,
        supports_outbound=True,
        supports_typing=False,
        supports_inbound_files=True,
        supports_outbound_files=True,
        supports_qr_login=True,
        transport="WebSocket / Webhook",
        entry_hint="App ID / App Secret",
        auth_fields=["app_id", "app_secret", "api_base_url"],
        default_priority=95,
        notes="当前已接入平台。",
    ),
    ClawPlatformCatalogItem(
        platform="dingtalk",
        display_name="钉钉",
        description="面向钉钉群和机器人应用的长连接接入，适合团队消息流转。",
        support_status="ready",
        runtime_enabled=True,
        supports_inbound=True,
        supports_outbound=True,
        supports_typing=False,
        supports_inbound_files=True,
        supports_outbound_files=True,
        supports_qr_login=True,
        transport="Stream WebSocket",
        entry_hint="Client ID / Client Secret",
        auth_fields=[],
        default_priority=68,
        notes="已接入平台。",
    ),
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_platform_source_marker(prompt: str, platform: str) -> str:
    label = _PLATFORM_LABELS.get(platform, platform).strip()
    if not label:
        return prompt.rstrip()
    marker = f"（来自{label}）"
    cleaned = prompt.rstrip()
    if not cleaned:
        return marker
    return f"{cleaned}\n\n{marker}"
