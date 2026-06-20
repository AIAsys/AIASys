"""Memory resolve 预览。

直接读取用户默认层和工作区层 Markdown 文件，并拼接为运行态预览。
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from pathlib import Path

from app.core.config import WORKSPACE_DIR, get_user_global_memory_dir
from app.services.memory.constants import (
    MEMORY_FILE_NAME,
    MEMORY_SNAPSHOT_MIRROR_DIR_NAME,
    MEMORY_SUMMARY_FILE_NAME,
)
from app.services.memory.models import (
    MemoryScope,
    MemorySnapshotRecord,
    ResolvedMemoryPreview,
)
from app.services.memory.store import MemoryStore
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)


def _to_global_memory_path(source_dir: Path, *suffix: str) -> Path:
    """把 source_dir 映射到用户默认层 memory 目录；测试环境中保持隔离。"""
    source_dir = Path(source_dir).resolve()
    try:
        rel = source_dir.relative_to(WORKSPACE_DIR.resolve())
    except ValueError:
        return source_dir.joinpath(*suffix)
    if not rel.parts:
        return source_dir.joinpath(*suffix)
    user_id = rel.parts[0]
    rest = rel.parts[1:]
    return get_user_global_memory_dir(user_id).joinpath(*rest, *suffix)


_SCOPE_LABELS: dict[MemoryScope, str] = {
    MemoryScope.USER: "用户默认层",
    MemoryScope.WORKSPACE: "工作区层",
}


# ---------------------------------------------------------------------------
# Module-level resolver cache
# ---------------------------------------------------------------------------
_resolver_cache: dict[str, tuple[MemoryResolver, float]] = {}
_resolver_cache_lock = threading.Lock()
_RESOLVER_CACHE_TTL = 3600  # 1 hour


class MemoryResolver:
    """把纯文本 memory resolve 成统一预览。

    Frozen Snapshot：
    - 首次 resolve_preview() 时捕获快照并缓存
    - 会话中复用缓存，减少 I/O 并利用 prefix cache
    - 文件变化时通过 invalidate() 或重新实例化刷新
    """

    def __init__(
        self,
        *,
        session_dir: Path,
        user_id: str,
        session_id: str,
        user_store: MemoryStore | None = None,
        workspace_id: str | None = None,
        workspace_store: MemoryStore | None = None,
        include_user_default_memory: bool = True,
        include_workspace_memory: bool = True,
    ):
        self.session_dir = Path(session_dir)
        self.user_id = user_id
        self.session_id = session_id
        self.user_store = user_store or MemoryStore(
            get_user_memory_file_path(self.session_dir.parent)
        )
        self.workspace_id = workspace_id
        self.workspace_store = workspace_store
        self.include_user_default_memory = include_user_default_memory
        self.include_workspace_memory = include_workspace_memory
        # Frozen snapshot cache
        self._snapshot: ResolvedMemoryPreview | None = None
        self._snapshot_files_hash: str | None = None

    def resolve_preview(self) -> ResolvedMemoryPreview:
        """返回 memory 预览。首次调用时捕获快照，后续复用冻结内容。

        Frozen Snapshot 语义：会话中 snapshot 一旦捕获就不再自动刷新，
        只有显式调用 invalidate() 或重新实例化 MemoryResolver 才会重新读取文件。
        """
        if self._snapshot is not None:
            self._record_citation()
            return self._snapshot

        parts: list[str] = []

        if self._is_scope_enabled(MemoryScope.USER):
            user_text = self.user_store.read_text().strip()
            if user_text:
                parts.append(f"## {_SCOPE_LABELS[MemoryScope.USER]}")
                parts.append(user_text)

        if self._is_scope_enabled(MemoryScope.WORKSPACE):
            ws_text = self.workspace_store.read_text().strip() if self.workspace_store else ""
            if ws_text:
                parts.append(f"## {_SCOPE_LABELS[MemoryScope.WORKSPACE]}")
                parts.append(ws_text)

        rendered_markdown = "\n\n".join(parts)
        snapshot_hash = _compute_snapshot_hash(rendered_markdown)

        preview = ResolvedMemoryPreview(
            version=snapshot_hash,
            snapshot_hash=snapshot_hash,
            rendered_markdown=rendered_markdown,
        )
        self._snapshot = preview
        self._snapshot_files_hash = self._compute_files_hash()
        self._record_citation()
        return preview

    def _record_citation(self) -> None:
        """为当前会话的 Stage 1 产物记录一次引用（尽力而为）。"""

        try:
            from app.services.memory.pipeline import get_memory_state_runtime

            runtime = get_memory_state_runtime(user_id=self.user_id)
            runtime.record_citation(
                user_id=self.user_id,
                session_id=self.session_id,
            )
        except Exception:
            logger.warning("Failed to record memory citation", exc_info=True)

    def invalidate(self) -> None:
        """手动失效快照，下次 resolve_preview() 会重新读取文件。"""
        self._snapshot = None
        self._snapshot_files_hash = None
        if self.user_store is not None:
            self.user_store.invalidate_cache()
        if self.workspace_store is not None:
            self.workspace_store.invalidate_cache()

    def get_frozen_snapshot(self) -> ResolvedMemoryPreview:
        """获取当前冻结快照。如果尚未捕获，先调用 resolve_preview()。"""
        if self._snapshot is None:
            return self.resolve_preview()
        return self._snapshot

    def _compute_files_hash(self) -> str:
        """计算当前 memory 文件状态哈希，用于检测变化。"""
        import hashlib
        import struct

        hasher = hashlib.sha256()
        for store in (self.user_store, self.workspace_store):
            if store is None:
                hasher.update(b"\x00")
                continue
            try:
                stat = os.stat(as_system_path(store.file_path))
                hasher.update(struct.pack(">Q", stat.st_mtime_ns))
                hasher.update(struct.pack(">Q", stat.st_size))
            except OSError:
                hasher.update(b"\x00")
        return hasher.hexdigest()[:16]

    def _enabled_scopes(self) -> tuple[MemoryScope, ...]:
        scopes: list[MemoryScope] = []
        if self.include_user_default_memory:
            scopes.append(MemoryScope.USER)
        if (
            self.include_workspace_memory
            and self.workspace_id is not None
            and self.workspace_store is not None
        ):
            scopes.append(MemoryScope.WORKSPACE)
        return tuple(scopes)

    def _is_scope_enabled(self, scope: MemoryScope) -> bool:
        return scope in self._enabled_scopes()


def _compute_snapshot_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def get_user_memory_file_path(user_dir: Path) -> Path:
    """返回用户默认层 MEMORY.md 路径；不自动创建目录或文件。"""
    return _to_global_memory_path(user_dir) / MEMORY_FILE_NAME


def get_workspace_memory_file_path(workspace_dir: Path) -> Path:
    """工作区 Memory 本地路径：{workspace}/.aiasys/memory/workspace_memory.md"""
    local_path = workspace_dir / ".aiasys" / "memory" / "workspace_memory.md"
    os.makedirs(as_system_path(local_path.parent), exist_ok=True)
    return local_path


def get_workspace_memory_summary_file_path(workspace_dir: Path) -> Path:
    """工作区 Memory Summary 本地路径：{workspace}/.aiasys/memory/workspace_memory_summary.md"""
    local_path = workspace_dir / ".aiasys" / "memory" / "workspace_memory_summary.md"
    os.makedirs(as_system_path(local_path.parent), exist_ok=True)
    return local_path


def get_memory_snapshot_mirror_dir(session_dir: Path) -> Path:
    return _to_global_memory_path(session_dir, MEMORY_SNAPSHOT_MIRROR_DIR_NAME)


def get_user_memory_summary_path(user_dir: Path) -> Path:
    """返回用户级 L2 memory summary 路径；不自动创建目录或文件。"""
    return _to_global_memory_path(user_dir) / MEMORY_SUMMARY_FILE_NAME


def _get_memory_summary_path_if_exists(
    user_dir: Path,
) -> Path | None:
    """返回 summary 文件路径；如果不存在则返回 None。"""
    summary_path = get_user_memory_summary_path(user_dir)
    if os.path.exists(as_system_path(summary_path)):
        return summary_path
    return None


def _cleanup_expired_resolver_cache() -> None:
    """移除过期的 resolver 缓存条目。"""
    now = time.time()
    expired_keys = [
        key for key, (resolver, ts) in _resolver_cache.items() if now - ts > _RESOLVER_CACHE_TTL
    ]
    for key in expired_keys:
        entry = _resolver_cache.pop(key, None)
        if entry is not None:
            entry[0].invalidate()


def get_cached_resolver(
    *,
    session_dir: Path,
    user_id: str,
    session_id: str,
) -> MemoryResolver:
    """按 (user_id, session_id) 缓存 MemoryResolver 实例，复用 Frozen Snapshot。"""
    cache_key = f"{user_id}:{session_id}"
    with _resolver_cache_lock:
        _cleanup_expired_resolver_cache()
        entry = _resolver_cache.get(cache_key)
        if entry is not None:
            resolver, _ts = entry
            return resolver

    workspace_id, workspace_store = resolve_workspace_memory_context(
        session_dir=Path(session_dir),
        user_id=user_id,
        session_id=session_id,
    )
    resolver = MemoryResolver(
        session_dir=Path(session_dir),
        user_id=user_id,
        session_id=session_id,
        user_store=MemoryStore(get_user_memory_file_path(Path(session_dir).parent)),
        workspace_id=workspace_id,
        workspace_store=workspace_store,
    )

    with _resolver_cache_lock:
        _cleanup_expired_resolver_cache()
        existing = _resolver_cache.get(cache_key)
        if existing is not None:
            return existing[0]
        _resolver_cache[cache_key] = (resolver, time.time())
        return resolver


def invalidate_resolver_cache(user_id: str, session_id: str) -> None:
    """清理指定 session 的缓存，下次调用 get_cached_resolver 会重新创建实例。"""
    cache_key = f"{user_id}:{session_id}"
    with _resolver_cache_lock:
        entry = _resolver_cache.pop(cache_key, None)
    if entry is not None:
        entry[0].invalidate()


def invalidate_user_resolver_cache(user_id: str) -> None:
    """清理某个用户的所有 resolver 缓存。"""

    prefix = f"{user_id}:"
    with _resolver_cache_lock:
        items = [
            (key, resolver)
            for key, (resolver, _ts) in _resolver_cache.items()
            if key.startswith(prefix)
        ]
        for key, _resolver in items:
            _resolver_cache.pop(key, None)
    for _key, resolver in items:
        resolver.invalidate()


def resolve_session_memory_preview(
    *,
    session_dir: Path,
    user_id: str,
    session_id: str,
) -> ResolvedMemoryPreview:
    resolver = get_cached_resolver(
        session_dir=Path(session_dir),
        user_id=user_id,
        session_id=session_id,
    )
    return resolver.resolve_preview()


def resolve_workspace_memory_context(
    *,
    session_dir: Path,
    user_id: str,
    session_id: str,
) -> tuple[str | None, MemoryStore | None]:
    from app.services.workspace_registry import WorkspaceRegistryService

    registry = WorkspaceRegistryService(Path(session_dir).parent.parent)
    workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
    if workspace_id is None:
        return None, None

    workspace_root = registry.get_workspace_root(user_id, workspace_id)
    return workspace_id, MemoryStore(get_workspace_memory_file_path(workspace_root))


def persist_memory_preview_snapshot(
    *,
    session_dir: Path,
    user_id: str,
    session_id: str,
    preview: ResolvedMemoryPreview,
) -> MemorySnapshotRecord | None:
    if not preview.rendered_markdown.strip():
        return None

    store = MemoryStore(get_user_memory_file_path(Path(session_dir).parent))
    workspace_id, workspace_store = resolve_workspace_memory_context(
        session_dir=Path(session_dir),
        user_id=user_id,
        session_id=session_id,
    )
    workspace_markdown = ""
    if workspace_store is not None:
        workspace_markdown = workspace_store.read_text()
    snapshot = MemorySnapshotRecord(
        id=f"memsnap_{session_id}_{preview.snapshot_hash}",
        user_id=user_id,
        workspace_id=workspace_id,
        session_id=session_id,
        version=preview.version,
        snapshot_hash=preview.snapshot_hash,
        system_markdown="",
        user_markdown=preview.rendered_markdown,
        workspace_markdown=workspace_markdown,
    )
    store.save_snapshot(snapshot)

    mirror_dir = get_memory_snapshot_mirror_dir(Path(session_dir))
    os.makedirs(as_system_path(mirror_dir), exist_ok=True)
    mirror_path = mirror_dir / f"{snapshot.id}.md"
    Path(as_system_path(mirror_path)).write_text(preview.rendered_markdown, encoding="utf-8")
    return snapshot
