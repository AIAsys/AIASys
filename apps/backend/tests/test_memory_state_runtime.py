from __future__ import annotations

from pathlib import Path

import pytest

from app.services.memory.pipeline import (
    MemoryPipelineService,
    get_memory_state_runtime,
    schedule_stage1_for_session,
    schedule_stage2_consolidation,
)
from app.services.memory.constants import USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE
from app.services.memory.models import MemoryScope
from app.services.memory.resolver import get_workspace_memory_file_path
from app.services.memory.state_runtime import MemoryStateRuntime
from app.services.memory.store import MemoryStore


def test_stage1_job_claim_uses_lease_and_done_state(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")

    first = runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-a",
        lease_seconds=60,
        now=100,
        worker_id="worker-a",
    )
    second = runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-a",
        lease_seconds=60,
        now=110,
        worker_id="worker-b",
    )
    third = runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-a",
        lease_seconds=60,
        now=200,
        worker_id="worker-c",
    )

    assert first.status == "claimed"
    assert first.worker_id == "worker-a"
    assert second.status == "leased"
    assert second.lease_until == 160
    assert third.status == "claimed"
    assert third.worker_id == "worker-c"

    runtime.write_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id="workspace-a",
        source_path="/workspace/session-a/.session/execution/records.jsonl",
        raw_memory="raw",
        rollout_summary="summary",
        rollout_slug="session-a",
        now=210,
    )
    after_done = runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-a",
        now=220,
    )

    assert after_done.status == "already_done"


def test_stage1_claim_respects_max_running_jobs(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")

    first = runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-a",
        max_running_jobs=1,
        now=100,
    )
    second = runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-b",
        max_running_jobs=1,
        now=101,
    )

    assert first.status == "claimed"
    assert second.status == "throttled"


def test_stage2_job_claim_uses_single_global_lease(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")

    first = runtime.claim_stage2_job(
        user_id="local_default",
        now=100,
        lease_seconds=60,
        worker_id="worker-a",
    )
    second = runtime.claim_stage2_job(
        user_id="local_default",
        now=110,
        lease_seconds=60,
        worker_id="worker-b",
    )
    third = runtime.claim_stage2_job(
        user_id="local_default",
        now=200,
        lease_seconds=60,
        worker_id="worker-c",
    )

    assert first.status == "claimed"
    assert second.status == "throttled"
    assert third.status == "claimed"


def test_pipeline_records_stage1_outputs_and_consolidation_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.core.config as config_module
    import app.services.memory.pipeline as pipeline_module

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline_module,
        "get_user_global_memory_dir",
        config_module.get_user_global_memory_dir,
    )

    runtime = MemoryStateRuntime(tmp_path / "state.db")
    service = MemoryPipelineService(runtime=runtime)

    record = service.record_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id="workspace-a",
        source_path="/workspace/session-a/.session/execution/records.jsonl",
        raw_memory="- preference: 使用中文",
        rollout_summary="修复 memory state runtime。",
        rollout_slug="2026-05-18 memory runtime",
        metadata={"cwd": "/workspace/a"},
        now=100,
    )
    pending = service.pending_consolidation_inputs(
        user_id="local_default",
        scope_key="workspace-a",
    )

    assert record.rollout_slug == "workspace-a_2026-05-18-memory-runtime"
    assert len(pending) == 1
    assert pending[0].metadata == {"cwd": "/workspace/a"}

    service.mark_consolidated(
        user_id="local_default",
        records=pending,
        memory_text="# MEMORY.md\n",
        summary_text="# Memory Summary\n",
        scope_key="workspace-a",
        now=120,
    )

    assert runtime.get_consolidation_watermark(
        user_id="local_default",
        scope_key="workspace-a",
    ) == 100
    assert service.pending_consolidation_inputs(
        user_id="local_default",
        scope_key="workspace-a",
    ) == []


