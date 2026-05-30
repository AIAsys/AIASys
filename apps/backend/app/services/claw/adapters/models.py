"""Configuration models for Claw platform adapters.

Extracted from vendored hermes_agent/gateway/config.py.
Only includes models actually used by AIASys Claw service.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional


class Platform(Enum):
    """Supported messaging platforms."""

    LOCAL = "local"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    SLACK = "slack"
    SIGNAL = "signal"
    MATTERMOST = "mattermost"
    MATRIX = "matrix"
    HOMEASSISTANT = "homeassistant"
    EMAIL = "email"
    SMS = "sms"
    DINGTALK = "dingtalk"
    API_SERVER = "api_server"
    WEBHOOK = "webhook"
    FEISHU = "feishu"
    WECOM = "wecom"
    WECOM_CALLBACK = "wecom_callback"
    WEIXIN = "weixin"
    BLUEBUBBLES = "bluebubbles"
    QQBOT = "qqbot"


@dataclass
class PlatformConfig:
    """Configuration for a single messaging platform."""

    enabled: bool = False
    token: Optional[str] = None
    api_key: Optional[str] = None

    # Reply threading mode (Telegram/Slack)
    reply_to_mode: str = "first"

    # Platform-specific settings
    extra: Dict[str, Any] = field(default_factory=dict)
