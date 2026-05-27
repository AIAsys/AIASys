"""
AIASys 自动任务工具集。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.auto_tasks import (
    MIN_INTERVAL_SECONDS,
    AutoTask,
    AutoTaskStore,
    AutoTaskTriggerType,
    FirstRunPolicy,
    TaskCategory,
    TaskStatus,
)
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)


def _resolve_workspace(
    ctx: dict[str, Any],
) -> tuple[str, str] | tuple[None, None]:
    """从上下文中解析 user_id 和 workspace_id。"""
    user_id = str(ctx.get("user_id") or "").strip()
    session_id = str(ctx.get("session_id") or "").strip()
    if not user_id or not session_id:
        return None, None
    try:
        registry = get_workspace_registry_service()
        workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
        if workspace_id:
            return user_id, workspace_id
    except Exception:
        logger.warning("查找 workspace_id 失败", exc_info=True)
    return None, None


def _task_category_for_trigger(trigger_type: AutoTaskTriggerType) -> TaskCategory:
    if trigger_type == AutoTaskTriggerType.continuous:
        return TaskCategory.continuous
    return TaskCategory.scheduled


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return bool(value)


def _coerce_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _parse_first_run_policy(value: Any) -> FirstRunPolicy:
    return FirstRunPolicy(str(value or FirstRunPolicy.next_scheduled.value).strip())


def _parse_task_status(value: Any) -> TaskStatus:
    return TaskStatus(str(value or TaskStatus.active.value).strip())


def _validate_trigger_value(
    trigger_type: AutoTaskTriggerType,
    trigger_value: str,
) -> str | None:
    if trigger_type == AutoTaskTriggerType.continuous:
        return None
    if not trigger_value:
        return "非 continuous 自动任务必须提供 trigger_value"
    if trigger_type == AutoTaskTriggerType.interval:
        try:
            interval_seconds = int(trigger_value)
        except Exception:
            return "interval 的 trigger_value 必须是秒数"
        if interval_seconds < MIN_INTERVAL_SECONDS:
            return f"interval 最短支持 {MIN_INTERVAL_SECONDS} 秒"
    if trigger_type == AutoTaskTriggerType.cron:
        if len(trigger_value.split()) != 5:
            return "cron 的 trigger_value 必须是 5 段表达式"
    return None


def _refresh_next_run(task: AutoTask) -> None:
    from app.services.auto_tasks.engine import _calculate_next_run

    next_run = _calculate_next_run(task)
    task.next_run_at = next_run.isoformat() if next_run else None


class CreateAutoTask(AiasysTool):
    """创建当前工作区的新自动任务。"""

    name = "CreateAutoTask"
    description = (
        "在当前工作区创建一个新的自动任务。"
        "支持 continuous（连续执行）、once（单次执行）、interval（按秒间隔）、cron（cron 表达式）四种触发类型。"
        "支持 bind_session_id 将任务绑定到已有 session（同一上下文累积）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "trigger_type": {
                "type": "string",
                "enum": ["continuous", "once", "interval", "cron"],
                "description": "触发类型。continuous=连续执行，once=单次执行，interval=按秒间隔，cron=cron 表达式",
            },
            "trigger_value": {
                "type": "string",
                "description": "触发值。once 填 ISO 时间如 2026-05-01T12:00:00，interval 填秒数如 3600，cron 填表达式如 0 9 * * *",
            },
            "prompt": {
                "type": "string",
                "description": "任务指令，触发时作为 Agent 的输入提示词",
            },
            "title": {
                "type": "string",
                "description": "任务标题（可选）",
            },
            "bind_session_id": {
                "type": "string",
                "description": "绑定的 session ID（可选）。设置后每次触发在同一 session 上下文中执行，不设置则每次新建 session",
            },
            "continuation_prompt": {
                "type": "string",
                "description": "continuous 模式每轮追加的续推说明（可选）。系统会固定追加完成审计和 auto_task_signal 退出规则",
            },
            "max_continuations": {
                "type": "integer",
                "description": "continuous 模式最大触发次数，-1 表示不限制",
            },
            "first_run_policy": {
                "type": "string",
                "enum": ["immediate", "next_scheduled"],
                "description": "时间触发任务的首次执行策略。immediate=创建或启用后立即执行一轮，next_scheduled=等待第一个计划时间点。continuous 模式忽略该字段",
            },
            "stop_on_signal": {
                "type": "boolean",
                "description": "continuous 模式是否允许 Agent 通过 auto_task_signal 标记完成或暂停，默认 true",
            },
            "stop_on_consecutive_errors": {
                "type": "integer",
                "description": "连续错误达到多少次后禁用任务，默认 10",
            },
            "status": {
                "type": "string",
                "enum": ["active", "paused"],
                "description": "创建后的初始状态。active=立即进入触发队列，paused=只登记任务，确认后再恢复或立即运行",
            },
        },
        "required": ["trigger_type", "prompt"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        trigger_type_str = str(kwargs.get("trigger_type") or "").strip()
        trigger_value = str(kwargs.get("trigger_value") or "").strip()
        prompt = str(kwargs.get("prompt") or "").strip()
        title = str(kwargs.get("title") or "").strip()
        if not prompt:
            return ToolResult(content="prompt 不能为空", is_error=True)
        if trigger_type_str == "continuous" and not trigger_value:
            trigger_value = ""

        try:
            trigger_type = AutoTaskTriggerType(trigger_type_str)
        except ValueError:
            return ToolResult(
                content=f"无效的 trigger_type: {trigger_type_str}，可选值: continuous/once/interval/cron",
                is_error=True,
            )

        validation_error = _validate_trigger_value(trigger_type, trigger_value)
        if validation_error:
            return ToolResult(content=validation_error, is_error=True)

        user_id, workspace_id = _resolve_workspace(ctx)
        if not user_id or not workspace_id:
            return ToolResult(
                content="无法确定当前工作区，可能当前会话未绑定工作区",
                is_error=True,
            )

        try:
            max_continuations = _coerce_int(kwargs.get("max_continuations"), -1)
            stop_on_consecutive_errors = _coerce_int(
                kwargs.get("stop_on_consecutive_errors"),
                10,
            )
        except ValueError:
            return ToolResult(
                content="max_continuations 和 stop_on_consecutive_errors 必须是整数", is_error=True
            )
        if stop_on_consecutive_errors < 1:
            return ToolResult(content="stop_on_consecutive_errors 必须是正整数", is_error=True)

        try:
            first_run_policy = _parse_first_run_policy(kwargs.get("first_run_policy"))
        except ValueError:
            return ToolResult(
                content="first_run_policy 只支持 immediate / next_scheduled",
                is_error=True,
            )
        if trigger_type == AutoTaskTriggerType.continuous:
            first_run_policy = FirstRunPolicy.immediate

        try:
            status = _parse_task_status(kwargs.get("status"))
        except ValueError:
            return ToolResult(
                content="status 只支持 active / paused",
                is_error=True,
            )
        if status not in {TaskStatus.active, TaskStatus.paused}:
            return ToolResult(
                content="创建自动任务时 status 只支持 active / paused",
                is_error=True,
            )

        task = AutoTask(
            task_id=str(uuid4()),
            workspace_id=workspace_id,
            user_id=user_id,
            prompt=prompt,
            trigger_type=trigger_type,
            trigger_value=trigger_value,
            status=status,
            title=title or "自动任务",
            bind_session_id=(kwargs.get("bind_session_id") or "").strip() or None,
            continuation_prompt=(kwargs.get("continuation_prompt") or "").strip() or None,
            max_continuations=max_continuations,
            task_category=_task_category_for_trigger(trigger_type),
            first_run_policy=first_run_policy,
            stop_on_signal=_coerce_bool(kwargs.get("stop_on_signal"), True),
            stop_on_consecutive_errors=stop_on_consecutive_errors,
        )
        _refresh_next_run(task)
        AutoTaskStore.put_task(user_id, workspace_id, task)

        return ToolResult(
            content=json.dumps(
                {
                    "task_id": task.task_id,
                    "title": task.title,
                    "trigger_type": task.trigger_type.value,
                    "trigger_value": task.trigger_value,
                    "status": task.status.value,
                    "task_category": task.task_category.value,
                    "first_run_policy": task.first_run_policy.value,
                    "max_continuations": task.max_continuations,
                    "stop_on_signal": task.stop_on_signal,
                    "session_strategy": "bind_session" if task.bind_session_id else "new_each_time",
                    "message": "自动任务已创建",
                },
                ensure_ascii=False,
            )
        )


class ListAutoTasks(AiasysTool):
    """列出当前工作区的所有自动任务。"""

    name = "ListAutoTasks"
    description = "列出当前工作区的所有自动任务，包括任务 ID、标题、触发类型、状态和上次运行时间。"
    parameters = {
        "type": "object",
        "properties": {},
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        user_id, workspace_id = _resolve_workspace(ctx)
        if not user_id or not workspace_id:
            return ToolResult(
                content="无法确定当前工作区",
                is_error=True,
            )

        tasks = AutoTaskStore.list_tasks(user_id, workspace_id)
        return ToolResult(
            content=json.dumps(
                {
                    "tasks": [
                        {
                            "task_id": t.task_id,
                            "title": t.title,
                            "trigger_type": t.trigger_type.value,
                            "trigger_value": t.trigger_value,
                            "status": t.status.value,
                            "task_category": t.task_category.value,
                            "first_run_policy": t.first_run_policy.value,
                            "prompt": t.prompt,
                            "created_at": t.created_at,
                            "last_run_at": t.last_run_at,
                            "fired_count": t.fired_count,
                            "max_continuations": t.max_continuations,
                            "stop_on_signal": t.stop_on_signal,
                            "stop_on_consecutive_errors": t.stop_on_consecutive_errors,
                        }
                        for t in tasks
                    ],
                    "count": len(tasks),
                },
                ensure_ascii=False,
            )
        )


class UpdateAutoTask(AiasysTool):
    """更新已有自动任务的配置。"""

    name = "UpdateAutoTask"
    description = (
        "修改已有自动任务的触发配置、目标指令、续推设置或停止条件。" "至少提供一个需要更新的字段。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "要更新的任务 ID",
            },
            "trigger_type": {
                "type": "string",
                "enum": ["continuous", "once", "interval", "cron"],
                "description": "新的触发类型（可选）",
            },
            "trigger_value": {
                "type": "string",
                "description": "新的触发值（可选）",
            },
            "prompt": {
                "type": "string",
                "description": "新的任务指令（可选）",
            },
            "title": {
                "type": "string",
                "description": "新的任务标题（可选）",
            },
            "bind_session_id": {
                "type": "string",
                "description": "新的绑定 session ID（可选）。传空字符串解绑",
            },
            "continuation_prompt": {
                "type": "string",
                "description": "新的 continuous 续推说明（可选，传空字符串清除）",
            },
            "max_continuations": {
                "type": "integer",
                "description": "新的 continuous 最大触发次数（可选）",
            },
            "first_run_policy": {
                "type": "string",
                "enum": ["immediate", "next_scheduled"],
                "description": "新的首次执行策略（可选）。只影响 interval / cron 类型",
            },
            "stop_on_signal": {
                "type": "boolean",
                "description": "是否允许 Agent 主动标记完成或暂停（可选）",
            },
            "stop_on_consecutive_errors": {
                "type": "integer",
                "description": "连续错误禁用阈值（可选）",
            },
        },
        "required": ["task_id"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        task_id = str(kwargs.get("task_id") or "").strip()
        if not task_id:
            return ToolResult(content="需要 task_id 参数", is_error=True)

        user_id, workspace_id = _resolve_workspace(ctx)
        if not user_id or not workspace_id:
            return ToolResult(content="无法确定当前工作区", is_error=True)

        task = AutoTaskStore.get_task(user_id, workspace_id, task_id)
        if task is None:
            return ToolResult(content=f"任务 {task_id} 不存在", is_error=True)

        changed = False
        trigger_type_str = str(kwargs.get("trigger_type") or "").strip()
        if trigger_type_str:
            try:
                task.trigger_type = AutoTaskTriggerType(trigger_type_str)
                task.task_category = _task_category_for_trigger(task.trigger_type)
                changed = True
            except ValueError:
                return ToolResult(
                    content=f"无效的 trigger_type: {trigger_type_str}",
                    is_error=True,
                )

        if "trigger_value" in kwargs:
            trigger_value = str(kwargs.get("trigger_value") or "").strip()
            task.trigger_value = trigger_value
            changed = True

        prompt = str(kwargs.get("prompt") or "").strip()
        if prompt:
            task.prompt = prompt
            changed = True

        title = str(kwargs.get("title") or "").strip()
        if title:
            task.title = title
            changed = True

        if "bind_session_id" in kwargs:
            raw = (kwargs.get("bind_session_id") or "").strip()
            task.bind_session_id = raw or None
            changed = True
        if "continuation_prompt" in kwargs:
            task.continuation_prompt = (kwargs.get("continuation_prompt") or "").strip() or None
            changed = True
        if "max_continuations" in kwargs:
            try:
                task.max_continuations = _coerce_int(kwargs.get("max_continuations"), -1)
            except ValueError:
                return ToolResult(content="max_continuations 必须是整数", is_error=True)
            changed = True
        if "stop_on_signal" in kwargs:
            task.stop_on_signal = _coerce_bool(kwargs.get("stop_on_signal"), task.stop_on_signal)
            changed = True
        if "stop_on_consecutive_errors" in kwargs:
            try:
                task.stop_on_consecutive_errors = _coerce_int(
                    kwargs.get("stop_on_consecutive_errors"),
                    10,
                )
            except ValueError:
                return ToolResult(content="stop_on_consecutive_errors 必须是整数", is_error=True)
            if task.stop_on_consecutive_errors < 1:
                return ToolResult(content="stop_on_consecutive_errors 必须是正整数", is_error=True)
            changed = True
        if "first_run_policy" in kwargs:
            try:
                task.first_run_policy = _parse_first_run_policy(kwargs.get("first_run_policy"))
            except ValueError:
                return ToolResult(
                    content="first_run_policy 只支持 immediate / next_scheduled",
                    is_error=True,
                )
            changed = True

        if not changed:
            return ToolResult(content="未提供任何需要更新的字段")
        if not task.prompt.strip():
            return ToolResult(content="prompt 不能为空", is_error=True)

        task.task_category = _task_category_for_trigger(task.trigger_type)
        if task.task_category == TaskCategory.continuous:
            task.trigger_value = ""
            task.first_run_policy = FirstRunPolicy.immediate

        validation_error = _validate_trigger_value(task.trigger_type, task.trigger_value)
        if validation_error:
            return ToolResult(content=validation_error, is_error=True)

        task.updated_at = datetime.now().isoformat()
        _refresh_next_run(task)

        AutoTaskStore.put_task(user_id, workspace_id, task)

        return ToolResult(
            content=json.dumps(
                {
                    "task_id": task_id,
                    "title": task.title,
                    "trigger_type": task.trigger_type.value,
                    "trigger_value": task.trigger_value,
                    "status": task.status.value,
                    "task_category": task.task_category.value,
                    "first_run_policy": task.first_run_policy.value,
                    "max_continuations": task.max_continuations,
                    "stop_on_signal": task.stop_on_signal,
                    "message": "自动任务已更新",
                },
                ensure_ascii=False,
            )
        )


class ControlAutoTask(AiasysTool):
    """控制自动任务的生命周期：暂停、恢复、完成、立即执行或删除。"""

    name = "ControlAutoTask"
    description = (
        "控制已有自动任务的生命周期。"
        "支持 pause（暂停）、resume（恢复）、complete（标记完成）、run（立即执行一次）、delete（删除）。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["pause", "resume", "complete", "run", "delete"],
                "description": "控制操作类型",
            },
            "task_id": {
                "type": "string",
                "description": "目标任务 ID",
            },
        },
        "required": ["action", "task_id"],
    }

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        ctx = ctx or {}
        action = str(kwargs.get("action") or "").strip().lower()
        task_id = str(kwargs.get("task_id") or "").strip()

        if not action:
            return ToolResult(
                content="缺少 action 参数（pause/resume/complete/run/delete）",
                is_error=True,
            )
        if not task_id:
            return ToolResult(content="缺少 task_id 参数", is_error=True)

        user_id, workspace_id = _resolve_workspace(ctx)
        if not user_id or not workspace_id:
            return ToolResult(content="无法确定当前工作区", is_error=True)

        task = AutoTaskStore.get_task(user_id, workspace_id, task_id)
        if task is None:
            return ToolResult(content=f"任务 {task_id} 不存在", is_error=True)

        if action == "pause":
            task.status = TaskStatus.paused
            task.updated_at = datetime.now().isoformat()
            _refresh_next_run(task)
            AutoTaskStore.put_task(user_id, workspace_id, task)
            return ToolResult(
                content=json.dumps(
                    {"task_id": task_id, "status": "paused", "message": "任务已暂停"},
                    ensure_ascii=False,
                )
            )

        if action == "resume":
            task.status = TaskStatus.active
            task.updated_at = datetime.now().isoformat()
            _refresh_next_run(task)
            AutoTaskStore.put_task(user_id, workspace_id, task)
            return ToolResult(
                content=json.dumps(
                    {"task_id": task_id, "status": "active", "message": "任务已恢复"},
                    ensure_ascii=False,
                )
            )

        if action == "complete":
            task.status = TaskStatus.completed
            task.updated_at = datetime.now().isoformat()
            task.next_run_at = None
            AutoTaskStore.put_task(user_id, workspace_id, task)
            return ToolResult(
                content=json.dumps(
                    {"task_id": task_id, "status": "completed", "message": "任务已标记完成"},
                    ensure_ascii=False,
                )
            )

        if action == "run":
            from app.services.auto_tasks.engine import run_task_now_with_lock

            result = await run_task_now_with_lock(
                task,
                origin="auto_task_agent_run",
            )

            return ToolResult(
                content=json.dumps(
                    {
                        "task_id": task_id,
                        "result": result,
                        "message": "任务已触发执行",
                    },
                    ensure_ascii=False,
                )
            )

        if action == "delete":
            deleted = AutoTaskStore.delete_task(user_id, workspace_id, task_id)
            if not deleted:
                return ToolResult(content=f"任务 {task_id} 不存在或删除失败", is_error=True)
            return ToolResult(
                content=json.dumps(
                    {"task_id": task_id, "message": "任务已删除"},
                    ensure_ascii=False,
                )
            )

        return ToolResult(content=f"未知的 action: {action}", is_error=True)
