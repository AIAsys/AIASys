"""文件管理 API 工具函数和模型。

所有辅助函数和 Pydantic 模型集中在此模块，供 files 子模块和外部消费者使用。
"""

from __future__ import annotations

import csv
import json
import logging
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import quote

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.core.config import WORKSPACE_DIR
from app.models.user import UserInfo
from app.services.export import MARKDOWN_EXTENSIONS
from app.services.runtime.notebook_activity import is_notebook_session_busy
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)

MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100MB


def _copyfileobj_with_limit(source, dest, max_size: int = MAX_UPLOAD_SIZE) -> int:
    """流式复制文件并检查大小限制。"""
    total = 0
    while True:
        chunk = source.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large. Maximum size is {max_size // (1024 * 1024)}MB.",
            )
        dest.write(chunk)
    return total


INTERNAL_SESSION_DIRS = {
    ".aiasys",
    ".env",
    "env",
}
INTERNAL_SESSION_FILES = {
    ".cleanup_marker",
    "metadata.json",
    "history.json",
    "file_snapshots.json",
}
WORKSPACE_MEMORY_MIRROR_PATH = Path("记忆/工作区记忆.md")
EDITABLE_EXTENSIONS = {
    ".md",
    ".markdown",
    ".mdx",
    ".txt",
    ".json",
    ".jsonl",
    ".yaml",
    ".yml",
    ".csv",
    ".tsv",
    ".xml",
    ".ini",
    ".conf",
    ".cfg",
    ".toml",
    ".log",
    ".properties",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".scss",
    ".sql",
    ".sh",
    ".bash",
    ".zsh",
    ".ipynb",
    ".canvas",
}
RESOURCE_DB_EXTENSIONS = {".db", ".sqlite", ".sqlite3", ".duckdb"}
RESOURCE_METADATA_TABLE = "_aiasys_metadata"
RESOURCE_METADATA_TOP_LEVEL_KEYS = {
    "resource_type",
    "schema_kind",
    "preview_kind",
    "renderer_hint",
}


class FileInfo(BaseModel):
    """文件信息"""

    name: str
    size: int
    modified: float
    absolute_path: str | None = None
    resource_type: str | None = None
    schema_kind: str | None = None
    preview_kind: str | None = None
    renderer_hint: str | None = None
    meta: dict[str, object] = Field(default_factory=dict)


class FileListResponse(BaseModel):
    """文件列表响应"""

    files: list[FileInfo]
    user_id: str
    session_id: str
    directory: str = ""
    recursive: bool = False
    limit: int = 200
    offset: int = 0
    returned: int = 0
    has_more: bool = False
    next_offset: int | None = None
    total: int | None = None


class FileCreateRequest(BaseModel):
    """新建工作区文件请求"""

    path: str = Field(..., min_length=1, max_length=500)
    content: str = ""
    overwrite: bool = False


class FileCreateResponse(BaseModel):
    """新建工作区文件响应"""

    success: bool
    filename: str
    path: str
    size: int
    overwritten: bool = False
    created_by: str
    meta: dict[str, object] | None = None


class FileContentRequest(BaseModel):
    """文件内容请求"""

    content: str


class CreateGraphDbRequest(BaseModel):
    """创建知识图谱 .db 文件请求"""

    path: str = Field(..., min_length=1, max_length=500)
    graph_id: str | None = None
    name: str | None = None
    description: str | None = None
    overwrite: bool = False


class CreateKnowledgeDbRequest(BaseModel):
    """创建知识库 .kb.db 文件请求"""

    path: str = Field(..., min_length=1, max_length=500)
    name: str | None = None
    description: str | None = None
    overwrite: bool = False


class FileContentResponse(BaseModel):
    """文件内容响应"""

    filename: str
    content: str
    size: int
    editable: bool
    edit_lock_reason: str | None = None


