"""Memory Frozen Snapshot 机制测试。"""

from pathlib import Path

import pytest

from app.services.memory.resolver import (
    MemoryResolver,
    get_user_memory_file_path,
    get_workspace_memory_file_path,
    invalidate_resolver_cache,
    resolve_session_memory_preview,
)
from app.services.memory.store import MemoryStore


@pytest.fixture(autouse=True)
def clear_resolver_cache():
    """每个测试前后清空模块级 resolver 缓存，避免测试间互相污染。"""
    from app.services.memory.resolver import _resolver_cache

    _resolver_cache.clear()
    yield
    _resolver_cache.clear()


@pytest.fixture
def memory_dirs(tmp_path: Path):
    user_dir = tmp_path / "user-1"
    user_dir.mkdir(parents=True)
    session_dir = user_dir / "session-a"
    session_dir.mkdir()
    workspace_dir = tmp_path / "workspace-a"
    workspace_dir.mkdir(parents=True)
    return user_dir, session_dir, workspace_dir


def test_snapshot_caches_first_resolve(memory_dirs):
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# Original\nContent.", encoding="utf-8")

    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    preview1 = resolver.resolve_preview()
    assert "Original" in preview1.rendered_markdown

    # 修改底层文件
    memory_path.write_text("# Modified\nNew content.", encoding="utf-8")

    # 快照应该复用缓存
    preview2 = resolver.resolve_preview()
    assert preview2.rendered_markdown == preview1.rendered_markdown
    assert "Modified" not in preview2.rendered_markdown


def test_snapshot_invalidation_refreshes(memory_dirs):
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# Original", encoding="utf-8")

    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    preview1 = resolver.resolve_preview()

    # 修改文件并手动失效
    memory_path.write_text("# Updated", encoding="utf-8")
    resolver.invalidate()

    preview2 = resolver.resolve_preview()
    assert preview2.rendered_markdown != preview1.rendered_markdown
    assert "Updated" in preview2.rendered_markdown


def test_get_frozen_snapshot_returns_cached(memory_dirs):
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# Data", encoding="utf-8")

    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    snap1 = resolver.get_frozen_snapshot()
    snap2 = resolver.get_frozen_snapshot()
    assert snap1.rendered_markdown == snap2.rendered_markdown


def test_new_instance_reads_latest(memory_dirs):
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# V1", encoding="utf-8")

    resolver1 = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    preview1 = resolver1.resolve_preview()

    memory_path.write_text("# V2", encoding="utf-8")

    resolver2 = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        include_workspace_memory=False,
    )
    preview2 = resolver2.resolve_preview()

    assert "V1" in preview1.rendered_markdown
    assert "V2" in preview2.rendered_markdown


def test_snapshot_with_workspace_scope(memory_dirs):
    user_dir, session_dir, workspace_dir = memory_dirs
    user_memory = get_user_memory_file_path(user_dir)
    user_memory.parent.mkdir(parents=True, exist_ok=True)
    user_memory.write_text("# Global", encoding="utf-8")

    ws_memory = get_workspace_memory_file_path(workspace_dir)
    ws_memory.parent.mkdir(parents=True, exist_ok=True)
    ws_memory.write_text("# Workspace", encoding="utf-8")

    resolver = MemoryResolver(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
        workspace_id="workspace-a",
        workspace_store=MemoryStore(ws_memory),
    )
    preview = resolver.resolve_preview()
    assert "Global" in preview.rendered_markdown
    assert "Workspace" in preview.rendered_markdown

    # 修改工作区文件，快照应复用
    ws_memory.write_text("# Modified Workspace", encoding="utf-8")
    preview2 = resolver.resolve_preview()
    assert "Modified" not in preview2.rendered_markdown


# ---------------------------------------------------------------------------
# resolve_session_memory_preview 模块级缓存测试
# ---------------------------------------------------------------------------


def test_resolve_session_memory_preview_uses_cache(memory_dirs):
    """同一 session 多次调用 resolve_session_memory_preview 应复用快照对象。"""
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# Original\nContent.", encoding="utf-8")

    preview1 = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
    )
    preview2 = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
    )
    assert preview1 is preview2
    assert "Original" in preview1.rendered_markdown


def test_resolve_session_memory_preview_refreshes_after_invalidation(memory_dirs):
    """文件变化后调用 invalidate_resolver_cache，下次 resolve 应读取最新内容。"""
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# Original", encoding="utf-8")

    preview1 = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
    )
    assert "Original" in preview1.rendered_markdown

    # 修改文件并显式失效缓存
    memory_path.write_text("# Updated", encoding="utf-8")
    invalidate_resolver_cache("user-1", "session-a")

    preview2 = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
    )
    assert preview2 is not preview1
    assert "Updated" in preview2.rendered_markdown


def test_resolve_session_memory_preview_cache_cleared_on_cleanup(memory_dirs):
    """模拟 session 结束清理：invalidate_resolver_cache 后再次 resolve 得到新对象。"""
    user_dir, session_dir, _workspace_dir = memory_dirs
    memory_path = get_user_memory_file_path(user_dir)
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory_path.write_text("# Data", encoding="utf-8")

    preview1 = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
    )

    # 模拟 session 结束时的缓存清理
    invalidate_resolver_cache("user-1", "session-a")

    preview2 = resolve_session_memory_preview(
        session_dir=session_dir,
        user_id="user-1",
        session_id="session-a",
    )
    assert preview2 is not preview1
    assert preview2.rendered_markdown == preview1.rendered_markdown