def test_retention_prunes_only_consolidated_outputs_and_rebuilds_mirrors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.core.config as config_module
    import app.services.memory.pipeline as pipeline_module

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline_module,
        "get_user_global_memory_dir",
        config_module.get_user_global_memory_dir,
    )

    runtime = MemoryStateRuntime(tmp_path / "state.db")
    service = MemoryPipelineService(runtime=runtime)
    old_record = service.record_stage1_output(
        user_id="local_default",
        session_id="old-session",
        workspace_id="workspace-a",
        source_path="/workspace/old/.session/execution/records.jsonl",
        raw_memory="old raw",
        rollout_summary="old summary",
        rollout_slug="old-session",
        now=100,
    )
    new_record = service.record_stage1_output(
        user_id="local_default",
        session_id="new-session",
        workspace_id="workspace-a",
        source_path="/workspace/new/.session/execution/records.jsonl",
        raw_memory="new raw",
        rollout_summary="new summary",
        rollout_slug="new-session",
        now=200,
    )
    pending_record = service.record_stage1_output(
        user_id="local_default",
        session_id="pending-session",
        workspace_id="workspace-a",
        source_path="/workspace/pending/.session/execution/records.jsonl",
        raw_memory="pending raw",
        rollout_summary="pending summary",
        rollout_slug="pending-session",
        now=300,
    )
    runtime.update_consolidation_state(
        user_id="local_default",
        input_watermark=200,
        stage1_output_ids=[old_record.id, new_record.id],
        now=250,
    )

    result = service.apply_retention(user_id="local_default", keep_latest=1)

    assert result["pruned_count"] == 1
    assert result["pruned_rollout_slugs"] == ["workspace-a_old-session"]
    retained_ids = {
        record.id
        for record in runtime.list_stage1_outputs(user_id="local_default", limit=10)
    }
    assert old_record.id not in retained_ids
    assert new_record.id in retained_ids
    assert pending_record.id in retained_ids

    layout = config_module.get_user_global_memory_dir("local_default")
    raw_text = (layout / "raw_memories.md").read_text(encoding="utf-8")
    assert "old raw" not in raw_text
    assert "new raw" in raw_text
    assert "pending raw" in raw_text
    rollout_dir = layout / "rollout_summaries"
    assert not (rollout_dir / "workspace-a_old-session.md").exists()
    assert (rollout_dir / "workspace-a_new-session.md").exists()
    assert (rollout_dir / "workspace-a_pending-session.md").exists()


def test_pipeline_status_reports_latest_jobs_and_pending_outputs(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")

    runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-a",
        workspace_id="workspace-a",
        now=100,
        worker_id="worker-a",
    )
    runtime.write_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id="workspace-a",
        source_path="/workspace/session-a/.session/execution/records.jsonl",
        raw_memory="raw",
        rollout_summary="summary",
        rollout_slug="session-a",
        now=110,
    )
    runtime.claim_stage1_job(
        user_id="local_default",
        session_id="session-b",
        workspace_id="workspace-a",
        now=120,
        worker_id="worker-b",
    )
    runtime.fail_stage1_job(
        user_id="local_default",
        session_id="session-b",
        error="no records",
        now=130,
    )
    runtime.claim_stage2_job(
        user_id="local_default",
        scope_key="workspace-a",
        now=140,
        worker_id="worker-c",
    )

    status = runtime.get_pipeline_status(
        user_id="local_default",
        scope_key="workspace-a",
    )

    assert status["stage1"]["total_outputs"] == 1
    assert status["stage1"]["pending_outputs"] == 1
    assert status["stage1"]["latest_output_at"] == 110
    assert status["stage1"]["latest_job"]["status"] == "failed"
    assert status["stage1"]["latest_job"]["last_error"] == "no records"
    assert status["stage2"]["latest_job"]["status"] == "running"


