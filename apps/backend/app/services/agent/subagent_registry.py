"""
子 Agent 运行时注册表。

在内存中维护当前活跃的子 Agent session 映射，用于：
- 停止子 Agent（调用 session.cancel()）
- 查询子 Agent 是否仍在运行
- Host cancel 时级联取消所有子 Agent

注意：这只是一个轻量级运行时注册表，不持久化。
子 Agent 的持久化状态由 SubAgentStorage 和 SubAgentTrackingService 负责。
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.agent.runtime_backends.aiasys.session import AiasysRuntimeSession

logger = logging.getLogger(__name__)


class SubAgentRegistry:
    """子 Agent 运行时注册表（进程内单例）。"""

    def __init__(self) -> None:
        # agent_id -> AiasysRuntimeSession
        self._sessions: dict[str, "AiasysRuntimeSession"] = {}
        self._host_session_ids: dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def try_register(
        self,
        agent_id: str,
        session: "AiasysRuntimeSession",
        *,
        host_session_id: str | None = None,
        max_threads: int | None = None,
    ) -> bool:
        """原子地检查并发限制并注册子 Agent session。

        如果指定了 max_threads 且当前并发数已达到上限，则返回 False 且不注册。
        否则注册并返回 True。
        """
        async with self._lock:
            if host_session_id and max_threads is not None and max_threads > 0:
                active_count = sum(
                    1
                    for aid in self._sessions
                    if self._host_session_ids.get(aid) == host_session_id
                )
                if active_count >= max_threads:
                    logger.warning(
                        "SubAgent 并发数超限: host=%s, active=%d, max=%d",
                        host_session_id,
                        active_count,
                        max_threads,
                    )
                    return False
            self._sessions[agent_id] = session
            if host_session_id:
                self._host_session_ids[agent_id] = host_session_id
            else:
                self._host_session_ids.pop(agent_id, None)
            logger.debug("SubAgent registered: agent_id=%s", agent_id)
            return True

    async def register(
        self,
        agent_id: str,
        session: "AiasysRuntimeSession",
        *,
        host_session_id: str | None = None,
    ) -> None:
        """注册一个活跃子 Agent session（无并发检查，已被 try_register 替代）。"""
        async with self._lock:
            self._sessions[agent_id] = session
            if host_session_id:
                self._host_session_ids[agent_id] = host_session_id
            else:
                self._host_session_ids.pop(agent_id, None)
            logger.debug("SubAgent registered: agent_id=%s", agent_id)

    def unregister(self, agent_id: str) -> None:
        """注销子 Agent session（运行结束后）。"""
        removed = self._sessions.pop(agent_id, None)
        self._host_session_ids.pop(agent_id, None)
        if removed is not None:
            logger.debug("SubAgent unregistered: agent_id=%s", agent_id)

    def get(self, agent_id: str) -> "AiasysRuntimeSession" | None:
        """获取活跃子 Agent session。"""
        return self._sessions.get(agent_id)

    def is_active(self, agent_id: str) -> bool:
        """检查子 Agent 是否仍在活跃列表中。"""
        return agent_id in self._sessions

    def cancel(self, agent_id: str) -> bool:
        """取消指定子 Agent。

        Returns:
            True 如果成功找到并取消了 session，False 如果 agent_id 不在注册表中。
        """
        session = self._sessions.get(agent_id)
        if session is None:
            logger.warning("尝试取消未注册的子 Agent: agent_id=%s", agent_id)
            return False
        try:
            session.cancel()
            logger.info("SubAgent cancelled via registry: agent_id=%s", agent_id)
            return True
        except Exception:
            logger.exception("取消子 Agent 失败: agent_id=%s", agent_id)
            return False

    def cancel_all(self) -> list[str]:
        """取消所有活跃子 Agent（Host session 取消时级联调用）。

        Returns:
            被成功取消的 agent_id 列表。
        """
        cancelled: list[str] = []
        for agent_id, session in list(self._sessions.items()):
            try:
                session.cancel()
                cancelled.append(agent_id)
                logger.info("级联取消子 Agent: agent_id=%s", agent_id)
            except Exception:
                logger.exception("级联取消子 Agent 失败: agent_id=%s", agent_id)
        return cancelled

    def cancel_all_for_host(self, host_session_id: str) -> list[str]:
        """取消指定 Host 会话下的所有活跃子 Agent。

        Returns:
            被成功取消的 agent_id 列表。
        """
        cancelled: list[str] = []
        for agent_id, session in list(self._sessions.items()):
            if self._host_session_ids.get(agent_id) == host_session_id:
                try:
                    session.cancel()
                    cancelled.append(agent_id)
                    logger.info("级联取消子 Agent: agent_id=%s", agent_id)
                except Exception:
                    logger.exception("级联取消子 Agent 失败: agent_id=%s", agent_id)
        return cancelled

    def list_active(self) -> list[str]:
        """列出所有活跃子 Agent ID。"""
        return list(self._sessions.keys())

    def count_active_for_host(self, host_session_id: str) -> int:
        """统计指定 Host 会话下仍在运行的子 Agent 数。"""
        if not host_session_id:
            return 0
        return sum(
            1
            for agent_id in self._sessions
            if self._host_session_ids.get(agent_id) == host_session_id
        )

    def clear(self) -> None:
        """清空注册表（仅用于测试或特殊清理场景）。"""
        self._sessions.clear()
        self._host_session_ids.clear()


# 全局单例
_subagent_registry: SubAgentRegistry | None = None


def get_subagent_registry() -> SubAgentRegistry:
    """获取全局子 Agent 注册表实例。"""
    global _subagent_registry
    if _subagent_registry is None:
        _subagent_registry = SubAgentRegistry()
    return _subagent_registry
