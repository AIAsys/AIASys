"""
本地文件夹导入服务：扫描、过滤、复制用户选择的文件夹内容到工作区。
"""

from __future__ import annotations

import fnmatch
import logging
import os
import secrets
import shutil
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

MAX_SCAN_DEPTH = 8
MAX_SCAN_FILES = 10000
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
LARGE_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
MAX_UPLOAD_FILE_SIZE_BYTES = 100 * 1024 * 1024  # 100MB
MAX_UPLOAD_TOTAL_SIZE_BYTES = 1024 * 1024 * 1024  # 1GB

DEFAULT_EXCLUDE_PATTERNS: list[str] = [
    ".git/",
    ".svn/",
    ".hg/",
    ".aiasys/",
    "node_modules/",
    "__pycache__/",
    ".venv/",
    "venv/",
    ".tox/",
    ".pytest_cache/",
    ".mypy_cache/",
    "target/",
    "dist/",
    "build/",
    ".next/",
    ".nuxt/",
    ".svelte-kit/",
    ".env",
    ".env.*",
    "*.pyc",
    "*.pyo",
    "*.log",
    "*.tmp",
    "*.cache",
    ".DS_Store",
    "Thumbs.db",
]


@dataclass
class FolderImportTreeItem:
    relative_path: str
    is_directory: bool = False
    size: Optional[int] = None


@dataclass
class FolderImportPreviewResult:
    source_path: Path
    files: list[FolderImportTreeItem] = field(default_factory=list)
    excluded_files: list[str] = field(default_factory=list)
    default_selected_files: list[str] = field(default_factory=list)
    total_file_count: int = 0
    total_size_bytes: int = 0


ProgressCallback = Callable[[int, str], None]


def _normalize_relative_path(path: Path, root: Path) -> str:
    """返回相对于 root 的 POSIX 风格相对路径。"""
    try:
        rel = path.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"路径 {path} 不在根目录 {root} 下") from exc
    return rel.as_posix()


def _is_excluded(relative_path: str, exclude_patterns: list[str]) -> bool:
    """根据 gitignore 风格的模式判断是否排除。"""
    parts = relative_path.split("/")

    for pattern in exclude_patterns:
        pattern = pattern.strip()
        if not pattern:
            continue

        # 目录模式：以 / 结尾，匹配目录本身及其所有子内容
        if pattern.endswith("/"):
            dir_pattern = pattern.rstrip("/")
            if dir_pattern == "":
                continue
            # 匹配路径中任意一段目录名
            for i, part in enumerate(parts):
                if part == dir_pattern:
                    return True
                # 通配符匹配目录段
                if fnmatch.fnmatch(part, dir_pattern):
                    return True
                # 完整路径匹配
                prefix = "/".join(parts[: i + 1])
                if fnmatch.fnmatch(prefix, dir_pattern):
                    return True
            continue

        # 不含 / 的模式：匹配任何层级的文件或目录名
        if "/" not in pattern:
            for part in parts:
                if fnmatch.fnmatch(part, pattern):
                    return True
            # 也尝试匹配完整路径（用于 *.ext 匹配深层文件）
            if fnmatch.fnmatch(relative_path, f"*/{pattern}"):
                return True
            continue

        # 含 / 的模式：匹配完整路径
        if fnmatch.fnmatch(relative_path, pattern):
            return True
        if fnmatch.fnmatch(relative_path, pattern.lstrip("/")):
            return True

    return False


def _is_system_or_hidden(name: str) -> bool:
    """判断是否为隐藏文件或常见系统文件。"""
    return name.startswith(".") or name in {"Thumbs.db", "desktop.ini", ".DS_Store"}


def _validate_source_path(source_path: Path) -> None:
    """校验源路径是否合法。"""
    if not source_path.exists():
        raise ValueError(f"源文件夹不存在: {source_path}")
    if not source_path.is_dir():
        raise ValueError(f"源路径不是文件夹: {source_path}")
    if not os.access(source_path, os.R_OK):
        raise ValueError(f"源文件夹不可读: {source_path}")


