"""频道配置管理 — YAML 驱动，参考 Hermes GatewayConfig 设计。"""

from __future__ import annotations

import logging
import os
import re
import tempfile
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli_w
from filelock import FileLock

from app.core.config import WORKSPACE_DIR
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

# 当前真正接通 runtime 的平台
SUPPORTED_PLATFORMS = {"weixin", "feishu", "dingtalk"}

# 平台默认配置
PLATFORM_DEFAULTS: dict[str, dict[str, Any]] = {
    "weixin": {
        "base_url": "https://ilinkai.weixin.qq.com",
    },
    "feishu": {
        "base_url": "https://open.feishu.cn",
    },
    "dingtalk": {
        "base_url": "https://oapi.dingtalk.com",
    },
}


@dataclass
class ChannelEntry:
    """单个频道配置项。"""

    channel_id: str
    platform: str
    enabled: bool = False
    name: str = ""
    account_id: str = ""
    token: str = ""
    base_url: str = ""
    home_chat_id: str = ""
    allowed_users: list[str] = field(default_factory=list)
    # 平台特有字段
    app_id: str = ""  # feishu
    app_secret: str = ""  # feishu

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典（写入 YAML）。"""
        result: dict[str, Any] = {
            "platform": self.platform,
            "enabled": self.enabled,
        }
        if self.name:
            result["name"] = self.name
        if self.account_id:
            result["account_id"] = self.account_id
        if self.token:
            result["token"] = self.token
        if self.base_url:
            result["base_url"] = self.base_url
        if self.home_chat_id:
            result["home_chat_id"] = self.home_chat_id
        if self.allowed_users:
            result["allowed_users"] = self.allowed_users
        if self.app_id:
            result["app_id"] = self.app_id
        if self.app_secret:
            result["app_secret"] = self.app_secret
        return result

    @classmethod
    def from_dict(cls, channel_id: str, data: dict[str, Any]) -> ChannelEntry:
        """从字典反序列化。"""
        platform = str(data.get("platform", "")).strip()
        # 应用平台默认值
        defaults = PLATFORM_DEFAULTS.get(platform, {})
        return cls(
            channel_id=channel_id,
            platform=platform,
            enabled=bool(data.get("enabled", False)),
            name=str(data.get("name", "")).strip(),
            account_id=str(data.get("account_id", "")).strip(),
            token=str(data.get("token", "")).strip(),
            base_url=str(data.get("base_url", defaults.get("base_url", ""))).strip(),
            home_chat_id=str(data.get("home_chat_id", "")).strip(),
            allowed_users=list(data.get("allowed_users", [])),
            app_id=str(data.get("app_id", "")).strip(),
            app_secret=str(data.get("app_secret", "")).strip(),
        )

    def resolve_token(self) -> str:
        """解析 token，支持 ${ENV_VAR} 语法。"""
        return _resolve_env_vars(self.token)

    def resolve_app_secret(self) -> str:
        """解析 app_secret，支持 ${ENV_VAR} 语法。"""
        return _resolve_env_vars(self.app_secret)

    def is_configured(self) -> bool:
        """检查频道是否已配置（有有效凭证）。"""
        if self.platform == "weixin":
            return bool(self.account_id) and bool(self.resolve_token())
        if self.platform in ("feishu", "dingtalk"):
            return bool(self.app_id) and bool(self.resolve_app_secret())
        return bool(self.resolve_token())


class ChannelConfig:
    """频道配置管理器 — 读写 channels.toml。"""

    _FILE_NAME = "channels.toml"
    _LOCK_SUFFIX = ".lock"

    def __init__(self, user_id: str, workspace_root: Path | None = None):
        self.user_id = user_id
        self.workspace_root = Path(workspace_root or WORKSPACE_DIR)
        self._config_path = self._resolve_config_path()
        self._channels: dict[str, ChannelEntry] = {}
        self._loaded_mtime_ns: int | None = None
        self._loaded_size: int | None = None
        self._load()

    def _resolve_config_path(self) -> Path:
        """解析配置文件路径：{workspace}/{user_id}/global_workspace/.aiasys/channels.toml"""
        return self.workspace_root / self.user_id / "global_workspace" / ".aiasys" / self._FILE_NAME

    def _load(self) -> None:
        """从 TOML 加载配置。"""
        sys_path = as_system_path(str(self._config_path))
        if not Path(sys_path).exists():
            self._channels = {}
            self._loaded_mtime_ns = None
            self._loaded_size = None
            return

        try:
            raw = tomllib.load(Path(sys_path).open("rb"))
            stat = Path(sys_path).stat()
            self._loaded_mtime_ns = stat.st_mtime_ns
            self._loaded_size = stat.st_size
            if not isinstance(raw, dict):
                self._channels = {}
                return

            channels_data = raw.get("channels", {})
            if not isinstance(channels_data, dict):
                self._channels = {}
                return

            self._channels = {
                str(k): ChannelEntry.from_dict(str(k), v)
                for k, v in channels_data.items()
                if isinstance(v, dict)
            }
        except Exception as exc:
            logger.warning(
                "加载频道配置失败: user=%s path=%s error=%s",
                self.user_id,
                self._config_path,
                exc,
            )
            self._channels = {}
            self._loaded_mtime_ns = None
            self._loaded_size = None

    def _reload_if_changed(self) -> None:
        """重新加载被外部工具直接编辑过的 channels.toml。"""
        sys_path = as_system_path(str(self._config_path))
        if not Path(sys_path).exists():
            if self._loaded_mtime_ns is not None:
                self._load()
            return
        stat = Path(sys_path).stat()
        if stat.st_mtime_ns != self._loaded_mtime_ns or stat.st_size != self._loaded_size:
            self._load()

    def save(self) -> None:
        """保存配置到 TOML（带跨平台文件锁和原子替换）。"""
        sys_path = as_system_path(str(self._config_path))
        sys_parent = as_system_path(str(self._config_path.parent))
        Path(sys_parent).mkdir(parents=True, exist_ok=True)
        lock_path = as_system_path(str(self._config_path.with_suffix(self._LOCK_SUFFIX)))

        payload = {"channels": {k: v.to_dict() for k, v in self._channels.items()}}

        content = tomli_w.dumps(payload)
        with FileLock(lock_path):
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=sys_parent,
                delete=False,
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                tmp_file.write(content)
            tmp_path.replace(Path(sys_path))
            try:
                Path(sys_path).chmod(0o600)
            except OSError:
                logger.debug("设置 channels.toml 权限失败: path=%s", self._config_path)
            stat = Path(sys_path).stat()
            self._loaded_mtime_ns = stat.st_mtime_ns
            self._loaded_size = stat.st_size

    # ── CRUD ──

    def list_channels(self) -> list[ChannelEntry]:
        """返回所有频道列表。"""
        self._reload_if_changed()
        return list(self._channels.values())

    def get_channel(self, channel_id: str) -> ChannelEntry | None:
        """获取指定频道。"""
        self._reload_if_changed()
        return self._channels.get(channel_id)

    def set_channel(self, entry: ChannelEntry) -> None:
        """创建或更新频道。"""
        self._channels[entry.channel_id] = entry
        self.save()

    def remove_channel(self, channel_id: str) -> bool:
        """删除频道。"""
        if channel_id not in self._channels:
            return False
        del self._channels[channel_id]
        self.save()
        return True

    def set_enabled(self, channel_id: str, enabled: bool) -> bool:
        """启用/禁用频道。"""
        entry = self._channels.get(channel_id)
        if entry is None:
            return False
        entry.enabled = enabled
        self.save()
        return True

    # ── 查询 ──

    def get_enabled_channels(self) -> list[ChannelEntry]:
        """返回已启用的频道。"""
        self._reload_if_changed()
        return [c for c in self._channels.values() if c.enabled]

    def get_configured_channels(self) -> list[ChannelEntry]:
        """返回已配置的频道（有有效凭证）。"""
        self._reload_if_changed()
        return [c for c in self._channels.values() if c.is_configured()]

    def get_running_channels(self) -> list[ChannelEntry]:
        """返回应运行的频道（已启用且已配置）。"""
        self._reload_if_changed()
        return [c for c in self._channels.values() if c.enabled and c.is_configured()]


# ── 模块级缓存 ──

_CONFIG_CACHE: dict[tuple[str, str], ChannelConfig] = {}


def get_channel_config(user_id: str, workspace_root: Path | None = None) -> ChannelConfig:
    """获取指定用户的频道配置（带缓存）。"""
    root = str(Path(workspace_root or WORKSPACE_DIR))
    cache_key = (root, user_id)
    cfg = _CONFIG_CACHE.get(cache_key)
    if cfg is None:
        cfg = ChannelConfig(user_id, workspace_root=Path(root))
        _CONFIG_CACHE[cache_key] = cfg
    else:
        cfg._reload_if_changed()
    return cfg


def invalidate_channel_config(user_id: str, workspace_root: Path | None = None) -> None:
    """使指定用户的配置缓存失效。"""
    if workspace_root is None:
        for key in [key for key in _CONFIG_CACHE if key[1] == user_id]:
            _CONFIG_CACHE.pop(key, None)
        return
    _CONFIG_CACHE.pop((str(Path(workspace_root)), user_id), None)


# ── 辅助函数 ──


def _resolve_env_vars(value: str) -> str:
    """解析字符串中的 ${ENV_VAR} 引用。"""
    match = re.match(r"^\$\{([^}]+)\}$", value)
    if match:
        return os.environ.get(match.group(1), value)
    return value
