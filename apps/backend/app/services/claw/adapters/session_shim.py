"""Session-related types and helpers for Claw platform adapters.

Extracted from vendored hermes_agent/gateway/session.py.
Only includes types used by BasePlatformAdapter.
"""

from dataclasses import dataclass
from typing import Optional

from app.services.claw.adapters.models import Platform


@dataclass
class SessionSource:
    """Describes where a message originated from."""

    platform: Platform
    chat_id: str
    chat_name: Optional[str] = None
    chat_type: str = "dm"
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    thread_id: Optional[str] = None
    chat_topic: Optional[str] = None
    user_id_alt: Optional[str] = None
    chat_id_alt: Optional[str] = None


def build_session_key(
    source: SessionSource,
    group_sessions_per_user: bool = True,
    thread_sessions_per_user: bool = False,
) -> str:
    """Build a deterministic session key from a message source."""
    parts = [source.platform.value]

    if source.chat_type == "dm":
        if source.chat_id:
            parts.append(source.chat_id)
        elif source.thread_id:
            parts.append(source.thread_id)
        if source.thread_id and source.chat_id:
            parts.append(source.thread_id)
    else:
        parts.append(source.chat_id)
        if group_sessions_per_user and source.user_id:
            parts.append(source.user_id)
        if source.thread_id:
            parts.append(source.thread_id)

    return ":".join(parts)
