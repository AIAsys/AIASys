from __future__ import annotations

import asyncio

import pytest

from app.models.session import SessionBudget
from app.services.auto_tasks.executor import _build_prompt
from app.services.auto_tasks import engine as auto_task_engine
from app.services.auto_tasks.models import (
    AutoTask,
    AutoTaskTriggerType,
    OverlapPolicy,
    TaskCategory,
    TaskStatus,
)
from app.services.workspace_registry import WorkspaceRegistryService


def test_custom_continuation_prompt_keeps_system_stop_rules():
    task = AutoTask(
        task_id="auto-task-1",
        workspace_id="workspace-1",
        user_id="local_default",
        prompt="完成实验报告并通过测试",
        trigger_type=AutoTaskTriggerType.continuous,
        trigger_value="",
        task_category=TaskCategory.continuous,
        continuation_prompt="本轮优先补齐测试证据",
    )

    prompt = _build_prompt(task)

    assert "目标: 完成实验报告并通过测试" in prompt
    assert "本轮优先补齐测试证据" in prompt
    assert "完成审计" in prompt
    assert 'auto_task_signal(action="complete")' in prompt
    assert 'auto_task_signal(action="pause")' in prompt


def test_scheduled_auto_task_uses_original_prompt():
    task = AutoTask(
        task_id="auto-task-2",
        workspace_id="workspace-1",
        user_id="local_default",
        prompt="每天检查一次数据质量",
        trigger_type=AutoTaskTriggerType.interval,
        trigger_value="3600",
    )

    assert _build_prompt(task) == "每天检查一次数据质量"


@pytest.mark.asyncio
async def test_engine_records_missing_bound_session_as_failed_attempt(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", str(tmp_path))
    service = WorkspaceRegistryService(tmp_path)
    service.create_workspace(
        user_id="local_default",
        title="Auto Task Workspace",
        workspace_id="ws-auto-task",
        initial_conversation_id="conv-1",
    )
    monkeypatch.setattr(
        "app.services.auto_tasks.executor.get_workspace_registry_service",
        lambda: service,
    )

    task = AutoTask(
        task_id="auto-task-missing-session",
        workspace_id="ws-auto-task",
        user_id="local_default",
        prompt="继续推进目标",
        trigger_type=AutoTaskTriggerType.continuous,
        trigger_value="",
        task_category=TaskCategory.continuous,
        bind_session_id="missing-session",
        stop_on_consecutive_errors=2,
    )
    auto_task_engine.AutoTaskStore.put_task("local_default", "ws-auto-task", task)

    await auto_task_engine._execute_and_persist(task)

    persisted = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-missing-session",
    )
    assert persisted is not None
    assert persisted.fired_count == 0
    assert persisted.consecutive_errors == 1
    assert persisted.last_error is not None
    assert "绑定 Session 不存在" in persisted.last_error
    assert persisted.last_run_at is not None
    assert persisted.status == TaskStatus.active

    await auto_task_engine._execute_and_persist(persisted)

    persisted = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-missing-session",
    )
    assert persisted is not None
    assert persisted.fired_count == 0
    assert persisted.consecutive_errors == 2
    assert persisted.status == TaskStatus.disabled


@pytest.mark.asyncio
async def test_continuous_auto_task_pauses_when_session_budget_is_exhausted(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", str(tmp_path))
    service = WorkspaceRegistryService(tmp_path)
    service.create_workspace(
        user_id="local_default",
        title="Auto Task Workspace",
        workspace_id="ws-auto-task",
        initial_conversation_id="conv-1",
    )
    metadata = service.session_manager.get_session("conv-1", "local_default")
    assert metadata is not None
    metadata.budget = SessionBudget(
        token_budget=10,
        tokens_used=10,
        status="budget_limited",
    )
    (tmp_path / "local_default" / "conv-1" / "metadata.json").write_text(
        metadata.model_dump_json(indent=2),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.services.auto_tasks.executor.get_workspace_registry_service",
        lambda: service,
    )

    async def _fake_execute(**_kwargs):
        return "预算保护测试"

    monkeypatch.setattr(
        "app.services.agent.agent_service.execute",
        _fake_execute,
    )

    task = AutoTask(
        task_id="auto-task-budget",
        workspace_id="ws-auto-task",
        user_id="local_default",
        prompt="继续推进目标",
        trigger_type=AutoTaskTriggerType.continuous,
        trigger_value="",
        task_category=TaskCategory.continuous,
        bind_session_id="conv-1",
    )
    auto_task_engine.AutoTaskStore.put_task("local_default", "ws-auto-task", task)

    await auto_task_engine._execute_and_persist(task)

    persisted = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-budget",
    )
    assert persisted is not None
    assert persisted.status == TaskStatus.paused
    assert persisted.fired_count == 1