class CsvPreviewResponse(BaseModel):
    """CSV 分页预览响应"""

    filename: str
    size: int
    headers: list[str]
    rows: list[list[str]]
    page: int
    page_size: int
    start_row: int
    returned_rows: int
    has_previous: bool
    has_next: bool
    total_columns: int
    column_offset: int
    column_limit: int
    returned_columns: int
    has_previous_columns: bool
    has_more_columns: bool
    editable: bool


class CsvPageUpdateRequest(BaseModel):
    """CSV 当前页单元格更新请求"""

    rows: list[list[str]]
    page: int = Field(1, ge=1)
    page_size: int = Field(100, ge=1, le=500)
    column_offset: int = Field(0, ge=0)
    column_limit: int = Field(50, ge=1, le=200)


class FileMoveRequest(BaseModel):
    """移动/重命名文件请求"""

    source: str = Field(..., min_length=1, max_length=500)
    target: str = Field(..., min_length=1, max_length=500)


class FileMoveResponse(BaseModel):
    """移动/重命名文件响应"""

    success: bool
    source: str
    target: str
    moved_by: str


class FileCopyRequest(BaseModel):
    """复制文件或文件夹请求"""

    source: str = Field(..., min_length=1, max_length=500)
    target: str = Field(..., min_length=1, max_length=500)


class FileCopyResponse(BaseModel):
    """复制文件或文件夹响应"""

    success: bool
    source: str
    target: str
    copied_by: str


def _get_user_workspace(user_id: str) -> Path:
    """获取用户工作区路径（纯 getter，带路径遍历防护）"""
    import re

    if not re.match(r"^[a-zA-Z0-9_\-]+$", user_id):
        raise ValueError("Invalid user_id format")

    # 使用 normpath/abspath 处理 .. 等相对路径，但不跟随符号链接，
    # 避免工作区目录内部合法符号链接（如桌面版外置运行时）被误判为越界。
    workspace = Path(os.path.normpath(os.path.abspath(WORKSPACE_DIR / user_id)))
    base = Path(os.path.normpath(os.path.abspath(WORKSPACE_DIR)))

    try:
        workspace.relative_to(base)
    except ValueError as exc:
        raise PermissionError("Path traversal detected") from exc

    return workspace


def _parse_metadata_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return ""
    if stripped[0] not in '[{"-' and not stripped.isdigit():
        return value
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return value


def _read_sqlite_resource_metadata(file_path: Path) -> dict[str, object]:
    """读取 AIASys 资源型 SQLite 文件的自描述 metadata。

    支持两种表结构：
    - key/value: `_aiasys_metadata(key text, value text)`
    - 单行列式: `_aiasys_metadata(resource_type text, schema_kind text, ...)`
    """

    if file_path.suffix.lower() not in RESOURCE_DB_EXTENSIONS:
        return {}
    if not file_path.is_file():
        return {}

    try:
        uri = f"file:{quote(str(file_path.resolve()), safe='/')}?mode=ro"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except (sqlite3.Error, OSError):
        return {}

    try:
        table = conn.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name=?",
            (RESOURCE_METADATA_TABLE,),
        ).fetchone()
        if not table:
            return {}

        column_rows = conn.execute(f"PRAGMA table_info({RESOURCE_METADATA_TABLE})").fetchall()
        columns = [str(row["name"]) for row in column_rows]
        normalized_columns = {column.lower(): column for column in columns}

        if "key" in normalized_columns and "value" in normalized_columns:
            key_column = normalized_columns["key"]
            value_column = normalized_columns["value"]
            rows = conn.execute(
                f"SELECT {key_column} AS key, {value_column} AS value "
                f"FROM {RESOURCE_METADATA_TABLE}"
            ).fetchall()
            metadata: dict[str, object] = {}
            for row in rows:
                key = str(row["key"]).strip()
                if key:
                    metadata[key] = _parse_metadata_value(row["value"])
            return metadata

        row = conn.execute(f"SELECT * FROM {RESOURCE_METADATA_TABLE} LIMIT 1").fetchone()
        if not row:
            return {}
        return {
            column: _parse_metadata_value(row[column])
            for column in columns
            if row[column] is not None
        }
    except sqlite3.Error as exc:
        logger.debug("读取 SQLite 资源 metadata 失败: %s", exc)
        return {}
    finally:
        conn.close()


