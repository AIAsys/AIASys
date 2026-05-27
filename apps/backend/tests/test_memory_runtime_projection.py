"""Memory runtime projection 测试（纯文本版）。"""

from __future__ import annotations

import pytest

from app.services.memory import resolver as memory_resolver
from app.services.memory.resolver import get_user_memory_file_path
from app.services.memory.store import MemoryStore
from app.services.session.config_projection import (
    build_runtime_config_projection,
    write_runtime_config_state,
)
from app.services.workspace_registry import WorkspaceRegistryService


@pytest.mark.asyncio
async def test_runtime_projection_marks_memory_snapshot_pending(
    tmp_path,
    monkeypatch,
) -> None:
    import app.core.config as config_module
    import app.services.session.config_projection as projection_module

    async def fake_compute_agent_config_version(**kwargs):
        return "agent-v1"

    monkeypatch.setattr(config_module, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(memory_resolver, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(
        projection_module,
        "compute_agent_config_version",
        fake_compute_agent_config_version,
    )
    monkeypatch.setattr(
        projection_module,
        "compute_capability_snapshot_version",
        lambda session_dir: "cap-v1",
    )
    monkeypatch.setattr(
        projection_module,
        "build_workspace_capability_summary",
        lambda session_dir: {"skill_count": 0, "mcp_server_count": 0},
    )

    registry = WorkspaceRegistryService(tmp_path)
    registry.create_workspace(
        user_id="local_default",
        workspace_id="workspace-memory",
        title="Memory Projection Workspace",
        initial_conversation_id="session-memory",
    )
    session_dir = tmp_path / "local_default" / "session-memory"

    user_memory = get_user_memory_file_path(tmp_path / "local_default")
    MemoryStore(user_memory).write_text("## 用户默认层\n- 记住当前偏好。\n")

    projection = await build_runtime_config_projection(
        session_dir=session_dir,
        user_id="local_default",
        session_id="session-memory",
        sandbox_mode=None,
        runtime_busy=False,
    )

    assert projection["rebuild_required"] is True
    assert "memory_snapshot_updated" in projection["rebuild_required_reasons"]
    assert projection["pending_memory_snapshot_hash"]
    assert "记住当前偏好" in projection["memory_snapshot_preview"]["rendered_markdown"]

    write_runtime_config_state(
        session_dir,
        applied_agent_config_version="agent-v1",
        applied_capability_snapshot_version="cap-v1",
        applied_memory_snapshot_version=projection["current_memory_snapshot_version"],
        applied_memory_snapshot_hash=projection["current_memory_snapshot_hash"],
    )

    aligned = await build_runtime_config_projection(
        session_dir=session_dir,
        user_id="local_default",
        session_id="session-memory",
        sandbox_mode=None,
        runtime_busy=False,
    )

    assert aligned["rebuild_required"] is False
    assert aligned["pending_memory_snapshot_hash"] is None
