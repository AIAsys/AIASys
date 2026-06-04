"""
会话控制 Mixin

负责中断、停止、清除和压缩会话
"""

import asyncio
import contextlib
import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from app.services.agent.mixins.environment import resolve_merged_env_vars_for_session
from app.services.agent.utils import get_session_key
from app.services.runtime.runtime_execution import resolve_runtime_execution_plan
from app.services.workspace_registry import get_workspace_registry_service

if TYPE_CHECKING:
    from app.services.agent import AgentService

logger = logging.getLogger(__name__)


def _log_task_exception(task: asyncio.Task) -> None:
    with contextlib.suppress(asyncio.CancelledError):
        exc = task.exception()
        if exc is not None:
            logger.error("后台任务异常: %s", exc, exc_info=True)


_TERMINAL_SUBAGENT_STATUSES = {"completed", "failed", "cancelled", "killed", "idle"}


def _normalize_subagent_status(status: str | None) -> str:
    normalized = (status or "").strip().lower()
    if normalized == "interrupted":
        return "cancelled"
    if normalized == "finished":
        return "completed"
    return normalized


def _find_live_background_subagent_task(
    runtime_session: object,
    agent_id: str,
):
    cancel_subagent = getattr(runtime_session, "cancel_subagent", None)
    if callable(cancel_subagent):
        try:
            return bool(cancel_subagent(agent_id))
        except Exception:
            logger.exception("停止后台协作节点任务失败: agent_id=%s", agent_id)
            return False

    background_manager = getattr(runtime_session, "background_tasks", None)
    if background_manager is None:
        return False
    if not hasattr(background_manager, "store") or not hasattr(background_manager, "kill"):
        return False

    try:
        for view in background_manager.store.list_views():
            spec = getattr(view, "spec", None)
            runtime = getattr(view, "runtime", None)
            kind_payload = getattr(spec, "kind_payload", None) or {}
            if getattr(spec, "kind", None) != "agent":
                continue
            if kind_payload.get("agent_id") != agent_id:
                continue
            if getattr(runtime, "status", None) in {"completed", "failed", "killed", "lost"}:
                continue
            task_id = getattr(spec, "id", None)
            if not isinstance(task_id, str) or not task_id:
                return False
            background_manager.kill(
                task_id,
                reason=f"Stopped by AIASys subagent control: {agent_id}",
            )
            return True
    except Exception:
        logger.exception("扫描后台协作节点任务失败: agent_id=%s", agent_id)
    return False


def _build_subagent_retry_prompt(
    *,
    agent_id: str,
    description: str,
    status: str,
    prompt_excerpt: str | None,
    output_excerpt: str | None,
) -> str:
    lines = [
        "继续接手一个未完成的协作节点任务，并由主控负责兜底。",
        "",
        "要求：",
        "1. 不要把“协作节点已经尝试过”当成任务完成。",
        "2. 先判断原任务是否已被真正完成；如果没有，主控必须负责补齐。",
        "3. 你可以自己补做关键步骤，也可以重新派发新的协作节点，但必须对最终结果负责。",
        "4. 如果证据不足以继续，就明确停在人类 gate，不要空转。",
        "5. 如果已经足够继续主线，就继续推进，不要只停在复盘说明。",
        "",
        "当前协作节点信息：",
        f"- 协作节点 ID: {agent_id}",
        f"- 协作节点描述: {description or '未记录'}",
        f"- 上次状态: {status or '未记录'}",
    ]

    if prompt_excerpt:
        lines.extend(
            [
                "",
                "该协作节点上次收到的任务指令摘要：",
                prompt_excerpt,
            ]
        )

    if output_excerpt:
        lines.extend(
            [
                "",
                "该协作节点上次输出摘要：",
                output_excerpt,
            ]
        )

    return "\n".join(lines)


async def _run_retry_control_turn(
    agent_service: "AgentService",
    *,
    prompt: str,
    user_id: str,
    session_id: str,
) -> None:
    try:
        await agent_service.execute(
            prompt=prompt,
            user_id=user_id,
            session_id=session_id,
        )
    except Exception:
        logger.exception(
            "主控补救回合执行失败: user=%s session=%s",
            user_id,
            session_id,
        )