def _build_visible_file_info(relative_path: str, file_path: Path) -> dict[str, object]:
    stat = file_path.stat()
    file_info: dict[str, object] = {
        "name": relative_path,
        "size": stat.st_size,
        "modified": stat.st_mtime,
        "absolute_path": str(file_path.absolute()),
    }

    metadata = _read_sqlite_resource_metadata(file_path)
    if not metadata:
        return file_info

    nested_meta = metadata.get("meta")
    resource_meta: dict[str, object] = dict(nested_meta) if isinstance(nested_meta, dict) else {}

    for key, value in metadata.items():
        if key in RESOURCE_METADATA_TOP_LEVEL_KEYS or key == "meta":
            continue
        resource_meta[key] = value

    if metadata.get("resource_type") and "db_path" not in resource_meta:
        resource_meta["db_path"] = f"/workspace/{relative_path}"
    if metadata.get("resource_type") and "source" not in resource_meta:
        resource_meta["source"] = "sqlite_metadata"

    for key in RESOURCE_METADATA_TOP_LEVEL_KEYS:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            file_info[key] = value.strip()

    if resource_meta:
        file_info["meta"] = resource_meta

    return file_info


def _get_work_dir(user_id: str, session_id: str) -> Path:
    """获取会话的工作区路径（纯 getter，不创建目录）

    路径: workspaces/{user_id}/{session_id}/
    目录创建交由 create_session 或写入操作自行处理。
    """
    return _get_user_workspace(user_id) / session_id


def _get_logical_workspace_root(user_id: str, session_id: str) -> Path:
    """解析当前对话实际所属的逻辑工作区根目录。

    - 若该 session 已绑定到任务工作区，则返回 `workspaces/{user_id}/{workspace_id}/`
    - 否则回退到旧的 `workspaces/{user_id}/{session_id}/`
    """
    return get_workspace_registry_service().get_logical_workspace_root(
        user_id,
        session_id,
    )


def _check_user_access(current_user: UserInfo, target_user_id: str):
    """检查用户是否有权访问目标用户的数据"""
    if not current_user.can_access_user_data(target_user_id):
        raise HTTPException(status_code=403, detail="You can only access your own files")


def _normalize_relative_path(relative_path: str) -> Path:
    """校验并规范化前端传入的逻辑工作区路径"""
    normalized_path = Path(relative_path.replace("\\", "/"))
    if (
        not relative_path
        or normalized_path.is_absolute()
        or any(part == ".." for part in normalized_path.parts)
    ):
        raise HTTPException(status_code=400, detail="Invalid filename")

    first_part = normalized_path.parts[0] if normalized_path.parts else ""
    if first_part in {".aiasys"} and len(normalized_path.parts) >= 2:
        second_part = normalized_path.parts[1]
        if second_part in {"session", ".memory"}:
            raise HTTPException(status_code=403, detail="Access denied")
    if len(normalized_path.parts) == 1 and normalized_path.name in INTERNAL_SESSION_FILES:
        raise HTTPException(status_code=403, detail="Access denied")

    return normalized_path


def _is_notebook_relative_path(relative_path: str | Path) -> bool:
    path = relative_path if isinstance(relative_path, Path) else Path(relative_path)
    return path.suffix.lower() == ".ipynb"


