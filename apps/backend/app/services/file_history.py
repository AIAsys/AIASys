"""轻量文件历史服务。

这个服务保存文件改动前的真实内容副本，不依赖 Git。
历史数据放在工作区自己的 `.aiasys/file-history/` 目录下。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import filelock

from app.core.encoding_utils import smart_decode
from app.services.diff_service import FileDiffResult, diff_service
from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

FileHistoryOperation = Literal[
    "before_update",
    "before_overwrite",
    "before_delete",
    "before_move",
    "before_restore",
]


@dataclass(slots=True)
class ChangeEvent:
    """一次变更事件，由相近时间内的多个文件历史条目聚合而成。"""

    id: str
    timestamp: str
    source: str
    source_detail: str | None
    operation: FileHistoryOperation
    files: list[FileHistoryEntry]


DEFAULT_MAX_FILE_SIZE = 2 * 1024 * 1024
DEFAULT_MAX_ENTRIES_PER_FILE = 50
HISTORY_DIR = Path(".aiasys/file-history")
HISTORY_INDEX = "index.json"
HISTORY_ENTRIES_DIR = "entries"
EXCLUDED_TOP_LEVEL_NAMES = {
    ".aiasys",
    ".env",
    ".git",
    ".ipynb_checkpoints",
    "__pycache__",
    "node_modules",
}


@dataclass(slots=True)
class FileHistoryEntry:
    id: str
    file_path: str
    timestamp: str
    operation: FileHistoryOperation
    source: str
    size: int
    sha256: str
    stored_path: str
    source_detail: str | None = None
    target_path: str | None = None


class FileHistoryService:
    def __init__(
        self,
        *,
        max_file_size: int = DEFAULT_MAX_FILE_SIZE,
        max_entries_per_file: int = DEFAULT_MAX_ENTRIES_PER_FILE,
    ) -> None:
        self.max_file_size = max_file_size
        self.max_entries_per_file = max_entries_per_file
        self._lock_cache: dict[str, filelock.FileLock] = {}

    def _get_index_lock(self, workspace_root: Path) -> filelock.FileLock:
        lock_path = self._history_root(workspace_root) / "index.lock"
        key = str(lock_path)
        lock = self._lock_cache.get(key)
        if lock is None:
            lock = filelock.FileLock(as_system_path(lock_path))
            self._lock_cache[key] = lock
        return lock

    def list_entries(self, workspace_root: Path, file_path: str) -> list[FileHistoryEntry]:
        normalized_path = self._normalize_relative_path(file_path)
        with self._get_index_lock(workspace_root):
            entries = [
                entry
                for entry in self._read_entries(workspace_root)
                if entry.file_path == normalized_path
            ]
        return sorted(entries, key=lambda entry: entry.timestamp, reverse=True)

    def list_recent_changes(
        self, workspace_root: Path, *, limit: int = 50
    ) -> list[tuple[str, FileHistoryEntry, int]]:
        """返回最近变更的文件列表。

        返回 (file_path, latest_entry, total_versions) 三元组，按 latest_entry.timestamp 倒序排列。
        """
        with self._get_index_lock(workspace_root):
            all_entries = self._read_entries(workspace_root)
        # 按 file_path 分组，取每组最新的 entry
        by_path: dict[str, list[FileHistoryEntry]] = {}
        for entry in all_entries:
            by_path.setdefault(entry.file_path, []).append(entry)
        result: list[tuple[str, FileHistoryEntry, int]] = []
        for file_path, entries in by_path.items():
            latest = max(entries, key=lambda e: e.timestamp)
            result.append((file_path, latest, len(entries)))
        result.sort(key=lambda item: item[1].timestamp, reverse=True)
        return result[:limit]

    def list_change_events(
        self,
        workspace_root: Path,
        *,
        limit: int = 50,
        time_window_seconds: int = 120,
    ) -> list[ChangeEvent]:
        """返回变更事件列表，按时间倒序排列。

        将时间相近（默认 120 秒内）的历史条目聚合为一个事件，方便查看"同一批次"的变更。
        """
        with self._get_index_lock(workspace_root):
            all_entries = self._read_entries(workspace_root)

        if not all_entries:
            return []

        sorted_entries = sorted(all_entries, key=lambda e: e.timestamp, reverse=True)
        events: list[ChangeEvent] = []
        current_group: list[FileHistoryEntry] = []

        def _flush_group() -> None:
            if not current_group:
                return
            first = current_group[0]
            events.append(
                ChangeEvent(
                    id=first.id,
                    timestamp=first.timestamp,
                    source=first.source,
                    source_detail=first.source_detail,
                    operation=first.operation,
                    files=list(current_group),
                )
            )
            current_group.clear()

        for entry in sorted_entries:
            if not current_group:
                current_group.append(entry)
                continue
            last = current_group[-1]
            last_dt = datetime.fromisoformat(last.timestamp.replace("Z", "+00:00"))
            entry_dt = datetime.fromisoformat(entry.timestamp.replace("Z", "+00:00"))
            delta = (last_dt - entry_dt).total_seconds()
            if 0 <= delta <= time_window_seconds:
                current_group.append(entry)
            else:
                _flush_group()
                current_group.append(entry)
        _flush_group()

        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def get_entry(self, workspace_root: Path, entry_id: str) -> FileHistoryEntry:
        with self._get_index_lock(workspace_root):
            for entry in self._read_entries(workspace_root):
                if entry.id == entry_id:
                    return entry
        raise FileNotFoundError("历史记录不存在")

    def read_entry_bytes(
        self, workspace_root: Path, entry_id: str
    ) -> tuple[FileHistoryEntry, bytes]:
        entry = self.get_entry(workspace_root, entry_id)
        stored_path = self._history_root(workspace_root) / entry.stored_path
        stored_sys_path = as_system_path(stored_path)
        if not os.path.exists(stored_sys_path) or not os.path.isfile(stored_sys_path):
            raise FileNotFoundError("历史内容不存在")
        with open(stored_sys_path, "rb") as f:
            return entry, f.read()

    def read_entry_text(self, workspace_root: Path, entry_id: str) -> tuple[FileHistoryEntry, str]:
        entry, content = self.read_entry_bytes(workspace_root, entry_id)
        decoded = smart_decode(content)
        if "\ufffd" in decoded and decoded.count("\ufffd") / max(len(decoded), 1) > 0.1:
            raise ValueError("历史内容不是有效的文本文件")
        return entry, decoded

    def diff_entry(self, workspace_root: Path, entry_id: str) -> tuple[FileHistoryEntry, bool, str]:
        entry, result = self.diff_entry_result(workspace_root, entry_id)
        return entry, result.right_exists, result.unified_diff

    def diff_entry_result(
        self, workspace_root: Path, entry_id: str
    ) -> tuple[FileHistoryEntry, FileDiffResult]:
        entry = self.get_entry(workspace_root, entry_id)
        stored_path = self._history_root(workspace_root) / entry.stored_path
        stored_sys_path = as_system_path(stored_path)
        if not os.path.exists(stored_sys_path) or not os.path.isfile(stored_sys_path):
            raise FileNotFoundError("历史内容不存在")
        current_path = self._resolve_workspace_path(workspace_root, entry.file_path)
        result = diff_service.compare_files(
            stored_path,
            current_path,
            left_label=f"history/{entry.file_path}",
            right_label=f"current/{entry.file_path}",
        )
        return entry, result

    def record_file_before_change(
        self,
        workspace_root: Path,
        file_path: str,
        *,
        operation: FileHistoryOperation,
        source: str,
        source_detail: str | None = None,
        target_path: str | None = None,
    ) -> FileHistoryEntry | None:
        normalized_path = self._normalize_relative_path(file_path)
        target = self._normalize_relative_path(target_path) if target_path is not None else None
        if self._should_skip(normalized_path):
            return None

        absolute_path = self._resolve_workspace_path(workspace_root, normalized_path)
        abs_sys_path = as_system_path(absolute_path)
        if (
            not os.path.exists(abs_sys_path)
            or not os.path.isfile(abs_sys_path)
            or os.path.islink(abs_sys_path)
        ):
            return None

        size = os.path.getsize(abs_sys_path)
        if size > self.max_file_size:
            logger.info("跳过文件历史记录，文件过大: %s", normalized_path)
            return None

        with open(abs_sys_path, "rb") as f:
            content = f.read()
        digest = hashlib.sha256(content).hexdigest()

        with self._get_index_lock(workspace_root):
            entries = self._read_entries(workspace_root)
            if operation in {"before_update", "before_overwrite"}:
                latest = self._latest_entry_for_path(entries, normalized_path)
                if latest is not None and latest.sha256 == digest:
                    return None

            entry_id = self._new_entry_id()
            stored_relative = self._stored_relative_path(entry_id, normalized_path)
            history_root = self._history_root(workspace_root)
            stored_absolute = history_root / stored_relative
            os.makedirs(as_system_path(stored_absolute.parent), exist_ok=True)
            with open(as_system_path(stored_absolute), "wb") as f:
                f.write(content)

            entry = FileHistoryEntry(
                id=entry_id,
                file_path=normalized_path,
                timestamp=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                operation=operation,
                source=source,
                source_detail=source_detail,
                size=size,
                sha256=digest,
                stored_path=stored_relative.as_posix(),
                target_path=target,
            )
            entries.append(entry)
            entries = self._prune_entries(workspace_root, entries, normalized_path)
            self._write_entries(workspace_root, entries)
            return entry

    def record_tree_before_change(
        self,
        workspace_root: Path,
        file_path: str,
        *,
        operation: FileHistoryOperation,
        source: str,
        source_detail: str | None = None,
        target_path: str | None = None,
    ) -> list[FileHistoryEntry]:
        normalized_path = self._normalize_relative_path(file_path)
        workspace_root = workspace_root.resolve()
        absolute_path = self._resolve_workspace_path(workspace_root, normalized_path)
        abs_sys_path = as_system_path(absolute_path)
        if not os.path.exists(abs_sys_path):
            return []
        if os.path.isfile(abs_sys_path):
            entry = self.record_file_before_change(
                workspace_root,
                normalized_path,
                operation=operation,
                source=source,
                source_detail=source_detail,
                target_path=target_path,
            )
            return [entry] if entry is not None else []
        if not os.path.isdir(abs_sys_path) or os.path.islink(abs_sys_path):
            return []

        entries: list[FileHistoryEntry] = []
        target_prefix = (
            self._normalize_relative_path(target_path) if target_path is not None else None
        )
        walk_root = as_system_path(absolute_path)
        workspace_sys_root = as_system_path(workspace_root)
        absolute_sys_path = as_system_path(absolute_path)
        for current_dir, dir_names, file_names in os.walk(walk_root, topdown=True):
            current_path = Path(current_dir)
            rel_parts = current_path.relative_to(workspace_sys_root).parts
            if any(part in EXCLUDED_TOP_LEVEL_NAMES for part in rel_parts):
                dir_names[:] = []
                continue
            dir_names[:] = sorted(
                d
                for d in dir_names
                if d not in EXCLUDED_TOP_LEVEL_NAMES
                and not os.path.islink(as_system_path(current_path / d))
            )
            for file_name in sorted(file_names):
                file_path = current_path / file_name
                file_sys_path = as_system_path(file_path)
                if os.path.islink(file_sys_path) or not os.path.isfile(file_sys_path):
                    continue
                relative_child = file_path.relative_to(workspace_sys_root).as_posix()
                child_target = None
                if target_prefix is not None:
                    child_suffix = file_path.relative_to(absolute_sys_path).as_posix()
                    child_target = (Path(target_prefix) / child_suffix).as_posix()
                entry = self.record_file_before_change(
                    workspace_root,
                    relative_child,
                    operation=operation,
                    source=source,
                    source_detail=source_detail,
                    target_path=child_target,
                )
                if entry is not None:
                    entries.append(entry)
        return entries

    def move_entries(
        self,
        workspace_root: Path,
        source_path: str,
        target_path: str,
    ) -> None:
        normalized_source = self._normalize_relative_path(source_path)
        normalized_target = self._normalize_relative_path(target_path)
        with self._get_index_lock(workspace_root):
            entries = self._read_entries(workspace_root)
            changed = False
            for entry in entries:
                moved_path = self._move_path(entry.file_path, normalized_source, normalized_target)
                if moved_path is not None:
                    entry.file_path = moved_path
                    changed = True
            if changed:
                self._write_entries(workspace_root, entries)

    def cleanup_orphan_stores(self, workspace_root: Path) -> int:
        """删除不在 index 中引用的存储文件，返回删除数量。"""
        history_root = self._history_root(workspace_root)
        entries_dir = history_root / HISTORY_ENTRIES_DIR
        if not os.path.exists(as_system_path(entries_dir)):
            return 0

        with self._get_index_lock(workspace_root):
            entries = self._read_entries(workspace_root)
            referenced = {entry.stored_path for entry in entries}
            removed = 0
            for item in entries_dir.iterdir():
                item_sys_path = as_system_path(item)
                if not os.path.isfile(item_sys_path):
                    continue
                relative = item.relative_to(history_root).as_posix()
                if relative not in referenced:
                    os.unlink(item_sys_path)
                    removed += 1
            return removed

    def restore_entry(
        self,
        workspace_root: Path,
        entry_id: str,
        *,
        source: str,
        source_detail: str | None = None,
    ) -> tuple[FileHistoryEntry, int]:
        entry, content = self.read_entry_bytes(workspace_root, entry_id)
        target_path = self._resolve_workspace_path(workspace_root, entry.file_path)
        target_sys_path = as_system_path(target_path)
        if os.path.exists(target_sys_path) and os.path.isfile(target_sys_path):
            self.record_file_before_change(
                workspace_root,
                entry.file_path,
                operation="before_restore",
                source=source,
                source_detail=source_detail or entry_id,
            )
        os.makedirs(as_system_path(target_path.parent), exist_ok=True)
        with open(target_sys_path, "wb") as f:
            f.write(content)
        return entry, len(content)

    def _history_root(self, workspace_root: Path) -> Path:
        return workspace_root / HISTORY_DIR

    def _index_path(self, workspace_root: Path) -> Path:
        return self._history_root(workspace_root) / HISTORY_INDEX

    def _resolve_workspace_path(self, workspace_root: Path, relative_path: str) -> Path:
        normalized_path = self._normalize_relative_path(relative_path)
        root = workspace_root.resolve()
        target = (root / normalized_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError("无效的文件路径") from exc
        return target

    def _normalize_relative_path(self, relative_path: str | Path) -> str:
        normalized = Path(str(relative_path).replace("\\", "/"))
        if (
            not str(relative_path).strip()
            or normalized.is_absolute()
            or any(part == ".." for part in normalized.parts)
        ):
            raise ValueError("无效的文件路径")
        return normalized.as_posix()

    def _should_skip(self, relative_path: str) -> bool:
        parts = Path(relative_path).parts
        if not parts:
            return True
        return any(part in EXCLUDED_TOP_LEVEL_NAMES for part in parts)

    def _read_entries(self, workspace_root: Path) -> list[FileHistoryEntry]:
        index_path = self._index_path(workspace_root)
        index_sys_path = as_system_path(index_path)
        if not os.path.exists(index_sys_path):
            return []
        try:
            with open(index_sys_path, encoding="utf-8") as f:
                payload = json.loads(f.read())
        except (json.JSONDecodeError, OSError):
            logger.warning("文件历史索引无法读取，按空索引处理: %s", index_path)
            return []
        raw_entries = payload.get("entries", [])
        if not isinstance(raw_entries, list):
            return []
        entries: list[FileHistoryEntry] = []
        for raw_entry in raw_entries:
            if not isinstance(raw_entry, dict):
                continue
            try:
                entries.append(FileHistoryEntry(**raw_entry))
            except TypeError:
                continue
        return entries

    def _write_entries(self, workspace_root: Path, entries: list[FileHistoryEntry]) -> None:
        index_path = self._index_path(workspace_root)
        os.makedirs(as_system_path(index_path.parent), exist_ok=True)
        temp_path = index_path.with_suffix(".tmp")
        temp_sys_path = as_system_path(temp_path)
        payload = {
            "version": 1,
            "updated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "entries": [asdict(entry) for entry in entries],
        }
        try:
            with open(temp_sys_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False, indent=2))
            os.replace(temp_sys_path, as_system_path(index_path))
        except Exception:
            try:
                os.remove(temp_sys_path)
            except OSError:
                logger.warning("Failed to clean up temp file: %s", temp_sys_path)
            raise

    def _latest_entry_for_path(
        self,
        entries: list[FileHistoryEntry],
        file_path: str,
    ) -> FileHistoryEntry | None:
        matches = [entry for entry in entries if entry.file_path == file_path]
        if not matches:
            return None
        return max(matches, key=lambda entry: entry.timestamp)

    def _prune_entries(
        self,
        workspace_root: Path,
        entries: list[FileHistoryEntry],
        file_path: str,
    ) -> list[FileHistoryEntry]:
        same_file = sorted(
            [entry for entry in entries if entry.file_path == file_path],
            key=lambda entry: entry.timestamp,
            reverse=True,
        )
        keep_ids = {entry.id for entry in same_file[: self.max_entries_per_file]}
        pruned: list[FileHistoryEntry] = []
        history_root = self._history_root(workspace_root)
        for entry in entries:
            if entry.file_path == file_path and entry.id not in keep_ids:
                stored_path = history_root / entry.stored_path
                try:
                    os.unlink(as_system_path(stored_path))
                except OSError:
                    logger.warning("Failed to remove pruned history file: %s", stored_path)
                continue
            pruned.append(entry)
        return pruned

    def _stored_relative_path(self, entry_id: str, file_path: str) -> Path:
        suffix = Path(file_path).suffix
        if not suffix or len(suffix) > 16:
            suffix = ".bin"
        return Path(HISTORY_ENTRIES_DIR) / f"{entry_id}{suffix}"

    def _new_entry_id(self) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        return f"fh_{timestamp}_{secrets.token_hex(6)}"

    def _move_path(
        self,
        current_path: str,
        source_path: str,
        target_path: str,
    ) -> str | None:
        if current_path == source_path:
            return target_path
        source_prefix = f"{source_path}/"
        if current_path.startswith(source_prefix):
            suffix = current_path[len(source_prefix) :]
            return f"{target_path}/{suffix}"
        return None


file_history_service = FileHistoryService()
