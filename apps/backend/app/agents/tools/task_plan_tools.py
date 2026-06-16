"""
Session 级 Task / Plan 工具。

这些工具用于单个 Agent 会话内的任务分解、进度跟踪和只读规划隔离。
它们不触碰 AutoTask 工作区调度，也不负责子 Agent 委派。
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from app.agents.tools.ask_user.models import AskUserRequest, AskUserStore, AskUserType
from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.models.session import SessionTaskItem
from app.services.history import current_session_id, current_session_root, current_user_id
from app.services.session import SessionTaskPlanStore


def _resolve_store(ctx: dict[str, Any] | None) -> tuple[SessionTaskPlanStore, str, str]:
    ctx = ctx or {}
    session_root = Path(str(ctx.get("session_root") or current_session_root.get() or "."))
    session_id = str(ctx.get("session_id") or current_session_id.get() or "").strip()
    user_id = str(ctx.get("user_id") or current_user_id.get() or "").strip()
    if not session_id or not user_id:
        raise ValueError("当前缺少 session 上下文")
    return SessionTaskPlanStore(session_root), user_id, session_id


def _format_tasks(tasks: list[SessionTaskItem]) -> str:
    if not tasks:
        return "当前没有任务。"
    lines = []
    for task in tasks:
        marker = {
            "pending": "[ ]",
            "in_progress": "[>]",
            "completed": "[x]",
            "cancelled": "[-]",
        }.get(task.status, "[ ]")
        deps = f" (依赖: {', '.join(task.dependencies)})" if task.dependencies else ""
        lines.append(f"- {marker} {task.id}: {task.content}{deps}")
    return "\n".join(lines)


def _summarize_counts(tasks: list[SessionTaskItem]) -> dict[str, int]:
    counts = {"pending": 0, "in_progress": 0, "completed": 0, "cancelled": 0}
    for task in tasks:
        counts[task.status] = counts.get(task.status, 0) + 1
    return counts


class TaskInput(BaseModel):
    id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)


class TaskCreateParams(BaseModel):
    tasks: list[TaskInput] = Field(default_factory=list)
    merge: bool = Field(
        default=True,
        description="true 表示增量创建或覆盖同 id 任务；false 表示用本次列表替换整个任务板。",
    )


class SetTodoListItem(BaseModel):
    id: str = Field(min_length=1, description="任务唯一标识")
    content: str = Field(min_length=1, description="任务描述")
    status: Literal["pending", "in_progress", "completed", "cancelled"] = Field(
        default="pending",
        description="任务状态",
    )


class SetTodoListParams(BaseModel):
    todos: list[SetTodoListItem] | None = Field(
        default=None,
        description="要写入的待办列表。不提供则读取当前列表。",
    )
    merge: bool = Field(
        default=False,
        description="true 表示增量更新同 id 任务；false（默认）表示替换整个列表。",
    )


class TaskUpdateParams(BaseModel):
    id: str = Field(min_length=1)
    status: Literal["pending", "in_progress", "completed", "cancelled"]
    content: str | None = None
    dependencies: list[str] | None = None


class TaskListParams(BaseModel):
    include_completed: bool = True


class EnterPlanModeParams(BaseModel):
    reason: str = Field(min_length=1)


class ExitPlanModeParams(BaseModel):
    plan_filename: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    plan_markdown: str = Field(
        min_length=1,
        description="完整计划内容，Markdown 格式。",
    )


class TaskCreateTool(AiasysTool):
    name: ClassVar[str] = "task_create"
    description: ClassVar[str] = (
        "创建当前会话的结构化任务。适合复杂需求拆分。每项需要 id、content，可选 dependencies。"
    )
    params: ClassVar[type[BaseModel]] = TaskCreateParams

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        params = TaskCreateParams.model_validate(kwargs)
        store, user_id, session_id = _resolve_store(ctx)

        created: list[SessionTaskItem] = []
        now = datetime.now().isoformat()
        for item in params.tasks:
            task = SessionTaskItem(
                id=item.id.strip(),
                content=item.content.strip(),
                dependencies=[dep.strip() for dep in item.dependencies if dep.strip()],
                status="pending",
                created_at=now,
                updated_at=now,
            )
            created.append(task)

        try:
            normalized = store.write_tasks(created, merge=params.merge)
        except Exception as exc:
            return ToolResult(content=str(exc), is_error=True)

        return ToolResult(
            content=json.dumps(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "created": [task.model_dump(mode="json") for task in created],
                    "counts": _summarize_counts(normalized),
                    "tasks": [task.model_dump(mode="json") for task in normalized],
                    "summary": _format_tasks(normalized),
                },
                ensure_ascii=False,
            )
        )


class TaskUpdateTool(AiasysTool):
    name: ClassVar[str] = "task_update"
    description: ClassVar[str] = "更新当前会话中的任务状态、内容或依赖。"
    params: ClassVar[type[BaseModel]] = TaskUpdateParams

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        params = TaskUpdateParams.model_validate(kwargs)
        store, user_id, session_id = _resolve_store(ctx)
        try:
            normalized = store.update_task(
                params.id.strip(),
                status=params.status,
                content=params.content,
                dependencies=params.dependencies,
            )
        except Exception as exc:
            return ToolResult(content=str(exc), is_error=True)
        return ToolResult(
            content=json.dumps(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "counts": _summarize_counts(normalized),
                    "tasks": [task.model_dump(mode="json") for task in normalized],
                    "summary": _format_tasks(normalized),
                },
                ensure_ascii=False,
            )
        )


class TaskListTool(AiasysTool):
    name: ClassVar[str] = "task_list"
    description: ClassVar[str] = "列出当前会话中的所有结构化任务。"
    params: ClassVar[type[BaseModel]] = TaskListParams

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        params = TaskListParams.model_validate(kwargs)
        store, user_id, session_id = _resolve_store(ctx)
        tasks = store.read_tasks()
        visible_tasks = (
            tasks
            if params.include_completed
            else [task for task in tasks if task.status in {"pending", "in_progress"}]
        )
        return ToolResult(
            content=json.dumps(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "counts": _summarize_counts(tasks),
                    "tasks": [task.model_dump(mode="json") for task in visible_tasks],
                    "summary": _format_tasks(visible_tasks),
                },
                ensure_ascii=False,
            )
        )


class SetTodoList(AiasysTool):
    name: ClassVar[str] = "SetTodoList"
    description: ClassVar[str] = (
        "管理当前会话的待办任务列表。提供 todos 参数写入或更新列表，"
        "不提供则读取当前列表。每项需要 id、content 和 status。"
    )
    params: ClassVar[type[BaseModel]] = SetTodoListParams

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        params = SetTodoListParams.model_validate(kwargs)
        store, user_id, session_id = _resolve_store(ctx)

        if params.todos is not None:
            now = datetime.now().isoformat()
            tasks: list[SessionTaskItem] = []
            for item in params.todos:
                tasks.append(
                    SessionTaskItem(
                        id=item.id.strip(),
                        content=item.content.strip(),
                        status=item.status,
                        created_at=now,
                        updated_at=now,
                    )
                )
            try:
                normalized = store.write_tasks(tasks, merge=params.merge)
            except Exception as exc:
                return ToolResult(content=str(exc), is_error=True)
            return ToolResult(
                content=json.dumps(
                    {
                        "session_id": session_id,
                        "user_id": user_id,
                        "counts": _summarize_counts(normalized),
                        "tasks": [task.model_dump(mode="json") for task in normalized],
                        "summary": _format_tasks(normalized),
                    },
                    ensure_ascii=False,
                )
            )

        tasks = store.read_tasks()
        if not tasks:
            return ToolResult(content="当前没有待办任务。")
        return ToolResult(
            content=json.dumps(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "counts": _summarize_counts(tasks),
                    "tasks": [task.model_dump(mode="json") for task in tasks],
                    "summary": _format_tasks(tasks),
                },
                ensure_ascii=False,
            )
        )


class EnterPlanModeTool(AiasysTool):
    name: ClassVar[str] = "enter_plan_mode"
    description: ClassVar[str] = (
        "进入只读规划模式。进入后运行时只允许读类工具、ask_user、task_list、exit_plan_mode。"
    )
    params: ClassVar[type[BaseModel]] = EnterPlanModeParams

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        params = EnterPlanModeParams.model_validate(kwargs)
        store, user_id, session_id = _resolve_store(ctx)
        # 保存进入 Plan Mode 前的权限模式，以便批准后恢复
        pre_mode = str(ctx.get("authorization_mode") or "smart") if ctx else "smart"
        plan_state = store.enter_plan_mode(pre_plan_permission_mode=pre_mode)
        return ToolResult(
            content=json.dumps(
                {
                    "session_id": session_id,
                    "user_id": user_id,
                    "plan_state": plan_state.model_dump(mode="json"),
                    "reason": params.reason,
                    "message": "已进入 Plan Mode。请只读探索、写出计划，并通过 exit_plan_mode 提交审批。",
                },
                ensure_ascii=False,
            )
        )


class ExitPlanModeTool(AiasysTool):
    name: ClassVar[str] = "exit_plan_mode"
    description: ClassVar[str] = (
        "提交规划方案并请求用户批准进入执行模式。计划会写入当前 session 的 plans 目录。"
    )
    params: ClassVar[type[BaseModel]] = ExitPlanModeParams

    async def invoke_stream(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ):
        params = ExitPlanModeParams.model_validate(kwargs)
        store, user_id, session_id = _resolve_store(ctx)
        plan_content = params.plan_markdown.strip()
        if not plan_content.startswith("#"):
            plan_content = f"# {params.plan_filename}\n\n{plan_content}"

        try:
            record = store.write_plan_file(
                filename=params.plan_filename,
                title=params.plan_filename,
                content=plan_content,
                status="pending_approval",
            )
        except Exception as exc:
            yield ToolResult(content=str(exc), is_error=True)
            return

        request = AskUserRequest(
            request_id=str(uuid.uuid4()),
            type=AskUserType.CHECKPOINT_REVIEW,
            title="审批执行计划",
            message=params.summary,
            timeout=600,
            checkpoint_data={
                "checkpoint_id": f"plan:{record.filename}",
                "title": "审批执行计划",
                "description": params.summary,
                "phase_name": "Plan Mode",
                "phase_id": "plan_mode",
                "deliverables": [
                    {
                        "item": record.filename,
                        "exists": True,
                        "path": f".aiasys/session/_active/plans/{record.filename}",
                        "status": "PASS",
                    }
                ],
                "custom_checks": [
                    {
                        "item": "确认计划范围、关键文件和验证方式可接受",
                        "status": "PENDING",
                        "note": plan_content,
                    }
                ],
                "auto_check_passed": True,
            },
        )

        yield ToolResult(
            content="",
            is_error=False,
            artifacts=[
                {
                    "_streaming_event": {
                        "kind": "ask_user_request",
                        "content": json.dumps(request.model_dump(), ensure_ascii=False),
                    }
                }
            ],
        )

        store_obj = AskUserStore()
        future = store_obj.create_request(
            request=request,
            session_id=session_id,
            user_id=user_id,
        )

        try:
            response = await asyncio.wait_for(future, timeout=request.timeout)
            if response.approved:
                approved_record = store.approve_plan_file(record.filename)
                final_payload = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "plan_file": approved_record.filename,
                    "plan_state": store.read_plan_state().model_dump(mode="json"),
                    "message": "用户已批准计划，已退出 Plan Mode，可以进入执行。",
                    "response": response.value,
                }
                yield ToolResult(content=json.dumps(final_payload, ensure_ascii=False))
            else:
                rejected_record = store.reject_plan_file(record.filename)
                final_payload = {
                    "session_id": session_id,
                    "user_id": user_id,
                    "plan_file": rejected_record.filename,
                    "plan_state": store.read_plan_state().model_dump(mode="json"),
                    "message": "用户未批准计划，请继续调整计划。",
                    "response": response.value,
                }
                yield ToolResult(
                    content=json.dumps(final_payload, ensure_ascii=False), is_error=True
                )
        except asyncio.TimeoutError:
            store.reject_plan_file(record.filename)
            yield ToolResult(content="等待用户审批超时，计划仍保持待调整状态。", is_error=True)
        finally:
            store_obj.remove_request(request.request_id)

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        final_result: ToolResult | None = None
        async for result in self.invoke_stream(ctx, **kwargs):
            final_result = result
        return final_result or ToolResult(content="计划审批没有返回结果", is_error=True)