def _is_notebook_file_name(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".ipynb"


def _is_workspace_memory_mirror_path(relative_path: str | Path) -> bool:
    path = relative_path if isinstance(relative_path, Path) else Path(relative_path)
    return path == WORKSPACE_MEMORY_MIRROR_PATH


def _is_session_private_workspace_path(relative_path: str | Path) -> bool:
    return _is_notebook_relative_path(relative_path)


def _ensure_path_within_root(root: Path, relative_path: Path) -> Path:
    """将相对路径解析到指定根目录并进行越界校验"""
    root.mkdir(parents=True, exist_ok=True)
    file_path = (root / relative_path).resolve()
    root_resolved = root.resolve()
    if not str(file_path).startswith(str(root_resolved)):
        raise HTTPException(status_code=403, detail="Access denied")
    return file_path


def _build_scoped_candidate_paths(
    user_id: str,
    session_id: str,
    relative_path: Path,
    *,
    write_target: Literal["session", "workspace"],
) -> tuple[Path, list[Path]]:
    session_dir = _get_work_dir(user_id, session_id)
    workspace_root = _get_logical_workspace_root(user_id, session_id)

    session_candidate = _ensure_path_within_root(session_dir, relative_path)
    workspace_candidate = _ensure_path_within_root(workspace_root, relative_path)

    ordered_candidates = (
        (session_candidate, workspace_candidate)
        if write_target == "session"
        else (workspace_candidate, session_candidate)
    )

    read_candidates: list[Path] = []
    for candidate in ordered_candidates:
        if candidate not in read_candidates:
            read_candidates.append(candidate)

    write_candidate = session_candidate if write_target == "session" else workspace_candidate
    return write_candidate, read_candidates


def _build_notebook_candidate_paths(
    user_id: str,
    session_id: str,
    relative_path: Path,
) -> tuple[Path, list[Path]]:
    return _build_scoped_candidate_paths(
        user_id,
        session_id,
        relative_path,
        write_target="session",
    )


def _resolve_notebook_path(
    user_id: str,
    session_id: str,
    relative_path: Path,
    *,
    for_write: bool = False,
) -> Path:
    write_candidate, read_candidates = _build_notebook_candidate_paths(
        user_id,
        session_id,
        relative_path,
    )
    if for_write:
        return write_candidate

    for candidate in read_candidates:
        if candidate.exists():
            return candidate
    return write_candidate


def _build_memory_mirror_candidate_paths(
    user_id: str,
    session_id: str,
    relative_path: Path,
) -> tuple[Path, list[Path]] | None:
    if _is_workspace_memory_mirror_path(relative_path):
        return _build_scoped_candidate_paths(
            user_id,
            session_id,
            relative_path,
            write_target="workspace",
        )
    return None


def _resolve_memory_mirror_path(
    user_id: str,
    session_id: str,
    relative_path: Path,
    *,
    for_write: bool = False,
) -> Path | None:
    candidates = _build_memory_mirror_candidate_paths(
        user_id,
        session_id,
        relative_path,
    )
    if candidates is None:
        return None

    write_candidate, read_candidates = candidates
    if for_write:
        return write_candidate

    for candidate in read_candidates:
        if candidate.exists():
            return candidate
    return write_candidate


def _is_runtime_busy_for_session(user_id: str, session_id: str) -> bool:
    from app.services.agent import agent_service

    session_key = f"{user_id}/{session_id}"
    session_lock = getattr(agent_service, "_session_locks", {}).get(session_key)
    if session_lock and session_lock.locked():
        return True
    return is_notebook_session_busy(user_id, session_id)


def _get_notebook_edit_lock_reason(user_id: str, session_id: str) -> str | None:
    if not _is_runtime_busy_for_session(user_id, session_id):
        return None
    return "当前会话正在运行 Agent / notebook，暂时禁止人工编辑该 notebook。"


def _resolve_workspace_path(user_id: str, session_id: str, relative_path: str) -> Path:
    """将逻辑工作区路径解析为真实文件路径

    当前逻辑工作区优先对齐任务工作区根目录；若 session 尚未绑定工作区，
    则使用会话目录 `workspaces/{user_id}/{session_id}/`。
    """
    normalized_path = _normalize_relative_path(relative_path)
    if _is_notebook_relative_path(normalized_path):
        return _resolve_notebook_path(user_id, session_id, normalized_path)

    memory_mirror_path = _resolve_memory_mirror_path(
        user_id,
        session_id,
        normalized_path,
    )
    if memory_mirror_path is not None:
        return memory_mirror_path

    workspace_root = _get_logical_workspace_root(user_id, session_id)
    root_candidate = _ensure_path_within_root(workspace_root, normalized_path)
    return root_candidate


def _resolve_workspace_path_for_write(
    user_id: str,
    session_id: str,
    relative_path: Path,
) -> Path:
    if _is_notebook_relative_path(relative_path):
        return _resolve_notebook_path(
            user_id,
            session_id,
            relative_path,
            for_write=True,
        )

    memory_mirror_path = _resolve_memory_mirror_path(
        user_id,
        session_id,
        relative_path,
        for_write=True,
    )
    if memory_mirror_path is not None:
        return memory_mirror_path

    return _resolve_workspace_path(user_id, session_id, relative_path.as_posix())


def _sync_workspace_memory_from_mirror(
    *,
    user_id: str,
    session_id: str,
    relative_path: Path,
    content: str,
) -> None:
    from app.services.memory.resolver import (
        get_workspace_memory_file_path,
    )
    from app.services.memory.store import MemoryStore

    normalized_content = content.strip()
    registry = get_workspace_registry_service()

    if not _is_workspace_memory_mirror_path(relative_path):
        return

    workspace_id = registry.find_workspace_id_by_session_id(user_id, session_id)
    if workspace_id is None:
        raise HTTPException(status_code=400, detail="当前会话未绑定工作区，无法保存工作区记忆")
    workspace_root = registry.get_workspace_root(user_id, workspace_id)
    memory_path = get_workspace_memory_file_path(workspace_root)
    store = MemoryStore(memory_path)

    if not normalized_content:
        store.write_text("")
        return

    store.write_text(normalized_content)


def _clear_workspace_memory_from_mirror(
    *,
    user_id: str,
    session_id: str,
    relative_path: Path,
) -> None:
    _sync_workspace_memory_from_mirror(
        user_id=user_id,
        session_id=session_id,
        relative_path=relative_path,
        content="",
    )


def _should_skip_session_file(relative_path: str) -> bool:
    """判断文件是否属于内部文件，不应暴露给工作区面板"""
    path = Path(relative_path)
    parts = path.parts
    if not parts:
        return True
    file_name = path.name

    if parts[0] in INTERNAL_SESSION_DIRS:
        return True
    if len(parts) == 1 and file_name in INTERNAL_SESSION_FILES:
        return True
    if any(part in {".aiasys"} for part in parts[:-1]):
        return True
    # 跳过 SQLite WAL 临时文件
    if file_name.endswith("-shm") or file_name.endswith("-wal") or file_name.endswith("-journal"):
        return True
    return False


def _iter_directory_files(base_dir: Path):
    """递归遍历目录文件，返回相对路径和文件路径"""
    if not base_dir.exists() or not base_dir.is_dir():
        return

    for file_path in base_dir.rglob("*"):
        if not file_path.is_file():
            continue

        relative_path = file_path.relative_to(base_dir).as_posix()
        if _should_skip_session_file(relative_path):
            continue

        yield relative_path, file_path


def _is_pruned_session_dir(relative_path: str) -> bool:
    path = Path(relative_path)
    parts = path.parts
    if not parts:
        return False
    if parts[0] in INTERNAL_SESSION_DIRS:
        return True
    if any(part in {".aiasys"} for part in parts):
        return True
    return False


def _iter_session_files(
    session_dir: Path,
    *,
    directory: str = "",
    recursive: bool = True,
    max_depth: int | None = None,
):
    """遍历逻辑工作区文件，支持目录、递归和深度控制。"""
    if not session_dir.exists() or not session_dir.is_dir():
        return

    emitted_paths: set[str] = set()
    normalized_directory = directory.strip("/")
    if normalized_directory and _is_pruned_session_dir(normalized_directory):
        return

    root_dir = (session_dir / normalized_directory).resolve()
    session_root = session_dir.resolve()
    try:
        root_dir.relative_to(session_root)
    except ValueError:
        return
    if not root_dir.exists() or not root_dir.is_dir():
        return

    for current_dir, dir_names, file_names in os.walk(root_dir, topdown=True):
        current_path = Path(current_dir)
        relative_dir = current_path.relative_to(session_root).as_posix()
        if relative_dir == ".":
            relative_dir = ""

        visible_dir_names: list[str] = []
        for dir_name in sorted(dir_names):
            dir_path = current_path / dir_name
            if dir_path.is_symlink():
                continue
            candidate_relative = f"{relative_dir}/{dir_name}" if relative_dir else dir_name
            if _is_pruned_session_dir(candidate_relative):
                continue
            visible_dir_names.append(dir_name)

        if not recursive:
            visible_dir_names = []
        elif max_depth is not None:
            relative_to_listing_root = current_path.relative_to(root_dir)
            listing_depth = (
                0
                if relative_to_listing_root.as_posix() == "."
                else len(relative_to_listing_root.parts)
            )
            if listing_depth >= max_depth:
                visible_dir_names = []

        dir_names[:] = visible_dir_names

        for file_name in sorted(file_names):
            file_path = current_path / file_name
            if not file_path.is_file() or file_path.is_symlink():
                continue

            relative_path = file_path.relative_to(session_root).as_posix()
            if _should_skip_session_file(relative_path):
                continue
            if relative_path in emitted_paths:
                continue

            emitted_paths.add(relative_path)
            yield relative_path, file_path


def _iter_visible_workspace_files(
    user_id: str,
    session_id: str,
    *,
    directory: str = "",
    recursive: bool = True,
    max_depth: int | None = None,
):
    """枚举当前会话可见文件。

    规则：
    - 普通文件仍以逻辑工作区根为主
    - notebook 默认按会话私有，优先暴露 session 根里的 `.ipynb`
    - 若当前会话没有私有 notebook，则兼容暴露逻辑工作区根里的旧 notebook
    """
    logical_root = _get_logical_workspace_root(user_id, session_id)
    session_dir = _get_work_dir(user_id, session_id)
    emitted_paths: set[str] = set()

    if session_dir != logical_root:
        for relative_path, file_path in _iter_session_files(
            session_dir,
            directory=directory,
            recursive=recursive,
            max_depth=max_depth,
        ):
            if not _is_session_private_workspace_path(relative_path):
                continue
            if relative_path in emitted_paths:
                continue
            emitted_paths.add(relative_path)
            yield relative_path, file_path

    for relative_path, file_path in _iter_session_files(
        logical_root,
        directory=directory,
        recursive=recursive,
        max_depth=max_depth,
    ):
        if relative_path in emitted_paths:
            continue
        emitted_paths.add(relative_path)
        yield relative_path, file_path


def _get_session_owner_user_id(user_id: str, session_id: str) -> Optional[str]:
    """从 session metadata 中获取真实的 owner user_id"""
    try:
        session_dir = _get_work_dir(user_id, session_id)
        meta_path = session_dir / "metadata.json"
        if meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return data.get("user_id")
    except Exception:
        pass
    return None


def _is_editable_file(filename: str) -> bool:
    """检查文件是否可编辑（文本文件）"""
    ext = Path(filename).suffix.lower()
    return ext in EDITABLE_EXTENSIONS


def _is_markdown_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in MARKDOWN_EXTENSIONS


def _is_csv_file(filename: str) -> bool:
    return Path(filename).suffix.lower() == ".csv"


def _read_csv_preview_page(
    file_path: Path,
    *,
    filename: str,
    page: int,
    page_size: int,
    column_offset: int,
    column_limit: int,
    editable: bool,
) -> CsvPreviewResponse:
    if not _is_csv_file(file_path.name):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_size = file_path.stat().st_size
    safe_page = max(1, page)
    safe_page_size = min(max(1, page_size), 500)
    safe_column_offset = max(0, column_offset)
    safe_column_limit = min(max(1, column_limit), 200)
    data_start_index = (safe_page - 1) * safe_page_size
    data_stop_index = data_start_index + safe_page_size

    try:
        with file_path.open("r", encoding="utf-8", newline="") as csv_file:
            reader = csv.reader(csv_file)
            headers = next(reader, [])
            total_columns = len(headers)
            visible_column_stop = safe_column_offset + safe_column_limit
            visible_headers = headers[safe_column_offset:visible_column_stop]
            rows: list[list[str]] = []
            has_next = False

            for row_index, row in enumerate(reader):
                if row_index < data_start_index:
                    continue
                if row_index >= data_stop_index:
                    has_next = True
                    break
                normalized_row = [str(cell) for cell in row]
                rows.append(normalized_row[safe_column_offset:visible_column_stop])
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件不是有效的 UTF-8 CSV")
    except csv.Error as exc:
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {exc}") from exc

    return CsvPreviewResponse(
        filename=filename,
        size=file_size,
        headers=visible_headers,
        rows=rows,
        page=safe_page,
        page_size=safe_page_size,
        start_row=data_start_index + 1 if rows else data_start_index,
        returned_rows=len(rows),
        has_previous=safe_page > 1,
        has_next=has_next,
        total_columns=total_columns,
        column_offset=safe_column_offset,
        column_limit=safe_column_limit,
        returned_columns=len(visible_headers),
        has_previous_columns=safe_column_offset > 0,
        has_more_columns=visible_column_stop < total_columns,
        editable=editable,
    )


def _update_csv_preview_page(
    file_path: Path,
    *,
    rows: list[list[str]],
    page: int,
    page_size: int,
    column_offset: int,
    column_limit: int,
) -> int:
    if not _is_csv_file(file_path.name):
        raise HTTPException(status_code=400, detail="仅支持 CSV 文件")
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    safe_page = max(1, page)
    safe_page_size = min(max(1, page_size), 500)
    safe_column_offset = max(0, column_offset)
    safe_column_limit = min(max(1, column_limit), 200)
    data_start_index = (safe_page - 1) * safe_page_size
    data_stop_index = data_start_index + safe_page_size
    expected_row_count = data_stop_index - data_start_index
    if len(rows) > expected_row_count:
        raise HTTPException(status_code=400, detail="提交行数超过当前分页范围")
    if any(len(row) > safe_column_limit for row in rows):
        raise HTTPException(status_code=400, detail="提交列数超过当前列窗口")

    updated_rows = 0
    temp_path: Path | None = None
    try:
        with file_path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.reader(source)
            fd, temp_name = tempfile.mkstemp(
                prefix=f".{file_path.name}.",
                suffix=".tmp",
                dir=str(file_path.parent),
                text=True,
            )
            os.close(fd)
            temp_path = Path(temp_name)
            with temp_path.open("w", encoding="utf-8", newline="") as target:
                writer = csv.writer(target)
                for physical_index, source_row in enumerate(reader):
                    if physical_index == 0:
                        writer.writerow(source_row)
                        continue

                    data_index = physical_index - 1
                    if data_start_index <= data_index < data_stop_index:
                        update_index = data_index - data_start_index
                        if update_index < len(rows):
                            next_row = list(source_row)
                            visible_updates = [str(cell) for cell in rows[update_index]]
                            required_length = safe_column_offset + len(visible_updates)
                            if len(next_row) < required_length:
                                next_row.extend([""] * (required_length - len(next_row)))
                            for offset, value in enumerate(visible_updates):
                                next_row[safe_column_offset + offset] = value
                            writer.writerow(next_row)
                            updated_rows += 1
                            continue
                    writer.writerow(source_row)
    except UnicodeDecodeError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="文件不是有效的 UTF-8 CSV")
    except csv.Error as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"CSV 解析失败: {exc}") from exc
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="CSV 保存失败") from exc

    if temp_path is None:
        raise HTTPException(status_code=500, detail="CSV 保存失败")
    temp_path.replace(file_path)
    return updated_rows