class ControlMixin:
    """会话控制功能"""

    async def interrupt_session(
        self: "AgentService",
        user_id: str,
        session_id: str,
        *,
        remove_runtime_instance: bool = True,
    ):
        """中断当前推理流，并按需清理会话级资源。"""
        session_key = get_session_key(user_id, session_id)
        # 不要通过 asyncio.Lock 阻塞，因为 execute_stream 正在持有该锁
        session = self._active_sessions.get(session_key)
        if session:
            logger.info(f"正在中断会话: {session_key}")
            try:
                if hasattr(session, "cancel"):
                    # 这是一个同步方法，调用后会令内部 prompt 尽快进入取消路径。
                    session.cancel()
            except Exception as e:
                logger.error(f"中断会话出错: {e}")
        else:
            logger.info(f"未找到活跃的会话进行中断: {session_key}")

        # 级联取消所有活跃子 Agent
        try:
            from app.services.agent.subagent_registry import get_subagent_registry

            cancelled = get_subagent_registry().cancel_all_for_host(session_key)
            if cancelled:
                logger.info(
                    "级联取消子 Agent: session=%s, count=%d, agents=%s",
                    session_key,
                    len(cancelled),
                    cancelled,
                )
        except Exception:
            logger.warning("级联取消子 Agent 失败", exc_info=True)

        # 异步触发会话资源清理，不阻塞 cancel 调用返回
        _cleanup_task = asyncio.create_task(
            self._cleanup_session_resources(
                user_id=user_id,
                session_id=session_id,
                session_key=session_key,
                remove_runtime_instance=remove_runtime_instance,
            )
        )
        _cleanup_task.add_done_callback(_log_task_exception)

    async def stop_session(self: "AgentService", user_id: str, session_id: str):
        """强制停止会话并中断当前的推理流，同时清理后台任务。"""
        session_key = get_session_key(user_id, session_id)
        # 先停止可能存在的后台任务
        await self.stop_background_session(session_key)
        await self.interrupt_session(
            user_id=user_id,
            session_id=session_id,
            remove_runtime_instance=True,
        )

    async def stop_subagent_execution(
        self: "AgentService",
        user_id: str,
        session_id: str,
        agent_id: str,
        *,
        subagent_status: str | None = None,
    ) -> dict[str, str]:
        """停止指定协作节点。

        当前真实能力分三层：
        1. 若命中原生 SubAgentRegistry，直接 cancel 子 Agent session。
        2. 若命中活跃的运行时后台子节点任务，则直接 kill 后台任务。
        3. 若是前台子节点，则只能通过取消当前 host session 来中断。
        """
        normalized_status = _normalize_subagent_status(subagent_status)

        # 第 0 层：原生 SubAgentRegistry 直接取消
        try:
            from app.services.agent.subagent_registry import get_subagent_registry

            registry = get_subagent_registry()
            if registry.is_active(agent_id):
                cancelled = registry.cancel(agent_id)
                if cancelled:
                    return {
                        "status": "accepted",
                        "mode": "native_subagent_cancelled",
                        "detail": "已通过原生运行时注册表取消子 Agent。",
                    }
        except Exception:
            logger.warning("尝试 SubAgentRegistry 取消失败", exc_info=True)

        session_key = get_session_key(user_id, session_id)
        runtime_session = self._active_sessions.get(session_key)

        if runtime_session is not None:
            background_task_killed = _find_live_background_subagent_task(
                runtime_session,
                agent_id,
            )
            if background_task_killed:
                return {
                    "status": "accepted",
                    "mode": "background_task_killed",
                    "detail": ("已停止后台协作节点任务。"),
                }

        if normalized_status in {"running", "running_foreground"}:
            if runtime_session is None:
                raise RuntimeError(
                    "当前协作节点看起来仍在运行，但主控运行句柄已不可用，无法安全中断。"
                )
            await self.stop_session(user_id=user_id, session_id=session_id)
            return {
                "status": "accepted",
                "mode": "host_session_cancelled",
                "detail": (
                    "前台协作节点无法单独停止，已通过取消当前主控回合来中断。"
                    "停止前台协作节点会中断主控的所有当前操作。"
                ),
            }

        if normalized_status == "running_background":
            raise RuntimeError("后台协作节点当前不再挂在活跃主控句柄上，暂时无法安全中断。")

        if normalized_status in _TERMINAL_SUBAGENT_STATUSES:
            return {
                "status": "ignored",
                "mode": "already_terminal",
                "detail": "该协作节点已处于终态，无需再次停止。",
            }

        raise RuntimeError("当前协作节点状态不支持停止。")

    async def retry_subagent_execution(
        self: "AgentService",
        user_id: str,
        session_id: str,
        agent_id: str,
        *,
        description: str,
        subagent_status: str | None = None,
        prompt_excerpt: str | None = None,
        output_excerpt: str | None = None,
    ) -> dict[str, str]:
        """通过新的主控补救回合重试协作节点任务。"""
        normalized_status = _normalize_subagent_status(subagent_status)
        if normalized_status not in {"failed", "cancelled", "killed"}:
            raise RuntimeError("只有失败、取消或已杀掉的协作节点才能重试。")

        session_key = get_session_key(user_id, session_id)
        session_lock = await self._get_session_lock(session_key)
        async with session_lock:
            if self._active_sessions.get(session_key) is not None:
                raise RuntimeError("当前主控仍在运行，请先结束当前回合再发起协作节点重试。")

            prompt = _build_subagent_retry_prompt(
                agent_id=agent_id,
                description=description,
                status=normalized_status,
                prompt_excerpt=prompt_excerpt,
                output_excerpt=output_excerpt,
            )
            task = asyncio.create_task(
                _run_retry_control_turn(
                    self,
                    prompt=prompt,
                    user_id=user_id,
                    session_id=session_id,
                )
            )
            task.add_done_callback(_log_task_exception)

        return {
            "status": "accepted",
            "mode": "host_recovery_turn_queued",
            "detail": "已排队一个新的主控补救回合，主控将负责接手并判断是否重新派发协作节点。",
        }

    async def compact_session_context(
        self: "AgentService", user_id: str, session_id: str, instruction: str = ""
    ) -> None:
        """调用底层 runtime session 的 `/compact` 压缩上下文，可选自定义指令。"""
        config = self._get_config(None, user_id, None)
        session_key = get_session_key(user_id, session_id)
        workspace_registry = get_workspace_registry_service()
        session_root = workspace_registry.get_session_dir(user_id, session_id)
        logical_workspace_root = workspace_registry.get_logical_workspace_root(
            user_id,
            session_id,
        )
        resolved_env_id = self._resolve_env_id_for_session(user_id, session_id)
        resolved_sandbox_mode = self._resolve_sandbox_mode_for_session(
            user_id,
            session_id,
        )
        resolved_code_timeout = self._resolve_code_timeout_for_session(user_id, session_id)
        resolved_env_vars = resolve_merged_env_vars_for_session(user_id, logical_workspace_root)
        frozen_runtime_plan = resolve_runtime_execution_plan(
            workspace=logical_workspace_root,
            env_id=resolved_env_id,
        )
        frozen_runtime_plan = replace(
            frozen_runtime_plan,
            env_vars=resolved_env_vars,
            frozen=True,
        )
        tokens = self._set_session_context(
            user_id=user_id,
            session_id=session_id,
            workspace_path=logical_workspace_root,
            session_root=session_root,
            env_id=resolved_env_id,
            code_timeout=resolved_code_timeout,
            runtime_env_vars=resolved_env_vars,
            runtime_execution_plan=frozen_runtime_plan,
        )

        try:
            session_lock = await self._get_session_lock(session_key)
            async with session_lock:
                session = self._active_sessions.get(session_key)
                if session is None:
                    session = await self._get_or_create_session(
                        config=config,
                        user_id=user_id,
                        session_id=session_id,
                        sandbox_mode=resolved_sandbox_mode,
                    )
                    self._active_sessions[session_key] = session

                # 构建 compact 命令，支持自定义指令
                compact_cmd = "/compact"
                if instruction and instruction.strip():
                    compact_cmd += f" {instruction.strip()}"

                async for _ in session.prompt(compact_cmd, merge_wire_messages=True):
                    pass
        finally:
            self._reset_session_context(tokens)
