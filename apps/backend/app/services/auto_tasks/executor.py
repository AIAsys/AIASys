"""
自动任务执行器。

执行器支持两种会话策略：
- 绑定会话：向已有 session 注入 prompt
- 每次新建会话：在工作区里创建一条普通会话后执行
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from app.services.auto_tasks.models import (
    AutoTask,
    AutoTaskTriggerType,
    TaskCategory,
    TaskStatus,
)
from app.services.auto_tasks.policy import (
    ensure_auto_task_allowed_for_workspace,
)
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)


async def run_auto_task(
    task: AutoTask,
    *,
    origin: str = "auto_task_loop",
    manual_run: bool = False,
) -> dict:
    """执行单个自动任务。"""
    workspace_registry = get_workspace_registry_service()
    ensure_auto_task_allowed_for_workspace(
        user_id=task.user_id,
        workspace_id=task.workspace_id,
        workspace_registry=workspace_registry,
    )

    if task.bind_session_id:
        return await _execute_loop_mode(task, origin, manual_run)
    else:
        return await _execute_standalone_mode(task, origin, manual_run)


async def _execute_loop_mode(
    task: AutoTask,
    origin: str,
    manual_run: bool,
) -> dict:
    """Loop/continuous 模式：往绑定的 session 注入 prompt，同一上下文中执行。"""
    from app.services.agent import agent_service

    try:
        workspace_registry = get_workspace_registry_service()
        session_root = workspace_registry.get_session_dir(task.user_id, task.bind_session_id)
        if not session_root.exists():
            logger.warning(
                "绑定 Session 不存在，跳过执行: session=%s task=%s",
                task.bind_session_id,
                task.task_id,
            )
            return {
                "mode": "loop",
                "session_id": task.bind_session_id,
                "executed": False,
                "execution_reason": "bound_session_missing",
            }

        prompt = _build_prompt(task)
        if task.task_category == TaskCategory.continuous:
            _prepare_auto_task_signal(task, task.bind_session_id)

        logger.info(
            "Loop/continuous 模式执行: task=%s session=%s workspace=%s origin=%s manual=%s category=%s",
            task.task_id,
            task.bind_session_id,
            task.workspace_id,
            origin,
            manual_run,
            task.task_category.value,
        )

        result = await agent_service.execute(
            prompt=prompt,
            user_id=task.user_id,
            session_id=task.bind_session_id,
            model=task.model,
            model_id=task.model_id,
            sandbox_mode=task.sandbox_mode,
        )

        response = {
            "mode": "loop",
            "session_id": task.bind_session_id,
            "executed": True,
            "result": result[:500] if result else "",
        }

        if task.task_category == TaskCategory.continuous:
            _sync_auto_task_stop_signal(task, task.bind_session_id)
            _check_and_update_budget(task, task.bind_session_id)

        return response
    except Exception as exc:
        logger.error(
            "Loop/continuous 模式执行失败: task=%s session=%s error=%s",
            task.task_id,
            task.bind_session_id,
            exc,
            exc_info=True,
        )
        raise


def _build_prompt(task: AutoTask) -> str:
    """构建执行 prompt。

    continuous 模式允许用户补充续推说明，但完成审计和停止信号规则始终由系统追加，
    避免自定义提示词覆盖 `auto_task_signal` 的退出闭环。
    """
    if task.task_category != TaskCategory.continuous:
        return task.prompt

    custom = getattr(task, "continuation_prompt", None)
    if custom:
        return _continuous_prompt_with_system_rules(task, custom)

    return _default_continuation_prompt(task)


def _default_continuation_prompt(task: AutoTask) -> str:
    """continuous 模式的默认推进 prompt。"""
    return _continuous_prompt_with_system_rules(
        task,
        "继续推进当前目标，避免重复已完成的工作，选择下一个具体行动。",
    )


def _continuous_prompt_with_system_rules(task: AutoTask, continuation_instruction: str) -> str:
    """组合 continuous 单轮执行提示词和系统级停止规则。"""
    return (
        f"目标: {task.prompt}\n\n"
        f"本轮推进要求:\n{continuation_instruction.strip()}\n\n"
        f"完成审计（Completion Audit）——在标记目标完成前必须执行:\n"
        f"1. 把目标拆解为具体的、可验证的交付物清单\n"
        f"2. 逐条检查每个交付物是否有真实证据（文件路径、命令输出、测试结果）\n"
        f"3. 不允许用代理信号替代完成：测试通过、代码编译成功、清单完整都只是中间证据，"
        f"   必须覆盖目标描述的每一条需求\n"
        f"4. 如果有待办事项（todo）列表，确认所有条目都已完成且有交付物证据\n"
        f"5. 任何不确定是否满足的需求，都视为未完成\n\n"
        f"规则:\n"
        f'- 如果自动任务目标已完全达成，调用 auto_task_signal(action="complete") 标记完成，'
        f"  随后停止工作，不再继续。\n"
        f'- 如果自动任务无法完成或需要用户介入，调用 auto_task_signal(action="pause")。\n'
        f"- 只有目标仍 active 且确实还有未完成的实质性工作时，才继续执行。"
    )


def _read_session_metadata(user_id: str, session_id: str):
    from app.models.session import SessionMetadata

    registry = get_workspace_registry_service()
    session_dir = registry.get_session_dir(user_id, session_id)
    meta_path = session_dir / "metadata.json"
    if not meta_path.exists():
        return None, meta_path
    data = json.loads(meta_path.read_text(encoding="utf-8"))
    return SessionMetadata(**data), meta_path


def _write_session_metadata(meta_path: Path, metadata) -> None:
    meta_path.write_text(
        metadata.model_dump_json(indent=2),
        encoding="utf-8",
    )


def _prepare_auto_task_signal(task: AutoTask, session_id: str | None) -> None:
    """为本轮 continuous 自动任务写入完成信号占位。"""
    if not session_id:
        return
    try:
        from app.models.session import AutoTaskSignal

        metadata, meta_path = _read_session_metadata(task.user_id, session_id)
        if metadata is None:
            return
        metadata.auto_task_signal = AutoTaskSignal(
            auto_task_id=task.task_id,
            status="active",
            created_at=datetime.now().isoformat(),
        )
        _write_session_metadata(meta_path, metadata)
    except Exception:
        logger.warning("准备 continuous 自动任务信号失败", exc_info=True)


def _sync_auto_task_stop_signal(task: AutoTask, session_id: str | None) -> None:
    """读取 auto_task_signal 工具写回的状态，将 completed/paused 同步到自动任务。"""
    if not session_id:
        return
    if not getattr(task, "stop_on_signal", True):
        return
    try:
        metadata, _meta_path = _read_session_metadata(task.user_id, session_id)
        if metadata is None or metadata.auto_task_signal is None:
            return
        signal = metadata.auto_task_signal
        if signal.auto_task_id != task.task_id:
            return
        if signal.status == "completed":
            task.status = TaskStatus.completed
            logger.info(
                "continuous 自动任务收到完成信号: task=%s session=%s",
                task.task_id,
                session_id,
            )
        elif signal.status == "paused":
            task.status = TaskStatus.paused
            logger.info(
                "continuous 自动任务收到暂停信号: task=%s session=%s",
                task.task_id,
                session_id,
            )
    except Exception:
        logger.warning("同步 continuous 自动任务信号失败", exc_info=True)


def _check_and_update_budget(task: AutoTask, session_id: str | None) -> None:
    """同步 session 级预算保护状态，耗尽时暂停 continuous 任务。"""
    if not session_id:
        return
    try:
        meta, _meta_path = _read_session_metadata(task.user_id, session_id)
        if meta is None:
            return
        if meta.budget and meta.budget.is_exhausted():
            task.status = TaskStatus.paused
            logger.info(
                "Session budget 耗尽，暂停 continuous 任务: task=%s session=%s",
                task.task_id,
                session_id,
            )
    except Exception:
        logger.debug("检查 session budget 失败", exc_info=True)


async def _execute_standalone_mode(
    task: AutoTask,
    origin: str,
    manual_run: bool,
) -> dict:
    """独立模式：新建 session 并执行。"""
    from app.services.agent import agent_service

    try:
        workspace_registry = get_workspace_registry_service()
        session_id = _create_workspace_session(task, workspace_registry)
        prompt = _build_prompt(task)
        if task.task_category == TaskCategory.continuous:
            _prepare_auto_task_signal(task, session_id)

        logger.info(
            "独立模式执行: task=%s workspace=%s new_session=%s origin=%s manual=%s",
            task.task_id,
            task.workspace_id,
            session_id,
            origin,
            manual_run,
        )

        result = await agent_service.execute(
            prompt=prompt,
            user_id=task.user_id,
            session_id=session_id,
            model=task.model,
            model_id=task.model_id,
            sandbox_mode=task.sandbox_mode,
        )

        if task.task_category == TaskCategory.continuous:
            _sync_auto_task_stop_signal(task, session_id)
            _check_and_update_budget(task, session_id)

        return {
            "mode": "standalone",
            "session_id": session_id,
            "executed": True,
            "result": result[:500] if result else "",
        }
    except Exception as exc:
        logger.error(
            "独立模式执行失败: task=%s workspace=%s error=%s",
            task.task_id,
            task.workspace_id,
            exc,
            exc_info=True,
        )
        raise


def _create_workspace_session(task: AutoTask, workspace_registry) -> str:
    """在目标工作区里创建自动任务会话，保证工作区索引和共享目录完整。"""
    session_id = str(uuid4())
    title = task.title.strip() if task.title else "自动任务会话"
    workspace_registry.create_conversation(
        user_id=task.user_id,
        workspace_id=task.workspace_id,
        conversation_id=session_id,
        title=title,
        sandbox_mode=task.sandbox_mode,
        source="auto_task",
        auto_task_id=task.task_id,
        make_current=False,
    )
    return session_id
