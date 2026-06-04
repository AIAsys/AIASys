"""
会话级上下文变量。

用于在一次请求/会话执行链路中传递 user/session/workspace/env 信息，
避免工具层依赖进程级全局状态。
"""

from __future__ import annotations

import contextvars
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_user_id", default=None
)
current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)
current_workspace: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "current_workspace", default=None
)
current_session_root: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "current_session_root", default=None
)
current_global_workspace: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "current_global_workspace", default=None
)
current_env_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_env_id", default=None
)
current_runtime_env_vars: contextvars.ContextVar[dict[str, str] | None] = contextvars.ContextVar(
    "current_runtime_env_vars", default=None
)
current_runtime_execution_plan: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "current_runtime_execution_plan", default=None
)
current_code_timeout: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_code_timeout", default=None
)
current_agent_config_snapshot: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "current_agent_config_snapshot", default=None
)


def resolve_current_code_timeout() -> int | None:
    """
    解析当前执行链路的 code timeout。

    优先读取 ContextVar；如果执行框架切换导致该值未透传，
    则回退到当前 workspace 的 metadata.json。
    """
    timeout = current_code_timeout.get()
    if timeout is not None:
        return timeout

    session_root = current_session_root.get() or current_workspace.get()
    if session_root is None:
        return None

    metadata_path = Path(session_root) / "metadata.json"
    if not metadata_path.exists():
        return None

    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("Failed to read session context from metadata", exc_info=True)
        return None

    raw_timeout = payload.get("code_timeout")
    return raw_timeout if isinstance(raw_timeout, int) else None
