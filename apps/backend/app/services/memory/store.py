"""Markdown-backed memory 主存储。

只提供文件读写、原子写入和跨平台文件锁。
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from filelock import FileLock

from app.services.memory.models import MemorySnapshotRecord
from app.services.memory.security import scan_memory_content

logger = logging.getLogger(__name__)


def _atomic_write_text(path: Path, content: str) -> None:
    """同目录临时文件 + fsync + os.replace，避免半写文件。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
        text=True,
    )
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
        if os.name != "nt":
            try:
                dir_fd = os.open(path.parent, os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


class MemorySecurityError(ValueError):
    """Memory 内容未通过安全扫描时抛出的异常。"""


class MemoryCapacityError(ValueError):
    """Memory 文件大小超过容量限制时抛出的异常。"""


class MemoryStore:
    """Markdown-backed memory 主存储（纯文本版）。"""

    def __init__(self, file_path: Path):
        self.file_path = Path(file_path)
        if self.file_path.suffix != ".md":
            raise ValueError("MemoryStore 只接受 Markdown memory 文件路径")
        self._snapshots_path = self.file_path.with_suffix(".snapshots.json")
        self._lock_path = self.file_path.with_suffix(self.file_path.suffix + ".lock")
        self._cache_text: str | None = None
        self._cache_mtime_ns: int | None = None
        self._dirty = False

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    @contextmanager
    def _file_lock(self):
        with FileLock(str(self._lock_path)):
            yield

    # ------------------------------------------------------------------
    # 纯文本读写
    # ------------------------------------------------------------------

    def read_text(self) -> str:
        """读取文件内容，不存在则返回空字符串。"""
        if not self.file_path.exists():
            self._cache_text = ""
            self._cache_mtime_ns = None
            self._dirty = False
            return ""
        with self._file_lock():
            try:
                mtime_ns = self.file_path.stat().st_mtime_ns
            except OSError:
                self._cache_text = ""
                self._cache_mtime_ns = None
                self._dirty = False
                return ""
            if (
                not self._dirty
                and self._cache_text is not None
                and self._cache_mtime_ns == mtime_ns
            ):
                return self._cache_text
            text = self.file_path.read_text(encoding="utf-8")
            self._cache_text = text
            self._cache_mtime_ns = mtime_ns
            self._dirty = False
            return text

    def write_text(
        self, content: str, *, skip_security_scan: bool = False, max_size: int | None = None
    ) -> None:
        """原子写入文件内容。

        Args:
            content: 要写入的内容。
            skip_security_scan: 为 True 时跳过安全扫描（仅内部重建镜像时使用）。
            max_size: 容量限制（字符数）。为 None 时不做容量检查。

        Raises:
            MemorySecurityError: 检测到威胁内容时拒绝写入。
            MemoryCapacityError: 内容大小超过 max_size 时拒绝写入。
        """
        if max_size is not None and len(content) > max_size:
            raise MemoryCapacityError(
                f"Memory 文件大小超过限制（{len(content)}/{max_size} chars），"
                "请触发 consolidation 或手动清理"
            )

        if not skip_security_scan:
            result = scan_memory_content(content)
            if result.blocked:
                threat_types = {t["type"] for t in result.threats}
                logger.warning(
                    "Memory 安全扫描拦截写入: file=%s threats=%s",
                    self.file_path,
                    threat_types,
                )
                raise MemorySecurityError(f"检测到安全威胁: {', '.join(threat_types)}")

        self._dirty = True
        with self._file_lock():
            _atomic_write_text(self.file_path, content)
            try:
                self._cache_mtime_ns = self.file_path.stat().st_mtime_ns
            except OSError:
                self._cache_mtime_ns = None
            self._cache_text = content
            self._dirty = False

    def update_text(
        self,
        mutator: Callable[[str], str],
        *,
        skip_security_scan: bool = False,
        max_size: int | None = None,
    ) -> str:
        """在同一把文件锁内完成 read-modify-write。

        Args:
            mutator: 接收旧内容，返回新内容。
            skip_security_scan: 为 True 时跳过安全扫描（仅内部镜像重建使用）。
            max_size: 容量限制（字符数）。为 None 时不做容量检查。

        Returns:
            写入后的新内容。
        """

        self._dirty = True
        with self._file_lock():
            try:
                try:
                    existing = self.file_path.read_text(encoding="utf-8")
                except FileNotFoundError:
                    existing = ""

                content = mutator(existing)
                if max_size is not None and len(content) > max_size:
                    raise MemoryCapacityError(
                        f"Memory 文件大小超过限制（{len(content)}/{max_size} chars），"
                        "请触发 consolidation 或手动清理"
                    )

                if not skip_security_scan:
                    result = scan_memory_content(content)
                    if result.blocked:
                        threat_types = {t["type"] for t in result.threats}
                        logger.warning(
                            "Memory 安全扫描拦截写入: file=%s threats=%s",
                            self.file_path,
                            threat_types,
                        )
                        raise MemorySecurityError(f"检测到安全威胁: {', '.join(threat_types)}")

                _atomic_write_text(self.file_path, content)
                try:
                    self._cache_mtime_ns = self.file_path.stat().st_mtime_ns
                except OSError:
                    self._cache_mtime_ns = None
                self._cache_text = content
                self._dirty = False
                return content
            except Exception:
                self._dirty = False
                raise

    def invalidate_cache(self) -> None:
        """强制失效读缓存，下次 read_text() 重新读取文件。"""
        self._cache_text = None
        self._cache_mtime_ns = None
        self._dirty = False

    def exists(self) -> bool:
        return self.file_path.exists()

    def initialize(self) -> None:
        """确保文件存在（空文件）。"""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            with self._file_lock():
                if not self.file_path.exists():
                    _atomic_write_text(self.file_path, "")
                    self._cache_text = ""
                    try:
                        self._cache_mtime_ns = self.file_path.stat().st_mtime_ns
                    except OSError:
                        self._cache_mtime_ns = None
                    self._dirty = False

    # ------------------------------------------------------------------
    # Snapshots（保留，用于版本漂移检测）
    # ------------------------------------------------------------------

    def save_snapshot(self, snapshot: MemorySnapshotRecord) -> MemorySnapshotRecord:
        with self._file_lock():
            snapshots = self._load_snapshots()
            snapshots = [item for item in snapshots if str(item.get("id") or "") != snapshot.id]
            snapshots.append(snapshot.model_dump(mode="json"))
            # 限制保留最近 50 个 snapshot，防止文件无限增长
            max_snapshots = 50
            if len(snapshots) > max_snapshots:
                snapshots = snapshots[-max_snapshots:]
            _atomic_write_text(
                self._snapshots_path,
                json.dumps(snapshots, ensure_ascii=False, indent=2),
            )
        return snapshot

    def _load_snapshots(self) -> list[dict[str, object]]:
        if not self._snapshots_path.exists():
            return []
        try:
            data = json.loads(self._snapshots_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