@pytest.mark.asyncio
async def test_stage2_consolidation_appends_global_and_workspace_memory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.core.config as config_module
    import app.services.memory.pipeline as pipeline_module

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline_module,
        "get_user_global_memory_dir",
        config_module.get_user_global_memory_dir,
    )

    workspace_root = tmp_path / "local_default" / "workspace-a"
    workspace_root.mkdir(parents=True)
    runtime = MemoryStateRuntime(tmp_path / "state.db")
    service = MemoryPipelineService(
        runtime=runtime,
        workspace_root_resolver=lambda user_id, workspace_id: workspace_root,
    )
    service.record_stage1_output(
        user_id="local_default",
        session_id="session-a",
        workspace_id="workspace-a",
        source_path="/workspace/session-a/.session/execution/records.jsonl",
        raw_memory="用户偏好使用简体中文；state.db 是全局单库。",
        rollout_summary="完成 memory state runtime，工作区层同步追加。",
        rollout_slug="session-a",
        now=100,
    )

    count = await service.run_stage2_consolidation(
        user_id="local_default",
        scope_key="workspace-a",
    )

    assert count == 1
    assert service.pending_consolidation_inputs(
        user_id="local_default",
        scope_key="workspace-a",
    ) == []
    assert runtime.get_consolidation_watermark(
        user_id="local_default",
        scope_key="workspace-a",
    ) == 100

    global_store = MemoryStore(
        config_module.get_user_global_memory_dir("local_default") / "MEMORY.md"
    )
    global_text = global_store.read_text()
    assert "workspace-a_session-a" not in global_text

    workspace_store = MemoryStore(get_workspace_memory_file_path(workspace_root))
    workspace_text = workspace_store.read_text()
    assert "## Stage 2 appended memories" in workspace_text
    assert "完成 memory state runtime，工作区层同步追加。" in workspace_text


@pytest.mark.asyncio
async def test_stage2_default_scope_only_processes_user_default_global_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.core.config as config_module
    import app.services.memory.pipeline as pipeline_module

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        pipeline_module,
        "get_user_global_memory_dir",
        config_module.get_user_global_memory_dir,
    )

    runtime = MemoryStateRuntime(tmp_path / "state.db")
    service = MemoryPipelineService(runtime=runtime)
    service.record_stage1_output(
        user_id="local_default",
        session_id="global-session",
        workspace_id=None,
        source_path="p",
        raw_memory="用户要求默认使用中文。",
        rollout_summary="全局偏好。",
        rollout_slug="global-session",
        now=100,
    )
    service.record_stage1_output(
        user_id="local_default",
        session_id="workspace-session",
        workspace_id="workspace-a",
        source_path="p",
        raw_memory="当前工作区数据库叫 demo。",
        rollout_summary="工作区事实。",
        rollout_slug="workspace-session",
        now=110,
    )

    count = await service.run_stage2_consolidation(user_id="local_default")

    assert count == 1
    assert runtime.get_consolidation_watermark(
        user_id="local_default",
        scope_key=USER_DEFAULT_GLOBAL_WORKSPACE_SCOPE,
    ) == 100
    global_text = MemoryStore(
        config_module.get_user_global_memory_dir("local_default") / "MEMORY.md"
    ).read_text()
    assert "用户要求默认使用中文" in global_text
    assert "当前工作区数据库叫 demo" not in global_text
    assert service.pending_consolidation_inputs(
        user_id="local_default",
        scope_key="workspace-a",
    )


@pytest.mark.asyncio
async def test_schedule_stage1_for_session_creates_background_task(tmp_path: Path) -> None:
    class FakeService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def run_stage1_for_session(self, **kwargs):
            self.calls.append(kwargs)
            return None

    service = FakeService()
    task = schedule_stage1_for_session(
        user_id="local_default",
        session_id="session-a",
        workspace_id="workspace-a",
        session_dir=tmp_path / "session-a",
        service=service,  # type: ignore[arg-type]
    )

    assert task is not None
    await task
    assert service.calls == [
        {
            "user_id": "local_default",
            "session_id": "session-a",
            "workspace_id": "workspace-a",
            "session_dir": tmp_path / "session-a",
        }
    ]


@pytest.mark.asyncio
async def test_schedule_stage2_consolidation_creates_background_task() -> None:
    class FakeService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def run_stage2_consolidation(self, **kwargs):
            self.calls.append(kwargs)
            return 0

    service = FakeService()
    task = schedule_stage2_consolidation(
        user_id="local_default",
        service=service,  # type: ignore[arg-type]
    )

    assert task is not None
    await task
    assert service.calls == [{"user_id": "local_default", "scope_key": "user_default_global_workspace"}]


def test_get_memory_state_runtime_defaults_to_user_memory_root(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import app.core.config as config_module
    import app.services.memory.pipeline as pipeline_module

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(pipeline_module, "get_user_global_memory_dir", config_module.get_user_global_memory_dir)

    runtime = get_memory_state_runtime(user_id="local_default")

    assert runtime.db_path == (
        tmp_path
        / "local_default"
        / "global_workspace"
        / ".aiasys"
        / ".memory"
        / "state.db"
    )
