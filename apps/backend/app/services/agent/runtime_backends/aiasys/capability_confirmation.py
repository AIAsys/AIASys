"""CapabilityConfirmationManager — 会话级能力确认管理器。

借鉴 kimi-cli ApprovalRuntime 的 asyncio.Future 机制，适配 AIASys 的 SSE + REST 架构。
每个 AiasysRuntimeSession 持有一个 manager 实例。

设计要点：
- 会话级自动批准按 pattern_key 记忆（如 "shell_command" / "global_write"），
  而非按工具名记忆。用户批准一次 Shell 命令不会自动放行所有 Shell 调用，
  但会记住同一 pattern 的审批决策。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class CapabilityConfirmationRecord:
    """单个能力确认请求的记录。"""

    tool_call_id: str
    tool_name: str
    arguments: dict[str, Any]
    prompt: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: str = "pending"  # pending | approved | denied | timeout | cancelled
    feedback: str = ""
    subagent_name: str | None = None
    agent_id: str | None = None
    pattern_key: str | None = None
    # Future 用于唤醒等待中的协程；不序列化
    _future: asyncio.Future | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """返回可序列化的字典（供 API 响应使用）。"""
        return {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "prompt": self.prompt,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "feedback": self.feedback,
            "subagent_name": self.subagent_name,
            "agent_id": self.agent_id,
            "pattern_key": self.pattern_key,
        }


class CapabilityConfirmationManager:
    """管理会话级的能力确认请求。

    工具调用在需要审批时通过 ``wait_for_confirmation()`` 阻塞，
    用户通过 REST API 调用 ``resolve()`` 恢复执行。

    设计要点（对标 kimi-cli ApprovalRuntime）：
    - 每个 Session 一个 manager，生命周期与 Session 绑定
    - 使用 asyncio.Future 作为暂停原语，不轮询
    - 支持会话级自动批准（approve_for_session），按 pattern_key 记忆
    - Session 关闭时自动取消所有 pending 请求
    """

    def __init__(self) -> None:
        self._pending: dict[str, CapabilityConfirmationRecord] = {}
        # 按 pattern_key 记忆（如 "shell_command" / "global_write"），非工具名
        self._session_auto_approved: set[str] = set()
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 自动批准
    # ------------------------------------------------------------------

    def is_auto_approved(self, pattern_key: str | None) -> bool:
        """检查指定 pattern 是否已在本会话自动批准。"""
        if pattern_key is None:
            return False
        return pattern_key in self._session_auto_approved

    def add_auto_approved(self, pattern_key: str | None) -> None:
        """将 pattern 加入本会话自动批准列表。"""
        if pattern_key:
            self._session_auto_approved.add(pattern_key)
            logger.info("Pattern %s 已加入本会话自动批准列表", pattern_key)

    # ------------------------------------------------------------------
    # 核心：请求确认并阻塞等待
    # ------------------------------------------------------------------

    async def wait_for_confirmation(
        self,
        tool_call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        prompt: str,
        pattern_key: str | None = None,
        subagent_name: str | None = None,
        agent_id: str | None = None,
        timeout: float = 300.0,
    ) -> tuple[bool, str]:
        """请求确认并阻塞等待用户响应。

        Args:
            tool_call_id: OpenAI tool call id
            tool_name: 工具名称
            arguments: 工具参数
            prompt: 展示给用户的确认提示文案
            pattern_key: 用于会话级自动批准的 pattern key
            subagent_name: 子 Agent 名称（如果有）
            agent_id: 子 Agent ID（如果有）
            timeout: 等待超时秒数，默认 5 分钟

        Returns:
            (approved, feedback) — approved 为 True 表示用户允许执行，
            feedback 为用户拒绝时填写的反馈文案或超时/取消原因
        """
        # 1. 检查会话级自动批准（pattern_key 为空时回退到 tool_name）
        check_key = pattern_key or tool_name
        if self.is_auto_approved(check_key):
            logger.debug("Pattern %s 已在本会话自动批准", check_key)
            return True, ""

        async with self._lock:
            # 重连场景：同 tool_call_id 已存在旧记录，先清理
            old = self._pending.pop(tool_call_id, None)
            if old and old._future and not old._future.done():
                old._future.set_result((False, "被新请求覆盖"))

            future: asyncio.Future = asyncio.get_running_loop().create_future()
            record = CapabilityConfirmationRecord(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=arguments,
                prompt=prompt,
                _future=future,
                pattern_key=pattern_key,
                subagent_name=subagent_name,
                agent_id=agent_id,
            )
            self._pending[tool_call_id] = record

        try:
            approved, feedback = await asyncio.wait_for(future, timeout=timeout)
            async with self._lock:
                if tool_call_id in self._pending:
                    self._pending[tool_call_id].status = "approved" if approved else "denied"
                    self._pending[tool_call_id].feedback = feedback
            return approved, feedback

        except asyncio.TimeoutError:
            logger.warning(
                "能力确认超时: tool_call_id=%s tool=%s timeout=%.0fs",
                tool_call_id,
                tool_name,
                timeout,
            )
            async with self._lock:
                if tool_call_id in self._pending:
                    self._pending[tool_call_id].status = "timeout"
            return False, "审批超时，操作已取消"

        finally:
            # 清理 future（保留记录供查询）
            async with self._lock:
                if tool_call_id in self._pending:
                    self._pending[tool_call_id]._future = None

    # ------------------------------------------------------------------
    # 用户通过 API 确认 / 拒绝
    # ------------------------------------------------------------------

    def resolve(
        self,
        tool_call_id: str,
        approved: bool,
        feedback: str = "",
        scope: str = "once",
    ) -> bool:
        """用户通过 REST API 确认或拒绝请求。

        Args:
            tool_call_id: 要处理的 tool call id
            approved: True 表示允许，False 表示拒绝
            feedback: 用户拒绝时填写的反馈文案
            scope: "once" 只批准这一次，"session" 记住到本会话自动批准列表

        Returns:
            是否成功找到并处理了 pending 请求
        """
        record = self._pending.get(tool_call_id)
        if record is None:
            logger.warning("未找到待确认请求: tool_call_id=%s", tool_call_id)
            return False

        if record._future is None or record._future.done():
            logger.warning("请求已处理或已超时: tool_call_id=%s status=%s", tool_call_id, record.status)
            return False

        record._future.set_result((approved, feedback))

        if approved and scope == "session" and record.pattern_key:
            self.add_auto_approved(record.pattern_key)

        return True

    # ------------------------------------------------------------------
    # 查询 & 清理
    # ------------------------------------------------------------------

    def list_pending(self) -> list[CapabilityConfirmationRecord]:
        """列出所有 pending 状态的记录（供重连时恢复）。"""
        return [r for r in self._pending.values() if r.status == "pending"]

    def cancel_all(self, reason: str = "会话结束") -> None:
        """取消所有 pending 请求（Session 关闭时调用）。"""
        cancelled_count = 0
        for _tool_call_id, record in list(self._pending.items()):
            if record.status == "pending" and record._future and not record._future.done():
                record._future.set_result((False, reason))
                record.status = "cancelled"
                record.feedback = reason
                cancelled_count += 1
        logger.info("已取消 %d 个 pending 能力确认请求: %s", cancelled_count, reason)
