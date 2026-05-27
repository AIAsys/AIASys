"""频道管理模块 — 统一 YAML 配置管理 IM 平台连接。"""

from .config import SUPPORTED_PLATFORMS, ChannelConfig, ChannelEntry, get_channel_config

__all__ = ["ChannelConfig", "ChannelEntry", "SUPPORTED_PLATFORMS", "get_channel_config"]