def scan_folder(
    source_path: Path,
    *,
    exclude_patterns: Optional[list[str]] = None,
    max_depth: int = MAX_SCAN_DEPTH,
    max_files: int = MAX_SCAN_FILES,
) -> FolderImportPreviewResult:
    """扫描源文件夹，返回文件树和默认预选文件列表。"""
    _validate_source_path(source_path)
    source_path = source_path.resolve()

    patterns = list(exclude_patterns) if exclude_patterns else list(DEFAULT_EXCLUDE_PATTERNS)

    result = FolderImportPreviewResult(source_path=source_path)
    scanned_count = 0
    default_selected_size = 0

    for root, dirs, files in os.walk(source_path):
        current_depth = root[len(str(source_path)) :].count(os.sep)
        if current_depth >= max_depth:
            dirs[:] = []
            continue

        root_path = Path(root)
        rel_root = _normalize_relative_path(root_path, source_path)

        if rel_root and rel_root != ".":
            if scanned_count >= max_files:
                break
            scanned_count += 1
            result.files.append(FolderImportTreeItem(relative_path=rel_root, is_directory=True))

        # 过滤目录：排除的目录不再深入
        filtered_dirs: list[str] = []
        for dirname in dirs:
            rel_dir = (rel_root + "/" + dirname) if rel_root and rel_root != "." else dirname
            if _is_excluded(rel_dir, patterns):
                result.excluded_files.append(rel_dir)
                continue
            filtered_dirs.append(dirname)
        dirs[:] = filtered_dirs

        for filename in files:
            if scanned_count >= max_files:
                break
            scanned_count += 1

            rel_file = (rel_root + "/" + filename) if rel_root and rel_root != "." else filename

            file_path = root_path / filename
            if file_path.is_symlink():
                result.excluded_files.append(rel_file)
                continue

            size: Optional[int] = None
            try:
                size = file_path.stat().st_size
            except OSError:
                pass

            result.files.append(
                FolderImportTreeItem(
                    relative_path=rel_file,
                    is_directory=False,
                    size=size,
                )
            )

            if _is_excluded(rel_file, patterns):
                result.excluded_files.append(rel_file)
                continue

            # 超大文件默认不选，但允许用户手动勾选
            if size is not None and size > MAX_FILE_SIZE_BYTES:
                continue

            result.default_selected_files.append(rel_file)
            if size is not None:
                default_selected_size += size

    if scanned_count >= max_files:
        logger.warning("扫描文件数达到上限 %d，已停止扫描", max_files)

    result.total_file_count = scanned_count
    result.total_size_bytes = default_selected_size
    return result


def _report_progress(
    callback: Optional[ProgressCallback],
    progress: int,
    message: str,
    last_reported: list[float],
) -> None:
    """限制进度回调频率，避免 SSE 过于频繁；但关键节点强制上报。"""
    if callback is None:
        return
    now = time.monotonic()
    is_milestone = progress in (0, 90, 100)
    if not is_milestone and now - last_reported[0] < 0.05:
        return
    last_reported[0] = now
    try:
        callback(progress, message)
    except Exception:
        logger.warning("进度回调异常", exc_info=True)


def copy_selected_files(
    source_path: Path,
    target_path: Path,
    selected_files: list[str],
    *,
    progress_callback: Optional[ProgressCallback] = None,
) -> tuple[int, int]:
    """复制用户选中的文件到目标目录。

    返回 (复制的文件数, 复制的字节数)。
    """
    _validate_source_path(source_path)
    source_path = source_path.resolve()
    target_path = target_path.resolve()

    if not selected_files:
        return 0, 0

    # 按相对路径排序并去重
    sorted_files = sorted(set(selected_files))

    # 预处理：验证所有路径合法，收集实际要复制的文件列表
    copy_tasks: list[tuple[Path, Path, int]] = []
    for rel_path in sorted_files:
        if not rel_path or rel_path.startswith("/") or ".." in rel_path.split("/"):
            raise ValueError(f"非法的相对路径: {rel_path}")

        src_file = source_path / rel_path
        src_file = src_file.resolve()

        # 确保解析后的路径仍在 source_path 内
        try:
            src_file.relative_to(source_path)
        except ValueError as exc:
            raise ValueError(f"路径越界: {rel_path}") from exc

        if not src_file.exists() or src_file.is_dir():
            continue
        if src_file.is_symlink():
            continue

        dst_file = target_path / rel_path
        copy_tasks.append((src_file, dst_file, rel_path))

    total_files = len(copy_tasks)
    copied_files = 0
    copied_bytes = 0
    last_reported = [0.0]

    _report_progress(progress_callback, 0, "正在准备复制...", last_reported)

    for index, (src_file, dst_file, rel_path) in enumerate(copy_tasks, start=1):
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        try:
            size = src_file.stat().st_size
            shutil.copy2(as_system_path(str(src_file)), as_system_path(str(dst_file)))
            copied_files += 1
            copied_bytes += size
        except OSError as exc:
            logger.warning("复制文件失败: %s -> %s — %s", src_file, dst_file, exc)
            continue

        progress = int(index / total_files * 90) if total_files > 0 else 90
        _report_progress(
            progress_callback,
            progress,
            f"正在复制文件 ({index}/{total_files})",
            last_reported,
        )

    _report_progress(progress_callback, 90, "文件复制完成", last_reported)
    return copied_files, copied_bytes


# ── Web 版临时上传目录管理 ──

_import_upload_dirs: dict[str, Path] = {}


def create_import_upload_dir() -> tuple[str, Path]:
    """创建一个新的临时上传目录，返回 upload_id 和目录路径。"""
    upload_id = secrets.token_hex(8)
    upload_dir = Path(tempfile.gettempdir()) / f"aiasys-upload-{upload_id}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    _import_upload_dirs[upload_id] = upload_dir
    return upload_id, upload_dir


def get_import_upload_dir(upload_id: str) -> Path | None:
    """获取临时上传目录。"""
    return _import_upload_dirs.get(upload_id)


def remove_import_upload_dir(upload_id: str) -> bool:
    """删除临时上传目录，返回是否成功。"""
    path = _import_upload_dirs.pop(upload_id, None)
    if path and path.exists():
        try:
            shutil.rmtree(as_system_path(str(path)), ignore_errors=True)
            return True
        except OSError:
            logger.warning("清理临时上传目录失败: %s", path, exc_info=True)
    return False
