"""Memory resolver 纯文本版测试。"""

from pathlib import Path

import pytest

from app.services.memory.models import MemoryScope
from app.services.memory.resolver import (
    MemoryResolver,
    _compute_snapshot_hash,
    get_user_memory_file_path,
    get_workspace_memory_file_path,
)
from app.services.memory.store import MemoryStore


@pytest.fixture
def memory_dirs(tmp_path: Path):
    user_dir = tmp_path / "user-1"
    user_dir.mkdir(parents=True)
    session_dir = user_dir / "session-a"
    session_dir.mkdir()
    workspace_dir = tmp_path / "workspace-a"
    workspace_dir.mkdir(parents=True)
    return user_dir, session_dir, workspace_dir


def test_memory_resolver_user_only(memory_dirs):
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# User Preference\nUse Chinese.", encoding="utf-8")

    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    preview = resolver.resolve_preview()

    assert "User Preference" in preview.rendered_markdown
    assert preview.snapshot_hash == _compute_snapshot_hash(preview.rendered_markdown)


def test_memory_resolver_with_workspace(memory_dirs):
    user_dir, session_dir, workspace_dir = memory_dirs
    user_memory = get_user_memory_file_path(user_dir)
    user_memory.parent.mkdir(parents=True, exist_ok=True)
    user_memory.write_text("# Global\nGlobal rule.", encoding="utf-8")

    ws_memory = get_workspace_memory_file_path(workspace_dir)
    ws_memory.parent.mkdir(parents=True, exist_ok=True)
    ws_memory.write_text("# Workspace\nWorkspace rule.", encoding="utf-8")

    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        workspace_id="workspace-a",
        workspace_store=MemoryStore(ws_memory),
    )
    preview = resolver.resolve_preview()

    assert "Global rule" in preview.rendered_markdown
    assert "Workspace rule" in preview.rendered_markdown


def test_memory_resolver_empty(memory_dirs):
    _user_dir, session_dir, _workspace_dir = memory_dirs
    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    preview = resolver.resolve_preview()

    assert preview.rendered_markdown == ""