@pytest.mark.asyncio
async def test_queue_overlap_runs_one_pending_attempt_after_current_finishes(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", str(tmp_path))
    service = WorkspaceRegistryService(tmp_path)
    service.create_workspace(
        user_id="local_default",
        title="Auto Task Workspace",
        workspace_id="ws-auto-task",
        initial_conversation_id="conv-1",
    )
    monkeypatch.setattr(
        "app.services.auto_tasks.executor.get_workspace_registry_service",
        lambda: service,
    )

    started = asyncio.Event()
    release_first_run = asyncio.Event()
    run_calls: list[int] = []

    async def _fake_run_auto_task(task: AutoTask, **_kwargs):
        run_calls.append(int(task.pending_run_count or 0))
        if len(run_calls) == 1:
            started.set()
            await release_first_run.wait()
        return {"executed": True}

    monkeypatch.setattr(
        "app.services.auto_tasks.executor.run_auto_task",
        _fake_run_auto_task,
    )

    task = AutoTask(
        task_id="auto-task-queue",
        workspace_id="ws-auto-task",
        user_id="local_default",
        prompt="处理待办",
        trigger_type=AutoTaskTriggerType.interval,
        trigger_value="60",
        overlap_policy=OverlapPolicy.queue,
    )
    auto_task_engine.AutoTaskStore.put_task("local_default", "ws-auto-task", task)

    running = asyncio.create_task(auto_task_engine._run_task_with_lock(task))
    await started.wait()

    queued_task = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-queue",
    )
    assert queued_task is not None
    await auto_task_engine._run_task_with_lock(queued_task)

    queued_task = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-queue",
    )
    assert queued_task is not None
    assert queued_task.pending_run_count == 1

    release_first_run.set()
    await running

    for _ in range(20):
        persisted = auto_task_engine.AutoTaskStore.get_task(
            "local_default",
            "ws-auto-task",
            "auto-task-queue",
        )
        if persisted is not None and persisted.fired_count == 2:
            break
        await asyncio.sleep(0.01)

    persisted = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-queue",
    )
    assert persisted is not None
    assert len(run_calls) == 2
    assert persisted.fired_count == 2
    assert persisted.pending_run_count == 0


@pytest.mark.asyncio
async def test_manual_run_reuses_engine_lock_when_background_run_is_active(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(auto_task_engine, "WORKSPACE_DIR", str(tmp_path))
    service = WorkspaceRegistryService(tmp_path)
    service.create_workspace(
        user_id="local_default",
        title="Auto Task Workspace",
        workspace_id="ws-auto-task",
        initial_conversation_id="conv-1",
    )
    monkeypatch.setattr(
        "app.services.auto_tasks.executor.get_workspace_registry_service",
        lambda: service,
    )

    started = asyncio.Event()
    release_run = asyncio.Event()
    run_calls = 0

    async def _fake_run_auto_task(task: AutoTask, **_kwargs):
        nonlocal run_calls
        run_calls += 1
        started.set()
        await release_run.wait()
        return {"executed": True}

    monkeypatch.setattr(
        "app.services.auto_tasks.executor.run_auto_task",
        _fake_run_auto_task,
    )

    task = AutoTask(
        task_id="auto-task-skip",
        workspace_id="ws-auto-task",
        user_id="local_default",
        prompt="处理待办",
        trigger_type=AutoTaskTriggerType.interval,
        trigger_value="60",
        overlap_policy=OverlapPolicy.skip,
    )
    auto_task_engine.AutoTaskStore.put_task("local_default", "ws-auto-task", task)

    background_run = asyncio.create_task(auto_task_engine._run_task_with_lock(task))
    await started.wait()

    current_task = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-skip",
    )
    assert current_task is not None
    result = await auto_task_engine.run_task_now_with_lock(
        current_task,
        origin="auto_task_manual_run",
    )

    assert result == {
        "executed": False,
        "execution_reason": "overlap_skipped_active_auto_task_branch",
    }
    assert run_calls == 1

    release_run.set()
    await background_run

    persisted = auto_task_engine.AutoTaskStore.get_task(
        "local_default",
        "ws-auto-task",
        "auto-task-skip",
    )
    assert persisted is not None
    assert persisted.fired_count == 1
