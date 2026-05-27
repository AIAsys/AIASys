"""通用差异对比服务。"""

from __future__ import annotations

import difflib
import hashlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DiffStatus = Literal["added", "deleted", "modified", "unchanged", "skipped"]

DEFAULT_MAX_DIFF_FILE_SIZE = 2 * 1024 * 1024
DEFAULT_MAX_DIRECTORY_FILES = 1000
DEFAULT_EXCLUDED_DIR_NAMES = {".git", "__pycache__", "node_modules"}
_HUNK_RE = re.compile(r"@@ -(?P<left>\d+)(?:,\d+)? \+(?P<right>\d+)(?:,\d+)? @@")


class DiffTooLargeError(ValueError):
    """目录或文件超过差异对比限制。"""


@dataclass(slots=True)
class DiffStats:
    additions: int = 0
    deletions: int = 0
    left_lines: int = 0
    right_lines: int = 0


@dataclass(slots=True)
class TextDiffResult:
    left_label: str
    right_label: str
    left_text: str | None
    right_text: str | None
    unified_diff: str
    status: DiffStatus
    stats: DiffStats
    format: Literal["unified"] = "unified"
    can_show_content: bool = True
    skip_reason: str | None = None


@dataclass(slots=True)
class FileDiffResult:
    left_label: str
    right_label: str
    status: DiffStatus
    left_exists: bool
    right_exists: bool
    left_size: int | None
    right_size: int | None
    left_sha256: str | None
    right_sha256: str | None
    unified_diff: str
    stats: DiffStats
    format: Literal["unified"] = "unified"
    can_show_content: bool = True
    skip_reason: str | None = None
    is_binary: bool = False
    is_too_large: bool = False
    left_text: str | None = None
    right_text: str | None = None


@dataclass(slots=True)
class DirectoryDiffEntry:
    path: str
    status: DiffStatus
    left_size: int | None = None
    right_size: int | None = None
    left_sha256: str | None = None
    right_sha256: str | None = None


@dataclass(slots=True)
class DirectoryDiffResult:
    left_label: str
    right_label: str
    files: list[DirectoryDiffEntry]
    counts: dict[str, int]
    total_files: int
    included_files: int
    include_unchanged: bool
    max_files: int


@dataclass(slots=True)
class _FileProbe:
    exists: bool
    is_file: bool
    is_symlink: bool
    size: int | None = None
    sha256: str | None = None
    content: bytes | None = None
    is_binary: bool = False
    is_too_large: bool = False
    skip_reason: str | None = None


@dataclass(slots=True)
class _DirectorySnapshot:
    files: dict[str, DirectoryDiffEntry] = field(default_factory=dict)


