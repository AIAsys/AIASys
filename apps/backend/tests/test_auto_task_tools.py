from __future__ import annotations

import json
from datetime import datetime, timedelta

from app.agents.tools.auto_task_tool import (
    ControlAutoTask,
    CreateAutoTask,
    ListAutoTasks,
    UpdateAutoTask,
)
from app.services.auto_tasks import engine as auto_task_engine
from app.services.auto_tasks.models import TaskCategory, TaskStatus
from app.services.workspace_registry import WorkspaceRegistryService


def _prepare_tool_context(
    monkeypatch,
    tmp_path,
    *,
    user_id: str = "local_default",
    workspace_id: str = "ws-auto-task-tools",
    session_id: str = "session-auto-task-tools",
) -> dict[str, str]:
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", str(tmp_path))
    service = WorkspaceRegistryService(tmp_path)
    service.create_workspace(
        user_id=user_id,
        title="Auto Task Tool Workspace",
        workspace_id=workspace_id,
        initial_conversation_id=session_id,
    )
    monkeypatch.setattr(
        "app.agents.tools.auto_task_tool.get_workspace_registry_service",
        lambda: service,
    )
    return {"user_id": user_id, "session_id": session_id}


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


async def test_create_continuous_auto_task_sets_continuous_category(monkeypatch, tmp_path):
    ctx = _prepare_tool_context(monkeypatch, tmp_path)

    result = await CreateAutoTask().invoke(
        ctx,
        trigger_type="continuous",
        prompt="持续推进文献综述",
        title="文献综述推进",
        continuation_prompt="优先处理还没有读完的论文",
        max_continuations=3,
        stop_on_signal=True,
        stop_on_consecutive_errors=2,
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["trigger_type"] == "continuous"
    assert payload["task_category"] == "continuous"
    assert payload["first_run_policy"] == "immediate"
    assert payload["max_continuations"] == 3
    assert payload["stop_on_signal"] is True

    tasks = auto_task_engine.AutoTaskStore.list_tasks(
        "local_default",
        "ws-auto-task-tools",
    )
    assert len(tasks) == 1
    task = tasks[0]
    assert task.task_category == TaskCategory.continuous
    assert task.first_run_policy.value == "immediate"
    assert task.trigger_value == ""
    assert task.continuation_prompt == "优先处理还没有读完的论文"
    assert task.stop_on_consecutive_errors == 2
    assert task.next_run_at is not None


async def test_create_auto_task_can_start_paused(monkeypatch, tmp_path):
    ctx = _prepare_tool_context(monkeypatch, tmp_path)

    result = await CreateAutoTask().invoke(
        ctx,
        trigger_type="continuous",
        prompt="先登记自动研究任务",
        title="受控自动研究",
        status="paused",
    )

    assert result.is_error is False
    payload = json.loads(result.content)
    assert payload["status"] == "paused"

    tasks = auto_task_engine.AutoTaskStore.list_tasks(
        "local_default",
        "ws-auto-task-tools",
    )
    assert len(tasks) == 1
    task = tasks[0]
    assert task.status == TaskStatus.paused
    assert task.next_run_at is None


async def test_update_auto_task_switches_between_scheduled_and_continuous(monkeypatch, tmp_path):
    ctx = _prepare_tool_context(monkeypatch, tmp_path)
    created = await CreateAutoTask().invoke(
        ctx,
        trigger_type="interval",
        trigger_value="3600",
        prompt="定期检查数据",
        title="数据检查",
    )
    task_id = json.loads(created.content)["task_id"]

    updated = await UpdateAutoTask().invoke(
        ctx,
        task_id=task_id,
        trigger_type="continuous",
        continuation_prompt="每轮只推进一个最小交付物",
        max_continuations=5,
        stop_on_signal=False,
    )

    assert updated.is_error is False
    payload = json.loads(updated.content)
    assert payload["trigger_type"] == "continuous"
    assert payload["task_category"] == "continuous"
    assert payload["max_continuations"] == 5
    assert payload["stop_on_signal"] is False

    listed = json.loads((await ListAutoTasks().invoke(ctx)).content)
    assert listed["count"] == 1
    assert listed["tasks"][0]["task_category"] == "continuous"
    assert listed["tasks"][0]["max_continuations"] == 5
    assert listed["tasks"][0]["stop_on_signal"] is False


async def test_control_auto_task_complete_and_delete(monkeypatch, tmp_path):
    ctx = _prepare_tool_context(monkeypatch, tmp_path)
    created = await CreateAutoTask().invoke(
        ctx,
        trigger_type="continuous",
        prompt="完成实验报告",
        title="实验报告",
    )
    task_id = json.loads(created.content)["task_id"]

    completed = await ControlAutoTask().invoke(
        ctx,
        action="complete",
        task_id=task_id,
    )

    assert completed.is_error is False
    complete_payload = json.loads(completed.content)
    assert complete_payload["status"] == "completed"
    task = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task-tools",
        task_id,
    )
    assert task is not None
    assert task.status == TaskStatus.completed
    assert task.next_run_at is None

    deleted = await ControlAutoTask().invoke(
        ctx,
        action="delete",
        task_id=task_id,
    )

    assert deleted.is_error is False
    listed = json.loads((await ListAutoTasks().invoke(ctx)).content)
    assert listed["count"] == 0


async def test_create_auto_task_rejects_invalid_tool_payload(monkeypatch, tmp_path):
    ctx = _prepare_tool_context(monkeypatch, tmp_path)

    result = await CreateAutoTask().invoke(
        ctx,
        trigger_type="interval",
        trigger_value="1",
        prompt="过快执行",
    )

    assert result.is_error is True
    assert "最短支持" in result.content


async def test_create_scheduled_auto_task_supports_first_run_policy(monkeypatch, tmp_path):
    ctx = _prepare_tool_context(monkeypatch, tmp_path)

    delayed = await CreateAutoTask().invoke(
        ctx,
        trigger_type="interval",
        trigger_value="3600",
        first_run_policy="next_scheduled",
        prompt="等待第一个计划点",
    )
    assert delayed.is_error is False
    delayed_payload = json.loads(delayed.content)
    assert delayed_payload["first_run_policy"] == "next_scheduled"

    tasks = auto_task_engine.AutoTaskStore.list_tasks(
        "local_default",
        "ws-auto-task-tools",
    )
    delayed_task = next(t for t in tasks if t.task_id == delayed_payload["task_id"])
    assert delayed_task.next_run_at is not None
    assert _parse_iso(delayed_task.next_run_at) >= datetime.now() + timedelta(seconds=3500)

    updated = await UpdateAutoTask().invoke(
        ctx,
        task_id=delayed_payload["task_id"],
        first_run_policy="immediate",
    )
    assert updated.is_error is False
    updated_payload = json.loads(updated.content)
    assert updated_payload["first_run_policy"] == "immediate"

    updated_task = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task-tools",
        delayed_payload["task_id"],
    )
    assert updated_task is not None
    assert updated_task.next_run_at is not None
    assert _parse_iso(updated_task.next_run_at) <= datetime.now() + timedelta(seconds=2)
