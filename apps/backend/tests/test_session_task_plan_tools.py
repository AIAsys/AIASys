from __future__ import annotations

import json
import asyncio

from app.agents.tools.task_plan_tools import (
    EnterPlanModeTool,
    ExitPlanModeTool,
    SetTodoList,
    TaskCreateTool,
    TaskListTool,
    TaskUpdateTool,
)
from app.agents.tools.ask_user.models import AskUserResponse, AskUserStore
from app.models.session import SessionMetadata
from app.services.session import SessionTaskPlanStore


def _write_metadata(tmp_path, session_id: str = "session-task-plan") -> None:
    (tmp_path / ".aiasys" / "session" / "_active").mkdir(parents=True)
    (tmp_path / "metadata.json").write_text(
        SessionMetadata(
            session_id=session_id,
            user_id="local_default",
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )


async def test_task_tools_persist_tasks_to_session_metadata(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }

    create_result = await TaskCreateTool().invoke(
        ctx,
        tasks=[
            {"id": "inspect", "content": "确认现有实现"},
            {"id": "patch", "content": "补齐代码", "dependencies": ["inspect"]},
        ],
    )
    assert create_result.is_error is False

    update_result = await TaskUpdateTool().invoke(
        ctx,
        id="inspect",
        status="completed",
    )
    assert update_result.is_error is False
    update_result = await TaskUpdateTool().invoke(
        ctx,
        id="patch",
        status="in_progress",
    )
    assert update_result.is_error is False

    metadata = SessionMetadata(
        **json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))
    )
    assert [task.id for task in metadata.tasks] == ["patch", "inspect"]
    assert metadata.tasks[0].status == "in_progress"
    assert metadata.tasks[1].status == "completed"

    list_payload = json.loads((await TaskListTool().invoke(ctx)).content)
    assert list_payload["counts"] == {
        "pending": 0,
        "in_progress": 1,
        "completed": 1,
        "cancelled": 0,
    }


async def test_task_update_rejects_unmet_dependency(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }
    await TaskCreateTool().invoke(
        ctx,
        tasks=[
            {"id": "a", "content": "A"},
            {"id": "b", "content": "B", "dependencies": ["a"]},
        ],
    )

    result = await TaskUpdateTool().invoke(ctx, id="b", status="in_progress")

    assert result.is_error is True
    assert "依赖尚未完成" in result.content


async def test_enter_plan_mode_updates_metadata(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }

    result = await EnterPlanModeTool().invoke(ctx, reason="复杂跨模块修改")

    assert result.is_error is False
    plan_state = SessionTaskPlanStore(tmp_path).read_plan_state()
    assert plan_state.mode == "active"
    assert plan_state.approval_status == "draft"


async def test_exit_plan_mode_writes_plan_and_waits_for_approval(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }
    await EnterPlanModeTool().invoke(ctx, reason="复杂跨模块修改")

    async def _approve_pending_request() -> None:
        store = AskUserStore()
        for _ in range(50):
            pending = store.list_pending(
                session_id="session-task-plan",
                user_id="local_default",
            )
            if pending:
                request_id = pending[0]["request_id"]
                store.resolve_request(
                    request_id,
                    AskUserResponse(
                        request_id=request_id,
                        approved=True,
                        value="同意执行",
                    ),
                )
                return
            await asyncio.sleep(0.01)
        raise AssertionError("未收到 plan 审批请求")

    approve_task = asyncio.create_task(_approve_pending_request())
    results = [
        item
        async for item in ExitPlanModeTool().invoke_stream(
            ctx,
            plan_filename="task-plan.md",
            summary="按计划实现 task/plan 元工具",
            plan_markdown="# 执行计划\n\n- 补后端\n- 补前端\n- 验证",
        )
    ]
    await approve_task

    assert len(results) == 2
    assert results[0].artifacts
    event = results[0].artifacts[0]["_streaming_event"]
    assert event["kind"] == "ask_user_request"
    final_payload = json.loads(results[-1].content)
    assert final_payload["plan_file"] == "task-plan.md"
    assert final_payload["plan_state"]["mode"] == "inactive"
    assert final_payload["plan_state"]["approval_status"] == "approved"
    assert (tmp_path / ".aiasys" / "session" / "_active" / "plans" / "task-plan.md").exists()


async def test_set_todo_list_write_and_read(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }

    write_result = await SetTodoList().invoke(
        ctx,
        todos=[
            {"id": "1", "content": "分析代码", "status": "pending"},
            {"id": "2", "content": "编写测试", "status": "in_progress"},
        ],
    )
    assert write_result.is_error is False
    payload = json.loads(write_result.content)
    assert payload["counts"]["pending"] == 1
    assert payload["counts"]["in_progress"] == 1

    read_result = await SetTodoList().invoke(ctx)
    assert read_result.is_error is False
    read_payload = json.loads(read_result.content)
    assert len(read_payload["tasks"]) == 2
    assert read_payload["summary"].startswith("-")


async def test_set_todo_list_merge_mode(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }

    await SetTodoList().invoke(
        ctx,
        todos=[{"id": "1", "content": "原始任务", "status": "pending"}],
    )
    merge_result = await SetTodoList().invoke(
        ctx,
        todos=[{"id": "1", "content": "更新后", "status": "completed"}],
        merge=True,
    )
    assert merge_result.is_error is False
    payload = json.loads(merge_result.content)
    assert payload["counts"]["completed"] == 1


async def test_set_todo_list_clear_with_empty_list(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }

    await SetTodoList().invoke(
        ctx,
        todos=[{"id": "1", "content": "任务", "status": "pending"}],
    )
    clear_result = await SetTodoList().invoke(ctx, todos=[])
    assert clear_result.is_error is False

    read_result = await SetTodoList().invoke(ctx)
    assert read_result.content == "当前没有待办任务。"


async def test_set_todo_list_read_empty(tmp_path):
    _write_metadata(tmp_path)
    ctx = {
        "session_root": tmp_path,
        "session_id": "session-task-plan",
        "user_id": "local_default",
    }

    result = await SetTodoList().invoke(ctx)
    assert result.is_error is False
    assert result.content == "当前没有待办任务。"