class DiffService:
    def __init__(
        self,
        *,
        max_file_size: int = DEFAULT_MAX_DIFF_FILE_SIZE,
        max_directory_files: int = DEFAULT_MAX_DIRECTORY_FILES,
    ) -> None:
        self.max_file_size = max_file_size
        self.max_directory_files = max_directory_files

    def compare_text(
        self,
        left_text: str,
        right_text: str,
        *,
        left_label: str = "left",
        right_label: str = "right",
        include_text: bool = True,
    ) -> TextDiffResult:
        unified_diff = self._unified_diff(
            left_text,
            right_text,
            left_label=left_label,
            right_label=right_label,
        )
        status: DiffStatus = "unchanged" if left_text == right_text else "modified"
        stats = self._stats_from_unified_diff(
            unified_diff,
            left_text=left_text,
            right_text=right_text,
        )
        return TextDiffResult(
            left_label=left_label,
            right_label=right_label,
            left_text=left_text if include_text else None,
            right_text=right_text if include_text else None,
            unified_diff=unified_diff,
            status=status,
            stats=stats,
        )

    def compare_files(
        self,
        left_path: Path,
        right_path: Path,
        *,
        left_label: str | None = None,
        right_label: str | None = None,
        include_text: bool = True,
    ) -> FileDiffResult:
        left = self._probe_file(left_path)
        right = self._probe_file(right_path)
        resolved_left_label = left_label or left_path.as_posix()
        resolved_right_label = right_label or right_path.as_posix()

        status = self._status_from_probe(left, right)
        if left.skip_reason or right.skip_reason:
            return self._skipped_file_result(
                left,
                right,
                status=status,
                left_label=resolved_left_label,
                right_label=resolved_right_label,
            )

        left_text, left_error = self._decode_content(left.content)
        right_text, right_error = self._decode_content(right.content)
        if left_error or right_error:
            reason = left_error or right_error
            return self._skipped_file_result(
                left,
                right,
                status=status,
                left_label=resolved_left_label,
                right_label=resolved_right_label,
                skip_reason=reason,
            )

        text_result = self.compare_text(
            left_text or "",
            right_text or "",
            left_label=resolved_left_label,
            right_label=resolved_right_label,
            include_text=include_text,
        )
        return FileDiffResult(
            left_label=resolved_left_label,
            right_label=resolved_right_label,
            status=status,
            left_exists=left.exists,
            right_exists=right.exists,
            left_size=left.size,
            right_size=right.size,
            left_sha256=left.sha256,
            right_sha256=right.sha256,
            unified_diff=text_result.unified_diff,
            stats=text_result.stats,
            left_text=text_result.left_text,
            right_text=text_result.right_text,
        )

    def compare_directories(
        self,
        left_root: Path,
        right_root: Path,
        *,
        left_label: str | None = None,
        right_label: str | None = None,
        include_unchanged: bool = False,
        max_files: int | None = None,
    ) -> DirectoryDiffResult:
        limit = max_files or self.max_directory_files
        left_snapshot = self._scan_directory(left_root, max_files=limit)
        right_snapshot = self._scan_directory(right_root, max_files=limit)
        all_paths = sorted(set(left_snapshot.files) | set(right_snapshot.files))
        if len(all_paths) > limit:
            raise DiffTooLargeError(f"目录文件数量超过限制: {limit}")

        counts = {
            "added": 0,
            "deleted": 0,
            "modified": 0,
            "unchanged": 0,
            "skipped": 0,
        }
        files: list[DirectoryDiffEntry] = []
        for relative_path in all_paths:
            left = left_snapshot.files.get(relative_path)
            right = right_snapshot.files.get(relative_path)
            status = self._directory_entry_status(left, right)
            counts[status] += 1
            if status == "unchanged" and not include_unchanged:
                continue
            files.append(
                DirectoryDiffEntry(
                    path=relative_path,
                    status=status,
                    left_size=left.left_size if left else None,
                    right_size=right.right_size if right else None,
                    left_sha256=left.left_sha256 if left else None,
                    right_sha256=right.right_sha256 if right else None,
                )
            )

        return DirectoryDiffResult(
            left_label=left_label or left_root.as_posix(),
            right_label=right_label or right_root.as_posix(),
            files=files,
            counts=counts,
            total_files=len(all_paths),
            included_files=len(files),
            include_unchanged=include_unchanged,
            max_files=limit,
        )

    def _probe_file(self, path: Path) -> _FileProbe:
        if not path.exists():
            return _FileProbe(exists=False, is_file=False, is_symlink=False)
        if path.is_symlink():
            return _FileProbe(
                exists=True,
                is_file=False,
                is_symlink=True,
                skip_reason="符号链接不参与内容对比",
            )
        if not path.is_file():
            return _FileProbe(
                exists=True,
                is_file=False,
                is_symlink=False,
                skip_reason="路径不是文件",
            )

        size = path.stat().st_size
        digest = self._sha256_file(path)
        is_too_large = size > self.max_file_size
        with path.open("rb") as file:
            head = file.read(4096)
        is_binary = self._looks_binary(head)
        if is_too_large:
            return _FileProbe(
                exists=True,
                is_file=True,
                is_symlink=False,
                size=size,
                sha256=digest,
                is_binary=is_binary,
                is_too_large=True,
                skip_reason=f"文件超过 {self.max_file_size} 字节限制",
            )
        content = path.read_bytes()
        return _FileProbe(
            exists=True,
            is_file=True,
            is_symlink=False,
            size=size,
            sha256=digest,
            content=content,
            is_binary=is_binary,
            is_too_large=False,
        )

    def _scan_directory(self, root: Path, *, max_files: int) -> _DirectorySnapshot:
        if not root.exists():
            raise FileNotFoundError("目录不存在")
        if not root.is_dir():
            raise ValueError("路径不是目录")

        snapshot = _DirectorySnapshot()
        root_resolved = root.resolve()
        for current_dir, dir_names, file_names in os.walk(root_resolved, topdown=True):
            current_path = Path(current_dir)
            dir_names[:] = sorted(
                dir_name
                for dir_name in dir_names
                if dir_name not in DEFAULT_EXCLUDED_DIR_NAMES
                and not (current_path / dir_name).is_symlink()
            )
            for file_name in sorted(file_names):
                file_path = current_path / file_name
                if file_path.is_symlink() or not file_path.is_file():
                    continue
                relative_path = file_path.relative_to(root_resolved).as_posix()
                if len(snapshot.files) >= max_files:
                    raise DiffTooLargeError(f"目录文件数量超过限制: {max_files}")
                size = file_path.stat().st_size
                digest = self._sha256_file(file_path)
                snapshot.files[relative_path] = DirectoryDiffEntry(
                    path=relative_path,
                    status="unchanged",
                    left_size=size,
                    right_size=size,
                    left_sha256=digest,
                    right_sha256=digest,
                )
        return snapshot

    def _directory_entry_status(
        self,
        left: DirectoryDiffEntry | None,
        right: DirectoryDiffEntry | None,
    ) -> DiffStatus:
        if left is None and right is None:
            return "skipped"
        if left is None:
            return "added"
        if right is None:
            return "deleted"
        if left.left_sha256 == right.right_sha256 and left.left_size == right.right_size:
            return "unchanged"
        return "modified"

    def _status_from_probe(self, left: _FileProbe, right: _FileProbe) -> DiffStatus:
        if not left.exists and not right.exists:
            return "skipped"
        if not left.exists and right.exists:
            return "added"
        if left.exists and not right.exists:
            return "deleted"
        if left.sha256 == right.sha256 and left.size == right.size:
            return "unchanged"
        return "modified"

    def _skipped_file_result(
        self,
        left: _FileProbe,
        right: _FileProbe,
        *,
        status: DiffStatus,
        left_label: str,
        right_label: str,
        skip_reason: str | None = None,
    ) -> FileDiffResult:
        reason = skip_reason or left.skip_reason or right.skip_reason or "无法展示内容差异"
        return FileDiffResult(
            left_label=left_label,
            right_label=right_label,
            status=status,
            left_exists=left.exists,
            right_exists=right.exists,
            left_size=left.size,
            right_size=right.size,
            left_sha256=left.sha256,
            right_sha256=right.sha256,
            unified_diff="",
            stats=DiffStats(),
            can_show_content=False,
            skip_reason=reason,
            is_binary=left.is_binary or right.is_binary,
            is_too_large=left.is_too_large or right.is_too_large,
        )

    def _decode_content(self, content: bytes | None) -> tuple[str | None, str | None]:
        if content is None:
            return "", None
        if self._looks_binary(content[:4096]):
            return None, "二进制文件不展示内容差异"
        try:
            return content.decode("utf-8"), None
        except UnicodeDecodeError:
            return None, "文件不是有效的 UTF-8 文本"

    def _unified_diff(
        self,
        left_text: str,
        right_text: str,
        *,
        left_label: str,
        right_label: str,
    ) -> str:
        diff_lines = difflib.unified_diff(
            left_text.splitlines(keepends=True),
            right_text.splitlines(keepends=True),
            fromfile=left_label,
            tofile=right_label,
        )
        return "".join(diff_lines)

    def _stats_from_unified_diff(
        self,
        unified_diff: str,
        *,
        left_text: str,
        right_text: str,
    ) -> DiffStats:
        additions = 0
        deletions = 0
        for line in unified_diff.splitlines():
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                additions += 1
            elif line.startswith("-"):
                deletions += 1
        return DiffStats(
            additions=additions,
            deletions=deletions,
            left_lines=len(left_text.splitlines()),
            right_lines=len(right_text.splitlines()),
        )

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _looks_binary(self, content: bytes) -> bool:
        return b"\x00" in content


diff_service = DiffService()
