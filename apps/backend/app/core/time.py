"""时间辅助函数。

统一提供 UTC 时间，避免继续使用已废弃的 ``datetime.utcnow()``。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """返回带 UTC 时区的当前时间。"""
    return datetime.now(UTC)


def utc_now_naive() -> datetime:
    """返回不带时区信息的 UTC 时间。

    主要用于仍以 naive datetime 存储的数据库字段，保持现有存储兼容。
    """
    return utc_now().replace(tzinfo=None)
