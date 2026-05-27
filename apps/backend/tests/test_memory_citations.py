from __future__ import annotations

from pathlib import Path

import pytest

from app.services.memory.pipeline import (
    MemoryPipelineService,
    get_memory_state_runtime,
)
from app.services.memory.state_runtime import MemoryStateRuntime


def test_record_citation_increments_count(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")
    runtime.write_stage1_output(
        user_id="u1",
        session_id="s1",
        source_path="/src",
        raw_memory="raw",
        rollout_summary="summary",
        rollout_slug="slug",
        now=100,
    )

    runtime.record_citation(user_id="u1", session_id="s1", now=200)
    runtime.record_citation(user_id="u1", session_id="s1", now=300)

    stats = runtime.get_citation_stats(user_id="u1")
    assert len(stats) == 1
    assert stats[0]["usage_count"] == 2


def test_record_citation_updates_last_used(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")
    runtime.write_stage1_output(
        user_id="u1",
        session_id="s1",
        source_path="/src",
        raw_memory="raw",
        rollout_summary="summary",
        rollout_slug="slug",
        now=100,
    )

    runtime.record_citation(user_id="u1", session_id="s1", now=500)

    stats = runtime.get_citation_stats(user_id="u1")
    assert stats[0]["last_used_at"] == 500


def test_retention_preserves_high_usage_records(
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
        workspace_id="ws-a",
        source_path="/workspace/old/.aiasys/session/execution/records.jsonl",
        raw_memory="old raw",
        rollout_summary="old summary",
        rollout_slug="old-session",
        now=100,
    )
    new_record = service.record_stage1_output(
        user_id="local_default",
        session_id="new-session",
        workspace_id="ws-a",
        source_path="/workspace/new/.aiasys/session/execution/records.jsonl",
        raw_memory="new raw",
        rollout_summary="new summary",
        rollout_slug="new-session",
        now=200,
    )
    runtime.update_consolidation_state(
        user_id="local_default",
        input_watermark=200,
        stage1_output_ids=[old_record.id, new_record.id],
        now=250,
    )

    # 给旧记录刷高引用次数，应被保留
    runtime.record_citation(
        user_id="local_default",
        session_id="old-session",
        now=300,
    )
    runtime.record_citation(
        user_id="local_default",
        session_id="old-session",
        now=310,
    )
    runtime.record_citation(
        user_id="local_default",
        session_id="old-session",
        now=320,
    )

    # keep_latest=0 使所有记录都超出数量保护窗口
    result = service.apply_retention(
        user_id="local_default",
        keep_latest=0,
        max_age_days=1,
    )

    # old-session usage_count=3，受保护；new-session usage_count=0，被清理
    assert result["pruned_count"] == 1
    assert result["pruned_rollout_slugs"] == ["ws-a_new-session"]

    retained = runtime.list_stage1_outputs(user_id="local_default", limit=10)
    retained_ids = {r.id for r in retained}
    assert old_record.id in retained_ids
    assert new_record.id not in retained_ids


def test_retention_removes_low_usage_old_records(
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
        workspace_id="ws-a",
        source_path="/workspace/old/.aiasys/session/execution/records.jsonl",
        raw_memory="old raw",
        rollout_summary="old summary",
        rollout_slug="old-session",
        now=100,
    )
    new_record = service.record_stage1_output(
        user_id="local_default",
        session_id="new-session",
        workspace_id="ws-a",
        source_path="/workspace/new/.aiasys/session/execution/records.jsonl",
        raw_memory="new raw",
        rollout_summary="new summary",
        rollout_slug="new-session",
        now=200,
    )
    runtime.update_consolidation_state(
        user_id="local_default",
        input_watermark=200,
        stage1_output_ids=[old_record.id, new_record.id],
        now=250,
    )

    # keep_latest=0 使所有记录都超出数量保护窗口
    result = service.apply_retention(
        user_id="local_default",
        keep_latest=0,
        max_age_days=1,
    )

    assert result["pruned_count"] == 2
    assert "ws-a_old-session" in result["pruned_rollout_slugs"]
    assert "ws-a_new-session" in result["pruned_rollout_slugs"]

    retained = runtime.list_stage1_outputs(user_id="local_default", limit=10)
    retained_ids = {r.id for r in retained}
    assert old_record.id not in retained_ids
    assert new_record.id not in retained_ids


def test_get_citation_stats_returns_ordered_list(tmp_path: Path) -> None:
    runtime = MemoryStateRuntime(tmp_path / "state.db")

    for i in range(3):
        runtime.write_stage1_output(
            user_id="u1",
            session_id=f"s{i}",
            source_path="/src",
            raw_memory="raw",
            rollout_summary="summary",
            rollout_slug=f"slug-{i}",
            now=100 + i,
        )

    runtime.record_citation(user_id="u1", session_id="s1", now=200)
    runtime.record_citation(user_id="u1", session_id="s1", now=210)
    runtime.record_citation(user_id="u1", session_id="s2", now=220)

    stats = runtime.get_citation_stats(user_id="u1")
    assert len(stats) == 2
    assert stats[0]["session_id"] == "s1"
    assert stats[0]["usage_count"] == 2
    assert stats[1]["session_id"] == "s2"
    assert stats[1]["usage_count"] == 1
