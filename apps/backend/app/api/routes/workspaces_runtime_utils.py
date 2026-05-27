"""
任务工作区与对话主接口
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def _is_runtime_busy(user_id: str, session_id: str) -> bool:
    from app.services.agent import agent_service

    session_key = f"{user_id}/{session_id}"
    session_lock = getattr(agent_service, "_session_locks", {}).get(session_key)
    return bool(session_lock and session_lock.locked())


async def _wait_for_session_stop(
    user_id: str,
    session_id: str,
    *,
    timeout_s: float = 5.0,
) -> bool:
    from app.services.agent import agent_service

    session_key = f"{user_id}/{session_id}"
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        runtime_session = getattr(agent_service, "_active_sessions", {}).get(session_key)
        session_lock = getattr(agent_service, "_session_locks", {}).get(session_key)
        if runtime_session is None and not (session_lock and session_lock.locked()):
            return True
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.05)


def _resolve_runtime_control_capability(
    runtime_summary: dict[str, object],
) -> tuple[bool, bool, str | None]:
    runtime_kind = runtime_summary.get("runtime_kind")
    if runtime_kind not in ("local_ipython", "uv"):
        return False, False, "当前会话不是本地主线运行态。"

    if bool(runtime_summary.get("runtime_busy")):
        return False, False, "当前会话正在执行，暂时不能切换运行态。"

    if bool(runtime_summary.get("kernel_active")):
        return False, True, None

    return True, False, None
