"""Memory 容量限制与监控测试。"""

from pathlib import Path

import pytest

from app.services.memory.constants import (
    MAX_MEMORY_SIZE,
    MAX_SUMMARY_SIZE,
    MAX_WORKSPACE_MEMORY_SIZE,
)
from app.services.memory.pipeline import MemoryPipelineService
from app.services.memory.resolver import get_workspace_memory_file_path
from app.services.memory.state_runtime import MemoryStateRuntime
from app.services.memory.store import MemoryCapacityError, MemoryStore


@pytest.fixture
def service_with_layout(tmp_path: Path, monkeypatch):
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
    return service, tmp_path


def test_capacity_ok(service_with_layout):
    service, _tmp_path = service_with_layout
    info = service.check_capacity(user_id="local_default")
    assert info["status"] == "ok"
    assert info["memory"]["current"] == 0
    assert info["memory"]["percentage"] == 0.0


def test_capacity_warning_on_memory(service_with_layout):
    service, tmp_path = service_with_layout
    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "MEMORY.md"
    # 写入超过 80% 容量的内容
    warning_size = int(MAX_MEMORY_SIZE * 0.85)
    memory_file.write_text("x" * warning_size, encoding="utf-8")

    info = service.check_capacity(user_id="local_default")
    assert info["status"] == "warning"
    assert info["memory"]["current"] == warning_size
    assert info["memory"]["percentage"] > 80


def test_capacity_critical_on_memory(service_with_layout):
    service, tmp_path = service_with_layout
    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "MEMORY.md"
    critical_size = int(MAX_MEMORY_SIZE * 0.95)
    memory_file.write_text("x" * critical_size, encoding="utf-8")

    info = service.check_capacity(user_id="local_default")
    assert info["status"] == "critical"


def test_capacity_warning_on_summary(service_with_layout):
    service, tmp_path = service_with_layout
    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    summary_file = memory_dir / "memory_summary.md"
    warning_size = int(MAX_SUMMARY_SIZE * 0.85)
    summary_file.write_text("x" * warning_size, encoding="utf-8")

    info = service.check_capacity(user_id="local_default")
    assert info["status"] == "warning"
    assert info["summary"]["current"] == warning_size


def test_capacity_with_workspace(service_with_layout):
    service, tmp_path = service_with_layout
    workspace_root = tmp_path / "workspace-a"
    workspace_root.mkdir(parents=True)
    ws_path = get_workspace_memory_file_path(workspace_root)
    ws_path.write_text("y" * 100, encoding="utf-8")

    info = service.check_capacity(
        user_id="local_default",
        workspace_root=workspace_root,
    )
    assert info["workspace"]["current"] == 100
    assert info["workspace"]["limit"] == MAX_WORKSPACE_MEMORY_SIZE


def test_should_consolidate_on_capacity_warning(service_with_layout):
    service, _tmp_path = service_with_layout
    capacity_info = {
        "status": "warning",
        "memory": {"percentage": 85.0},
        "summary": {"percentage": 10.0},
        "workspace": {"percentage": 0.0},
    }
    records = []
    assert service._should_consolidate(records=records, capacity_info=capacity_info)


def test_should_consolidate_on_many_records(service_with_layout):
    service, _tmp_path = service_with_layout
    from app.services.memory.state_runtime import Stage1OutputRecord

    records = [
        Stage1OutputRecord(
            id=f"r{i}",
            user_id="u",
            session_id="s",
            workspace_id=None,
            source_path="p",
            raw_memory="m",
            rollout_summary="s",
            rollout_slug="slug",
            metadata={},
            created_at=100 + i,
            consolidated_at=None,
        )
        for i in range(3)
    ]
    capacity_info = {
        "status": "ok",
        "memory": {"percentage": 10.0},
        "summary": {"percentage": 10.0},
        "workspace": {"percentage": 0.0},
    }
    assert service._should_consolidate(records=records, capacity_info=capacity_info)


def test_should_not_consolidate_when_healthy(service_with_layout):
    service, _tmp_path = service_with_layout
    from app.services.memory.state_runtime import Stage1OutputRecord

    records = [
        Stage1OutputRecord(
            id="r1",
            user_id="u",
            session_id="s",
            workspace_id=None,
            source_path="p",
            raw_memory="m",
            rollout_summary="s",
            rollout_slug="slug",
            metadata={},
            created_at=100,
            consolidated_at=None,
        )
    ]
    capacity_info = {
        "status": "ok",
        "memory": {"percentage": 10.0},
        "summary": {"percentage": 10.0},
        "workspace": {"percentage": 0.0},
    }
    assert not service._should_consolidate(records=records, capacity_info=capacity_info)


def test_memory_store_rejects_oversized_content(tmp_path):
    store = MemoryStore(tmp_path / "test.md")
    oversized = "x" * 101
    with pytest.raises(MemoryCapacityError):
        store.write_text(oversized, max_size=100)


def test_memory_store_allows_content_within_limit(tmp_path):
    store = MemoryStore(tmp_path / "test.md")
    store.write_text("x" * 100, max_size=100)
    assert len(store.read_text()) == 100


def test_pipeline_rejects_append_when_over_limit(service_with_layout):
    service, tmp_path = service_with_layout
    from app.services.memory.state_runtime import Stage1OutputRecord

    # 预设一个接近上限的 MEMORY.md
    memory_dir = tmp_path / "local_default" / "global_workspace" / ".aiasys" / ".memory"
    memory_dir.mkdir(parents=True)
    memory_file = memory_dir / "MEMORY.md"
    memory_file.write_text("x" * (MAX_MEMORY_SIZE - 10), encoding="utf-8")

    records = [
        Stage1OutputRecord(
            id="r1",
            user_id="local_default",
            session_id="s1",
            workspace_id=None,
            source_path="p",
            raw_memory="y" * 100,
            rollout_summary="summary",
            rollout_slug="slug",
            metadata={},
            created_at=100,
            consolidated_at=None,
        )
    ]

    with pytest.raises(MemoryCapacityError):
        service._append_stage2_records_to_markdown(user_id="local_default", records=records)
