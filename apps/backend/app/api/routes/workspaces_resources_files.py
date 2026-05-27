"""
工作区级文件读取接口

支持按 workspace_id 直接读取和下载工作区文件，不依赖 session_id。
用于跨会话/跨工作区引用文件的场景。
"""

from __future__ import annotations

import logging
import mimetypes
import os
import shutil
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.api.routes.files_utils import (
    EDITABLE_EXTENSIONS,
    INTERNAL_SESSION_FILES,
    CreateGraphDbRequest,
    CreateKnowledgeDbRequest,
    CsvPageUpdateRequest,
    CsvPreviewResponse,
    FileContentRequest,
    FileContentResponse,
    FileCopyRequest,
    FileCopyResponse,
    FileCreateRequest,
    FileCreateResponse,
    FileInfo,
    FileMoveRequest,
    FileMoveResponse,
    _build_visible_file_info,
    _read_csv_preview_page,
    _update_csv_preview_page,
)
from app.api.routes.workspaces_resources_tree import (
    WorkspaceResourcesTreeResponse,
    _is_hidden_by_config,
    _load_file_visibility_rules,
    _scan_workspace_file_assets,
)
from app.core.auth import require_auth
from app.knowledge import SQLiteKBService
from app.knowledge.models import KnowledgeBaseCreate
from app.models.user import UserInfo
from app.services.diff_service import FileDiffResult
from app.services.file_history import (
    FileHistoryEntry,
    FileHistoryOperation,
    file_history_service,
)
from app.services.workspace_registry import get_workspace_registry_service

logger = logging.getLogger(__name__)

router = APIRouter()


class WorkspaceFileListResponse(BaseModel):
    """工作区文件列表响应。"""

    files: list[FileInfo]
    workspace_id: str
    directory: str = ""
    recursive: bool = False
    limit: int = 200
    offset: int = 0
    returned: int = 0
    has_more: bool = False
    next_offset: int | None = None
    total: int | None = None


class FileHistoryEntryResponse(BaseModel):
    id: str
    file_path: str
    timestamp: str
    operation: str
    source: str
    source_detail: str | None = None
    size: int
    sha256: str
    target_path: str | None = None


class FileHistoryListResponse(BaseModel):
    scope: Literal["workspace", "global"]
    workspace_id: str
    filename: str
    entries: list[FileHistoryEntryResponse]


class FileHistoryContentResponse(BaseModel):
    entry: FileHistoryEntryResponse
    content: str
    size: int


class FileHistoryDiffResponse(BaseModel):
    entry: FileHistoryEntryResponse
    current_exists: bool
    diff: str
    status: Literal["added", "deleted", "modified", "unchanged", "skipped"] = "modified"
    left_label: str | None = None
    right_label: str | None = None
    left_text: str | None = None
    right_text: str | None = None
    can_show_content: bool = True
    skip_reason: str | None = None
    additions: int = 0
    deletions: int = 0


class FileHistoryRestoreResponse(BaseModel):
    success: bool
    filename: str
    restored_entry_id: str
    size: int


def _normalize_relative_path(relative_path: str) -> Path:
    """校验并规范化前端传入的逻辑工作区路径"""
    normalized_path = Path(relative_path.replace("\\", "/"))
    if (
        not relative_path
        or normalized_path.is_absolute()
        or any(part == ".." for part in normalized_path.parts)
    ):
        raise HTTPException(status_code=400, detail="无效的文件路径")

    first_part = normalized_path.parts[0] if normalized_path.parts else ""
    if first_part in {".aiasys"}:
        raise HTTPException(status_code=403, detail="Access denied")
    if len(normalized_path.parts) == 1 and normalized_path.name in INTERNAL_SESSION_FILES:
        raise HTTPException(status_code=403, detail="Access denied")

    return normalized_path


def _is_pruned_workspace_path(relative_path: str) -> bool:
    parts = Path(relative_path).parts
    if not parts:
        return False
    if parts[0] in {".env", ".aiasys"}:
        return True
    return False


def _should_skip_workspace_file(
    relative_path: str, file_path: Path, patterns: list[str]
) -> bool:
    parts = Path(relative_path).parts
    if not parts:
        return True
    if _is_hidden_by_config(relative_path, patterns):
        return True
    return False


def _iter_workspace_files(
    workspace_root: Path,
    *,
    directory: str = "",
    recursive: bool = True,
    max_depth: int | None = None,
):
    """遍历工作区文件，屏蔽内部目录和资源树文件夹标记。"""
    if not workspace_root.exists() or not workspace_root.is_dir():
        return

    patterns = _load_file_visibility_rules(workspace_root)

    normalized_directory = directory.strip().replace("\\", "/").strip("/")
    if normalized_directory and _is_pruned_workspace_path(normalized_directory):
        return

    root_dir = (workspace_root / normalized_directory).resolve()
    workspace_root_resolved = workspace_root.resolve()
    try:
        root_dir.relative_to(workspace_root_resolved)
    except ValueError:
        return
    if not root_dir.exists() or not root_dir.is_dir():
        return

    for current_dir, dir_names, file_names in os.walk(root_dir, topdown=True):
        current_path = Path(current_dir)
        relative_dir = current_path.relative_to(workspace_root_resolved).as_posix()
        if relative_dir == ".":
            relative_dir = ""

        visible_dir_names: list[str] = []
        for dir_name in sorted(dir_names):
            dir_path = current_path / dir_name
            if dir_path.is_symlink():
                continue
            candidate_relative = f"{relative_dir}/{dir_name}" if relative_dir else dir_name
            if _is_pruned_workspace_path(candidate_relative):
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

            relative_path = file_path.relative_to(workspace_root_resolved).as_posix()
            if _should_skip_workspace_file(relative_path, file_path, patterns):
                continue

            yield relative_path, file_path


def _ensure_path_within_root(root: Path, relative_path: Path) -> Path:
    """将相对路径解析到指定根目录并进行越界校验"""
    root.mkdir(parents=True, exist_ok=True)
    file_path = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        file_path.relative_to(root_resolved)
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    return file_path


def _resolve_workspace_file_path(workspace_root: Path, filename: str) -> Path:
    """在工作区根目录下解析文件路径。"""
    normalized_path = _normalize_relative_path(filename)
    return _ensure_path_within_root(workspace_root, normalized_path)


def _resolve_user_global_workspace_file_path(user_id: str, filename: str) -> Path:
    """解析用户默认层全局工作区内的文件路径。"""
    from app.core.config import get_user_global_workspace_dir

    normalized_path = _normalize_relative_path(filename)
    global_workspace_dir = get_user_global_workspace_dir(user_id)
    return _ensure_path_within_root(global_workspace_dir, normalized_path)


def _resolve_user_global_workspace_root(user_id: str) -> Path:
    """解析用户默认层全局工作区根目录。"""
    from app.core.config import get_user_global_workspace_dir

    return get_user_global_workspace_dir(user_id)


def _file_history_entry_response(entry: FileHistoryEntry) -> FileHistoryEntryResponse:
    return FileHistoryEntryResponse(
        id=entry.id,
        file_path=entry.file_path,
        timestamp=entry.timestamp,
        operation=entry.operation,
        source=entry.source,
        source_detail=entry.source_detail,
        size=entry.size,
        sha256=entry.sha256,
        target_path=entry.target_path,
    )


def _file_history_diff_response(
    entry: FileHistoryEntry,
    result: FileDiffResult,
) -> FileHistoryDiffResponse:
    return FileHistoryDiffResponse(
        entry=_file_history_entry_response(entry),
        current_exists=result.right_exists,
        diff=result.unified_diff,
        status=result.status,
        left_label=result.left_label,
        right_label=result.right_label,
        left_text=result.left_text,
        right_text=result.right_text,
        can_show_content=result.can_show_content,
        skip_reason=result.skip_reason,
        additions=result.stats.additions,
        deletions=result.stats.deletions,
    )


def _record_file_history(
    workspace_root: Path,
    relative_path: str | Path,
    *,
    operation: FileHistoryOperation,
    current_user: UserInfo,
    target_path: str | Path | None = None,
) -> None:
    file_history_service.record_file_before_change(
        workspace_root,
        Path(relative_path).as_posix(),
        operation=operation,
        source="api",
        source_detail=current_user.user_id,
        target_path=Path(target_path).as_posix() if target_path is not None else None,
    )


def _record_tree_history(
    workspace_root: Path,
    relative_path: str | Path,
    *,
    operation: FileHistoryOperation,
    current_user: UserInfo,
    target_path: str | Path | None = None,
) -> None:
    file_history_service.record_tree_before_change(
        workspace_root,
        Path(relative_path).as_posix(),
        operation=operation,
        source="api",
        source_detail=current_user.user_id,
        target_path=Path(target_path).as_posix() if target_path is not None else None,
    )


def _is_editable_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in EDITABLE_EXTENSIONS


def _normalize_resource_db_path(
    raw_path: str,
    *,
    required_suffix: str,
    resource_label: str,
) -> Path:
    normalized_path = _normalize_relative_path(raw_path.strip())
    if not normalized_path.as_posix().lower().endswith(required_suffix):
        raise HTTPException(
            status_code=400, detail=f"{resource_label}文件必须以 {required_suffix} 结尾"
        )
    return normalized_path


def _resource_id_from_db_path(path: Path, suffix: str) -> str:
    name = path.name
    if name.lower().endswith(suffix):
        return name[: -len(suffix)]
    return path.stem


def _copy_file_or_directory(source_path: Path, target_path: Path) -> None:
    if target_path.exists():
        raise HTTPException(status_code=409, detail="目标已存在")

    if source_path.is_dir():
        try:
            target_path.resolve().relative_to(source_path.resolve())
            raise HTTPException(status_code=400, detail="不能将文件夹复制到自身内部")
        except ValueError:
            pass

    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.is_dir():
        shutil.copytree(source_path, target_path, symlinks=True)
    else:
        shutil.copy2(source_path, target_path)


def _create_graph_db_at_path(
    *,
    file_path: Path,
    normalized_path: Path,
    request: CreateGraphDbRequest,
    logical_prefix: str,
) -> None:
    """创建空知识图谱资源数据库。"""
    import sqlite3

    file_path.parent.mkdir(parents=True, exist_ok=True)

    graph_id = (
        request.graph_id.strip()
        if request.graph_id
        else _resource_id_from_db_path(normalized_path, ".graph.db")
    )
    graph_name = request.name.strip() if request.name else graph_id
    graph_desc = request.description or ""

    try:
        with sqlite3.connect(str(file_path)) as conn:
            # 使用 DELETE journal，避免新建资源后文件树出现 -wal / -shm 临时文件。
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _aiasys_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS entities (
                    entity_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    entity_type TEXT NOT NULL,
                    description TEXT,
                    properties TEXT,
                    source_doc_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS relations (
                    relation_id TEXT PRIMARY KEY,
                    source_entity_id TEXT NOT NULL,
                    target_entity_id TEXT NOT NULL,
                    relation_type TEXT NOT NULL,
                    description TEXT,
                    strength REAL DEFAULT 1.0,
                    properties TEXT,
                    source_doc_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS communities (
                    community_id TEXT PRIMARY KEY,
                    level INTEGER NOT NULL,
                    entity_ids TEXT,
                    summary TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS graph_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    layout_positions TEXT,
                    layout_updated_at TEXT,
                    entity_count INTEGER DEFAULT 0,
                    relation_count INTEGER DEFAULT 0,
                    community_count INTEGER DEFAULT 0
                )
            """)
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("id", graph_id),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("resource_type", "graph"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("renderer_hint", "knowledge_graph_preview"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                ("db_path", f"{logical_prefix}/{normalized_path.as_posix()}"),
            )
            conn.execute(
                "INSERT OR REPLACE INTO graph_metadata (key, value) VALUES (?, ?)",
                ("name", graph_name),
            )
            if graph_desc:
                conn.execute(
                    "INSERT OR REPLACE INTO graph_metadata (key, value) VALUES (?, ?)",
                    ("description", graph_desc),
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"创建知识图谱数据库失败: {exc}") from exc


def _write_knowledge_db_metadata(
    *,
    file_path: Path,
    normalized_path: Path,
    kb_id: str,
    name: str,
    description: str,
    logical_prefix: str,
) -> None:
    import sqlite3

    try:
        with sqlite3.connect(str(file_path)) as conn:
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS _aiasys_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            metadata = {
                "id": kb_id,
                "knowledge_base_id": kb_id,
                "name": name,
                "description": description,
                "resource_type": "knowledge",
                "renderer_hint": "knowledge_base_preview",
                "db_path": f"{logical_prefix}/{normalized_path.as_posix()}",
            }
            for key, value in metadata.items():
                conn.execute(
                    "INSERT OR REPLACE INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                    (key, value),
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise HTTPException(status_code=500, detail=f"写入知识库文件 metadata 失败: {exc}") from exc


def _knowledge_db_resource_meta(
    *,
    normalized_path: Path,
    kb_id: str,
    name: str,
    description: str,
    logical_prefix: str,
    workspace_id: str | None = None,
    source: str = "workspace_asset",
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": kb_id,
        "knowledge_base_id": kb_id,
        "name": name,
        "description": description,
        "resource_type": "knowledge",
        "renderer_hint": "knowledge_base_preview",
        "db_path": f"{logical_prefix}/{normalized_path.as_posix()}",
        "source": source,
        "relative_path": normalized_path.as_posix(),
    }
    if workspace_id:
        metadata["workspace_id"] = workspace_id
    return metadata


def _graph_db_resource_meta(
    *,
    normalized_path: Path,
    graph_id: str,
    name: str,
    description: str,
    logical_prefix: str,
    workspace_id: str | None = None,
    source: str = "workspace_asset",
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "id": graph_id,
        "name": name,
        "description": description,
        "resource_type": "graph",
        "renderer_hint": "knowledge_graph_preview",
        "db_path": f"{logical_prefix}/{normalized_path.as_posix()}",
        "source": source,
        "relative_path": normalized_path.as_posix(),
    }
    if workspace_id:
        metadata["workspace_id"] = workspace_id
    return metadata


@router.get(
    "/{workspace_id}/files/list",
    response_model=WorkspaceFileListResponse,
)
async def list_workspace_files(
    workspace_id: str,
    directory: Annotated[
        str,
        Query(description="相对目录路径，默认工作区根目录"),
    ] = "",
    recursive: Annotated[
        bool,
        Query(description="是否递归列出子目录文件"),
    ] = False,
    max_depth: Annotated[
        int | None,
        Query(
            ge=0,
            le=20,
            description="递归时相对 directory 的最大目录深度",
        ),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_total: Annotated[
        bool,
        Query(description="是否计算总数"),
    ] = False,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前工作区文件，不依赖 session_id。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    normalized_directory = directory.strip().replace("\\", "/").strip("/")
    if normalized_directory:
        _normalize_relative_path(normalized_directory)

    files: list[dict[str, object]] = []
    total_seen = 0
    next_offset = None
    for relative_path, file_path in _iter_workspace_files(
        workspace_root,
        directory=normalized_directory,
        recursive=recursive,
        max_depth=max_depth,
    ):
        if total_seen < offset:
            total_seen += 1
            continue
        if len(files) >= limit:
            next_offset = total_seen
            break
        files.append(_build_visible_file_info(relative_path, file_path))
        total_seen += 1

    total = None
    if include_total:
        total = sum(
            1
            for _relative_path, _file_path in _iter_workspace_files(
                workspace_root,
                directory=normalized_directory,
                recursive=recursive,
                max_depth=max_depth,
            )
        )

    return WorkspaceFileListResponse(
        files=[FileInfo(**file_info) for file_info in files],
        workspace_id=workspace_id,
        directory=normalized_directory,
        recursive=recursive,
        limit=limit,
        offset=offset,
        returned=len(files),
        has_more=next_offset is not None,
        next_offset=next_offset,
        total=total,
    )


@router.get("/{workspace_id}/files/content/{filename:path}")
async def get_workspace_file_content(
    workspace_id: str,
    filename: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """按 workspace_id 读取工作区文本文件内容"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    file_path = _resolve_workspace_file_path(workspace_root, filename)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_size = file_path.stat().st_size

    try:
        content = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件不是有效的文本文件")

    return {
        "filename": filename,
        "content": content,
        "size": file_size,
    }


@router.put("/{workspace_id}/files/content/{filename:path}")
async def update_workspace_file_content(
    workspace_id: str,
    filename: str,
    request: FileContentRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """按 workspace_id 更新工作区文本文件内容。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    normalized_path = _normalize_relative_path(filename)
    file_path = _resolve_workspace_file_path(
        workspace_root,
        normalized_path.as_posix(),
    )

    if not _is_editable_file(file_path.name):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，只允许: {', '.join(sorted(EDITABLE_EXTENSIONS))}",
        )

    content_bytes = request.content.encode("utf-8")
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        workspace_root,
        normalized_path,
        operation="before_update",
        current_user=current_user,
    )
    file_path.write_bytes(content_bytes)
    logger.info(
        "工作区文件内容更新: %s/%s/%s",
        current_user.user_id,
        workspace_id,
        normalized_path.as_posix(),
    )

    return {
        "success": True,
        "filename": normalized_path.as_posix(),
        "size": len(content_bytes),
        "updated_by": current_user.user_id,
    }


@router.get(
    "/{workspace_id}/files/csv-preview/{filename:path}",
    response_model=CsvPreviewResponse,
)
async def get_workspace_csv_preview(
    workspace_id: str,
    filename: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    column_offset: int = Query(default=0, ge=0),
    column_limit: int = Query(default=50, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    """按 workspace_id 分页读取工作区 CSV 文件。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    file_path = _resolve_workspace_file_path(workspace_root, filename)
    return _read_csv_preview_page(
        file_path,
        filename=filename,
        page=page,
        page_size=page_size,
        column_offset=column_offset,
        column_limit=column_limit,
        editable=_is_editable_file(file_path.name),
    )


@router.put("/{workspace_id}/files/csv-preview/{filename:path}")
async def update_workspace_csv_preview(
    workspace_id: str,
    filename: str,
    request: CsvPageUpdateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """保存 workspace_id 作用域下 CSV 当前页单元格修改。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    normalized_path = _normalize_relative_path(filename)
    file_path = _ensure_path_within_root(workspace_root, normalized_path)
    if not _is_editable_file(file_path.name):
        raise HTTPException(status_code=400, detail="当前文件不可编辑")

    _record_file_history(
        workspace_root,
        normalized_path,
        operation="before_update",
        current_user=current_user,
    )
    updated_rows = _update_csv_preview_page(
        file_path,
        rows=request.rows,
        page=request.page,
        page_size=request.page_size,
        column_offset=request.column_offset,
        column_limit=request.column_limit,
    )
    logger.info(
        "工作区 CSV 当前页更新: %s/%s/%s",
        current_user.user_id,
        workspace_id,
        normalized_path.as_posix(),
    )
    return {
        "success": True,
        "filename": normalized_path.as_posix(),
        "updated_rows": updated_rows,
        "size": file_path.stat().st_size,
        "updated_by": current_user.user_id,
    }


@router.get("/{workspace_id}/files/download/{filename:path}")
async def download_workspace_file(
    workspace_id: str,
    filename: str,
    disposition: str = Query(default="attachment"),
    current_user: UserInfo = Depends(require_auth()),
):
    """按 workspace_id 下载工作区文件"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    file_path = _resolve_workspace_file_path(workspace_root, filename)

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    logger.info(f"工作区文件下载: {current_user.user_id}/{workspace_id}/{filename}")

    media_type = mimetypes.guess_type(file_path.name)[0]
    if disposition == "inline":
        return FileResponse(
            file_path,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{file_path.name}"'},
        )

    return FileResponse(
        file_path,
        filename=file_path.name,
        media_type=media_type,
        content_disposition_type="attachment",
    )


@router.post("/{workspace_id}/files/upload")
async def upload_workspace_file(
    workspace_id: str,
    file: UploadFile = File(...),
    path: str | None = Form(default=None),
    current_user: UserInfo = Depends(require_auth()),
):
    """上传文件到工作区根目录（不依赖 session）"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    raw_target_path = path.strip() if path else Path(file.filename).name
    if not raw_target_path:
        raise HTTPException(status_code=400, detail="Invalid filename")
    normalized_path = _normalize_relative_path(raw_target_path)
    if normalized_path.as_posix() in {"metadata.json", "history.json", "file_snapshots.json"}:
        raise HTTPException(status_code=400, detail="Invalid filename")

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    workspace_root.mkdir(parents=True, exist_ok=True)

    file_path = _ensure_path_within_root(workspace_root, normalized_path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        workspace_root,
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    with open(file_path, "wb") as f:
        from .files_utils import _copyfileobj_with_limit

        _copyfileobj_with_limit(file.file, f)

    logger.info(
        f"工作区文件上传: {current_user.user_id}/{workspace_id}/{normalized_path.as_posix()}"
    )

    return {
        "success": True,
        "filename": normalized_path.as_posix(),
        "path": f"/workspace/{normalized_path.as_posix()}",
        "size": file_path.stat().st_size,
        "uploaded_by": current_user.user_id,
    }


@router.post("/{workspace_id}/files/create")
async def create_workspace_file(
    workspace_id: str,
    request: FileCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在工作区根目录中创建文件或文件夹"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    normalized_path = _normalize_relative_path(request.path.strip())
    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)

    file_path = _ensure_path_within_root(workspace_root, normalized_path)
    existed_before = file_path.exists()
    if existed_before and not request.overwrite:
        raise HTTPException(status_code=409, detail="文件已存在")

    content_bytes = request.content.encode("utf-8") if request.content else b""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        workspace_root,
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    file_path.write_bytes(content_bytes)

    logger.info(
        f"工作区文件创建: {current_user.user_id}/{workspace_id}/{normalized_path.as_posix()}"
    )

    return FileCreateResponse(
        success=True,
        filename=normalized_path.as_posix(),
        path=f"/workspace/{normalized_path.as_posix()}",
        size=len(content_bytes),
        overwritten=existed_before,
        created_by=current_user.user_id,
    )


@router.post("/{workspace_id}/files/create-knowledge-db", response_model=FileCreateResponse)
async def create_knowledge_db_file(
    workspace_id: str,
    request: CreateKnowledgeDbRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在工作区中创建知识库 .kb.db 资源文件，并登记为可用知识库。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    normalized_path = _normalize_resource_db_path(
        request.path,
        required_suffix=".kb.db",
        resource_label="知识库",
    )
    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    file_path = _ensure_path_within_root(workspace_root, normalized_path)
    existed_before = file_path.exists()
    if existed_before and not request.overwrite:
        raise HTTPException(status_code=409, detail="文件已存在")

    kb_name = (
        request.name.strip()
        if request.name
        else _resource_id_from_db_path(normalized_path, ".kb.db")
    )
    kb_description = request.description or ""
    kb = SQLiteKBService().create_knowledge_base(
        current_user.user_id,
        KnowledgeBaseCreate(name=kb_name, description=kb_description),
    )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        workspace_root,
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    _write_knowledge_db_metadata(
        file_path=file_path,
        normalized_path=normalized_path,
        kb_id=kb.id,
        name=kb.name,
        description=kb.description or "",
        logical_prefix="/workspace",
    )

    logger.info(
        "知识库文件创建: %s/%s/%s -> %s",
        current_user.user_id,
        workspace_id,
        normalized_path.as_posix(),
        kb.id,
    )

    return FileCreateResponse(
        success=True,
        filename=normalized_path.as_posix(),
        path=f"/workspace/{normalized_path.as_posix()}",
        size=file_path.stat().st_size,
        overwritten=existed_before,
        created_by=current_user.user_id,
        meta=_knowledge_db_resource_meta(
            normalized_path=normalized_path,
            kb_id=kb.id,
            name=kb.name,
            description=kb.description or "",
            logical_prefix="/workspace",
            workspace_id=workspace_id,
            source="workspace_asset",
        ),
    )


@router.post("/{workspace_id}/files/create-graph-db", response_model=FileCreateResponse)
async def create_graph_db_file(
    workspace_id: str,
    request: CreateGraphDbRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在工作区中创建空的知识图谱 .db 文件并初始化表结构。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    normalized_path = _normalize_resource_db_path(
        request.path,
        required_suffix=".graph.db",
        resource_label="知识图谱",
    )
    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    file_path = _ensure_path_within_root(workspace_root, normalized_path)
    existed_before = file_path.exists()
    if existed_before and not request.overwrite:
        raise HTTPException(status_code=409, detail="文件已存在")

    graph_id = (
        request.graph_id.strip()
        if request.graph_id
        else _resource_id_from_db_path(normalized_path, ".graph.db")
    )
    graph_name = request.name.strip() if request.name else graph_id
    graph_description = request.description or ""
    _record_file_history(
        workspace_root,
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    _create_graph_db_at_path(
        file_path=file_path,
        normalized_path=normalized_path,
        request=request,
        logical_prefix="/workspace",
    )

    logger.info(
        "知识图谱文件创建: %s/%s/%s",
        current_user.user_id,
        workspace_id,
        normalized_path.as_posix(),
    )

    return FileCreateResponse(
        success=True,
        filename=normalized_path.as_posix(),
        path=f"/workspace/{normalized_path.as_posix()}",
        size=file_path.stat().st_size,
        overwritten=existed_before,
        created_by=current_user.user_id,
        meta=_graph_db_resource_meta(
            normalized_path=normalized_path,
            graph_id=graph_id,
            name=graph_name,
            description=graph_description,
            logical_prefix="/workspace",
            workspace_id=workspace_id,
            source="workspace_asset",
        ),
    )


@router.delete("/{workspace_id}/files/{filename:path}")
async def delete_workspace_file(
    workspace_id: str,
    filename: str,
    recursive: bool = Query(default=False, description="递归删除目录"),
    current_user: UserInfo = Depends(require_auth()),
):
    """删除工作区文件。目录删除需显式传入 recursive=true。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    file_path = _resolve_workspace_file_path(workspace_root, filename)

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    normalized_path = _normalize_relative_path(filename)
    _record_tree_history(
        workspace_root,
        normalized_path,
        operation="before_delete",
        current_user=current_user,
    )
    if file_path.is_dir():
        if not recursive:
            raise HTTPException(
                status_code=400,
                detail="目标是一个目录，需要传入 recursive=true 才能删除",
            )
        shutil.rmtree(file_path)
    else:
        file_path.unlink()

    logger.info(f"工作区文件删除: {current_user.user_id}/{workspace_id}/{filename}")

    return {"success": True, "filename": filename}


@router.post("/{workspace_id}/files/copy", response_model=FileCopyResponse)
async def copy_workspace_file(
    workspace_id: str,
    request: FileCopyRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """按 workspace_id 复制工作区文件或文件夹。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    normalized_source = _normalize_relative_path(request.source)
    normalized_target = _normalize_relative_path(request.target)
    source_path = _resolve_workspace_file_path(
        workspace_root,
        normalized_source.as_posix(),
    )
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="源文件不存在")
    target_path = _ensure_path_within_root(workspace_root, normalized_target)
    _copy_file_or_directory(source_path, target_path)

    logger.info(
        "工作区文件复制: %s/%s %s -> %s",
        current_user.user_id,
        workspace_id,
        request.source,
        request.target,
    )

    return FileCopyResponse(
        success=True,
        source=request.source,
        target=request.target,
        copied_by=current_user.user_id,
    )


@router.put("/{workspace_id}/files/move", response_model=FileMoveResponse)
async def move_workspace_file(
    workspace_id: str,
    request: FileMoveRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """按 workspace_id 移动或重命名工作区文件或文件夹。"""

    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    normalized_source = _normalize_relative_path(request.source)
    normalized_target = _normalize_relative_path(request.target)
    source_path = _resolve_workspace_file_path(
        workspace_root,
        normalized_source.as_posix(),
    )
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="源文件不存在")

    target_path = _ensure_path_within_root(workspace_root, normalized_target)
    if target_path.exists():
        raise HTTPException(status_code=409, detail="目标已存在")

    if source_path.is_dir():
        try:
            target_path.resolve().relative_to(source_path.resolve())
            raise HTTPException(status_code=400, detail="不能将文件夹移动到自身内部")
        except ValueError:
            pass

    _record_tree_history(
        workspace_root,
        normalized_source,
        operation="before_move",
        current_user=current_user,
        target_path=normalized_target,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(target_path))
    file_history_service.move_entries(
        workspace_root,
        normalized_source.as_posix(),
        normalized_target.as_posix(),
    )

    logger.info(
        "工作区文件移动: %s/%s %s -> %s",
        current_user.user_id,
        workspace_id,
        request.source,
        request.target,
    )

    return FileMoveResponse(
        success=True,
        source=request.source,
        target=request.target,
        moved_by=current_user.user_id,
    )


@router.get(
    "/{workspace_id}/files/history/list/{filename:path}",
    response_model=FileHistoryListResponse,
)
async def list_workspace_file_history(
    workspace_id: str,
    filename: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前工作区文件历史。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    normalized_path = _normalize_relative_path(filename)
    entries = file_history_service.list_entries(
        workspace_root,
        normalized_path.as_posix(),
    )
    return FileHistoryListResponse(
        scope="workspace",
        workspace_id=workspace_id,
        filename=normalized_path.as_posix(),
        entries=[_file_history_entry_response(entry) for entry in entries],
    )


@router.get(
    "/{workspace_id}/files/history/entries/{entry_id}/content",
    response_model=FileHistoryContentResponse,
)
async def get_workspace_file_history_content(
    workspace_id: str,
    entry_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取当前工作区文件历史内容。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        entry, content = file_history_service.read_entry_text(workspace_root, entry_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileHistoryContentResponse(
        entry=_file_history_entry_response(entry),
        content=content,
        size=entry.size,
    )


@router.get(
    "/{workspace_id}/files/history/entries/{entry_id}/diff",
    response_model=FileHistoryDiffResponse,
)
async def get_workspace_file_history_diff(
    workspace_id: str,
    entry_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """返回历史内容和当前工作区文件的 unified diff。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        entry, result = file_history_service.diff_entry_result(
            workspace_root,
            entry_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _file_history_diff_response(entry, result)


@router.post(
    "/{workspace_id}/files/history/entries/{entry_id}/restore",
    response_model=FileHistoryRestoreResponse,
)
async def restore_workspace_file_history_entry(
    workspace_id: str,
    entry_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """将当前工作区文件恢复到指定历史内容。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        entry, size = file_history_service.restore_entry(
            workspace_root,
            entry_id,
            source="api",
            source_detail=current_user.user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileHistoryRestoreResponse(
        success=True,
        filename=entry.file_path,
        restored_entry_id=entry.id,
        size=size,
    )


class RecentChangeItem(BaseModel):
    file_path: str
    latest_entry: FileHistoryEntryResponse
    total_versions: int


class RecentChangesResponse(BaseModel):
    scope: Literal["workspace", "global"]
    workspace_id: str
    files: list[RecentChangeItem]


@router.get(
    "/{workspace_id}/files/history/recent-changes",
    response_model=RecentChangesResponse,
)
async def list_workspace_recent_changes(
    workspace_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出当前工作区最近有变更的文件，按时间倒序。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    changes = file_history_service.list_recent_changes(workspace_root, limit=limit)
    files = [
        RecentChangeItem(
            file_path=file_path,
            latest_entry=_file_history_entry_response(latest_entry),
            total_versions=total_versions,
        )
        for file_path, latest_entry, total_versions in changes
    ]
    return RecentChangesResponse(scope="workspace", workspace_id=workspace_id, files=files)


@router.get(
    "/{workspace_id}/global-workspace/history/recent-changes",
    response_model=RecentChangesResponse,
)
async def list_global_workspace_recent_changes(
    workspace_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出用户默认层全局工作区最近有变更的文件，按时间倒序。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc

    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    changes = file_history_service.list_recent_changes(global_root, limit=limit)
    files = [
        RecentChangeItem(
            file_path=file_path,
            latest_entry=_file_history_entry_response(latest_entry),
            total_versions=total_versions,
        )
        for file_path, latest_entry, total_versions in changes
    ]
    return RecentChangesResponse(scope="global", workspace_id=workspace_id, files=files)


@router.get(
    "/{workspace_id}/global-workspace/tree",
    response_model=WorkspaceResourcesTreeResponse,
)
async def get_global_workspace_resources_tree(
    workspace_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取用户默认层全局工作区的文件资产树。"""
    from app.core import config as config_module
    from app.services.memory.layout import ensure_memory_layout

    global_workspace_dir = (
        config_module.WORKSPACE_DIR / current_user.user_id / config_module.GLOBAL_WORKSPACE_DIR_NAME
    )
    ensure_memory_layout(global_workspace_dir / config_module.GLOBAL_WORKSPACE_MEMORY_DIR_NAME)
    nodes = _scan_workspace_file_assets(
        global_workspace_dir,
        workspace_id=workspace_id,
        logical_prefix="/global",
        source="global_workspace_asset",
    )
    return WorkspaceResourcesTreeResponse(nodes=nodes)


@router.get("/{workspace_id}/global-workspace/content/{asset_path:path}")
async def get_global_workspace_file_content(
    workspace_id: str,
    asset_path: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取用户默认层全局工作区中的文本文件内容。"""
    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        asset_path,
    )

    if not global_path.exists() or not global_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    file_size = global_path.stat().st_size
    editable = _is_editable_file(global_path.name)

    try:
        content = global_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件不是有效的文本文件")

    return FileContentResponse(
        filename=asset_path,
        content=content,
        size=file_size,
        editable=editable,
    )


@router.get(
    "/{workspace_id}/global-workspace/csv-preview/{asset_path:path}",
    response_model=CsvPreviewResponse,
)
async def get_global_workspace_csv_preview(
    workspace_id: str,
    asset_path: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
    column_offset: int = Query(default=0, ge=0),
    column_limit: int = Query(default=50, ge=1, le=200),
    current_user: UserInfo = Depends(require_auth()),
):
    """分页读取用户默认层全局工作区 CSV 文件。"""
    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        asset_path,
    )
    return _read_csv_preview_page(
        global_path,
        filename=asset_path,
        page=page,
        page_size=page_size,
        column_offset=column_offset,
        column_limit=column_limit,
        editable=_is_editable_file(global_path.name),
    )


@router.put("/{workspace_id}/global-workspace/csv-preview/{asset_path:path}")
async def update_global_workspace_csv_preview(
    workspace_id: str,
    asset_path: str,
    request: CsvPageUpdateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """保存用户默认层全局工作区 CSV 当前页单元格修改。"""
    normalized_path = _normalize_relative_path(asset_path)
    if not _is_editable_file(normalized_path.name):
        raise HTTPException(status_code=400, detail="当前文件不可编辑")

    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_path.as_posix(),
    )
    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    _record_file_history(
        global_root,
        normalized_path,
        operation="before_update",
        current_user=current_user,
    )
    updated_rows = _update_csv_preview_page(
        global_path,
        rows=request.rows,
        page=request.page,
        page_size=request.page_size,
        column_offset=request.column_offset,
        column_limit=request.column_limit,
    )
    logger.info(
        "全局工作区 CSV 当前页更新: %s/%s",
        current_user.user_id,
        normalized_path.as_posix(),
    )
    return {
        "success": True,
        "filename": normalized_path.as_posix(),
        "updated_rows": updated_rows,
        "size": global_path.stat().st_size,
        "updated_by": current_user.user_id,
    }


@router.put("/{workspace_id}/global-workspace/content/{asset_path:path}")
async def update_global_workspace_file_content(
    workspace_id: str,
    asset_path: str,
    request: FileContentRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新用户默认层全局工作区中的文本文件内容。"""
    normalized_path = _normalize_relative_path(asset_path)
    if not _is_editable_file(normalized_path.name):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，只允许: {', '.join(sorted(EDITABLE_EXTENSIONS))}",
        )

    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_path.as_posix(),
    )
    content_bytes = request.content.encode("utf-8")
    global_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        _resolve_user_global_workspace_root(current_user.user_id),
        normalized_path,
        operation="before_update",
        current_user=current_user,
    )
    global_path.write_bytes(content_bytes)

    logger.info(
        "全局工作区文件更新: %s/%s",
        current_user.user_id,
        normalized_path.as_posix(),
    )

    return {
        "success": True,
        "filename": normalized_path.as_posix(),
        "size": len(content_bytes),
        "updated_by": current_user.user_id,
    }


@router.get("/{workspace_id}/global-workspace/download/{asset_path:path}")
async def download_global_workspace_file(
    workspace_id: str,
    asset_path: str,
    disposition: str = Query(default="attachment"),
    current_user: UserInfo = Depends(require_auth()),
):
    """下载用户默认层全局工作区中的文件。"""
    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        asset_path,
    )
    if not global_path.exists() or not global_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    media_type = mimetypes.guess_type(global_path.name)[0]
    if disposition == "inline":
        return FileResponse(
            global_path,
            media_type=media_type,
            headers={"Content-Disposition": f'inline; filename="{global_path.name}"'},
        )

    return FileResponse(
        global_path,
        filename=global_path.name,
        media_type=media_type,
        content_disposition_type="attachment",
    )


@router.post(
    "/{workspace_id}/global-workspace/create",
    response_model=FileCreateResponse,
)
async def create_global_workspace_file(
    workspace_id: str,
    request: FileCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在用户默认层全局工作区中创建文件或文件夹标记。"""
    normalized_path = _normalize_relative_path(request.path.strip())
    if not _is_editable_file(normalized_path.name):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型，只允许: {', '.join(sorted(EDITABLE_EXTENSIONS))}",
        )

    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_path.as_posix(),
    )
    existed_before = global_path.exists()
    if existed_before and not request.overwrite:
        raise HTTPException(status_code=409, detail="文件已存在")

    content_bytes = request.content.encode("utf-8") if request.content else b""
    global_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        _resolve_user_global_workspace_root(current_user.user_id),
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    global_path.write_bytes(content_bytes)

    logger.info(
        "全局工作区文件创建: %s/%s",
        current_user.user_id,
        normalized_path.as_posix(),
    )

    return FileCreateResponse(
        success=True,
        filename=normalized_path.as_posix(),
        path=f"/global/{normalized_path.as_posix()}",
        size=len(content_bytes),
        overwritten=existed_before,
        created_by=current_user.user_id,
    )


@router.post(
    "/{workspace_id}/global-workspace/create-knowledge-db",
    response_model=FileCreateResponse,
)
async def create_global_workspace_knowledge_db_file(
    workspace_id: str,
    request: CreateKnowledgeDbRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在用户默认层全局工作区中创建知识库 .kb.db 资源文件。"""
    normalized_path = _normalize_resource_db_path(
        request.path,
        required_suffix=".kb.db",
        resource_label="知识库",
    )
    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_path.as_posix(),
    )
    existed_before = global_path.exists()
    if existed_before and not request.overwrite:
        raise HTTPException(status_code=409, detail="文件已存在")

    kb_name = (
        request.name.strip()
        if request.name
        else _resource_id_from_db_path(normalized_path, ".kb.db")
    )
    kb_description = request.description or ""
    kb = SQLiteKBService().create_knowledge_base(
        current_user.user_id,
        KnowledgeBaseCreate(name=kb_name, description=kb_description),
    )
    global_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        _resolve_user_global_workspace_root(current_user.user_id),
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    _write_knowledge_db_metadata(
        file_path=global_path,
        normalized_path=normalized_path,
        kb_id=kb.id,
        name=kb.name,
        description=kb.description or "",
        logical_prefix="/global",
    )

    logger.info(
        "全局知识库文件创建: %s/%s -> %s",
        current_user.user_id,
        normalized_path.as_posix(),
        kb.id,
    )

    return FileCreateResponse(
        success=True,
        filename=normalized_path.as_posix(),
        path=f"/global/{normalized_path.as_posix()}",
        size=global_path.stat().st_size,
        overwritten=existed_before,
        created_by=current_user.user_id,
        meta=_knowledge_db_resource_meta(
            normalized_path=normalized_path,
            kb_id=kb.id,
            name=kb.name,
            description=kb.description or "",
            logical_prefix="/global",
            workspace_id=workspace_id,
            source="global_workspace_asset",
        ),
    )


@router.post(
    "/{workspace_id}/global-workspace/create-graph-db",
    response_model=FileCreateResponse,
)
async def create_global_workspace_graph_db_file(
    workspace_id: str,
    request: CreateGraphDbRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在用户默认层全局工作区中创建知识图谱 .graph.db 资源文件。"""
    normalized_path = _normalize_resource_db_path(
        request.path,
        required_suffix=".graph.db",
        resource_label="知识图谱",
    )
    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_path.as_posix(),
    )
    existed_before = global_path.exists()
    if existed_before and not request.overwrite:
        raise HTTPException(status_code=409, detail="文件已存在")

    graph_id = (
        request.graph_id.strip()
        if request.graph_id
        else _resource_id_from_db_path(normalized_path, ".graph.db")
    )
    graph_name = request.name.strip() if request.name else graph_id
    graph_description = request.description or ""
    _record_file_history(
        _resolve_user_global_workspace_root(current_user.user_id),
        normalized_path,
        operation="before_overwrite",
        current_user=current_user,
    )
    _create_graph_db_at_path(
        file_path=global_path,
        normalized_path=normalized_path,
        request=request,
        logical_prefix="/global",
    )

    logger.info(
        "全局知识图谱文件创建: %s/%s",
        current_user.user_id,
        normalized_path.as_posix(),
    )

    return FileCreateResponse(
        success=True,
        filename=normalized_path.as_posix(),
        path=f"/global/{normalized_path.as_posix()}",
        size=global_path.stat().st_size,
        overwritten=existed_before,
        created_by=current_user.user_id,
        meta=_graph_db_resource_meta(
            normalized_path=normalized_path,
            graph_id=graph_id,
            name=graph_name,
            description=graph_description,
            logical_prefix="/global",
            workspace_id=workspace_id,
            source="global_workspace_asset",
        ),
    )


@router.post(
    "/{workspace_id}/global-workspace/copy",
    response_model=FileCopyResponse,
)
async def copy_global_workspace_file(
    workspace_id: str,
    request: FileCopyRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """复制用户默认层全局工作区中的文件或文件夹。"""
    normalized_source = _normalize_relative_path(request.source)
    normalized_target = _normalize_relative_path(request.target)
    source_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_source.as_posix(),
    )
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="源文件不存在")
    target_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_target.as_posix(),
    )
    _copy_file_or_directory(source_path, target_path)

    logger.info(
        "全局工作区文件复制: %s %s -> %s",
        current_user.user_id,
        request.source,
        request.target,
    )

    return FileCopyResponse(
        success=True,
        source=request.source,
        target=request.target,
        copied_by=current_user.user_id,
    )


@router.put(
    "/{workspace_id}/global-workspace/move",
    response_model=FileMoveResponse,
)
async def move_global_workspace_file(
    workspace_id: str,
    request: FileMoveRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """移动或重命名用户默认层全局工作区中的文件或文件夹。"""
    normalized_source = _normalize_relative_path(request.source)
    normalized_target = _normalize_relative_path(request.target)
    source_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_source.as_posix(),
    )
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="源文件不存在")
    target_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        normalized_target.as_posix(),
    )
    if target_path.exists():
        raise HTTPException(status_code=409, detail="目标已存在")
    if source_path.is_dir():
        try:
            target_path.resolve().relative_to(source_path.resolve())
            raise HTTPException(status_code=400, detail="不能将文件夹移动到自身内部")
        except ValueError:
            pass

    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    _record_tree_history(
        global_root,
        normalized_source,
        operation="before_move",
        current_user=current_user,
        target_path=normalized_target,
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_path), str(target_path))
    file_history_service.move_entries(
        global_root,
        normalized_source.as_posix(),
        normalized_target.as_posix(),
    )

    logger.info(
        "全局工作区文件移动: %s %s -> %s",
        current_user.user_id,
        request.source,
        request.target,
    )

    return FileMoveResponse(
        success=True,
        source=request.source,
        target=request.target,
        moved_by=current_user.user_id,
    )


@router.get(
    "/{workspace_id}/global-workspace/history/list/{asset_path:path}",
    response_model=FileHistoryListResponse,
)
async def list_global_workspace_file_history(
    workspace_id: str,
    asset_path: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出用户默认层全局工作区文件历史。"""
    normalized_path = _normalize_relative_path(asset_path)
    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    entries = file_history_service.list_entries(
        global_root,
        normalized_path.as_posix(),
    )
    return FileHistoryListResponse(
        scope="global",
        workspace_id=workspace_id,
        filename=normalized_path.as_posix(),
        entries=[_file_history_entry_response(entry) for entry in entries],
    )


@router.get(
    "/{workspace_id}/global-workspace/history/entries/{entry_id}/content",
    response_model=FileHistoryContentResponse,
)
async def get_global_workspace_file_history_content(
    workspace_id: str,
    entry_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """读取用户默认层全局工作区文件历史内容。"""
    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    try:
        entry, content = file_history_service.read_entry_text(global_root, entry_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileHistoryContentResponse(
        entry=_file_history_entry_response(entry),
        content=content,
        size=entry.size,
    )


@router.get(
    "/{workspace_id}/global-workspace/history/entries/{entry_id}/diff",
    response_model=FileHistoryDiffResponse,
)
async def get_global_workspace_file_history_diff(
    workspace_id: str,
    entry_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """返回全局工作区历史内容和当前文件的 unified diff。"""
    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    try:
        entry, result = file_history_service.diff_entry_result(
            global_root,
            entry_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return _file_history_diff_response(entry, result)


@router.post(
    "/{workspace_id}/global-workspace/history/entries/{entry_id}/restore",
    response_model=FileHistoryRestoreResponse,
)
async def restore_global_workspace_file_history_entry(
    workspace_id: str,
    entry_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """将全局工作区文件恢复到指定历史内容。"""
    global_root = _resolve_user_global_workspace_root(current_user.user_id)
    try:
        entry, size = file_history_service.restore_entry(
            global_root,
            entry_id,
            source="api",
            source_detail=current_user.user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return FileHistoryRestoreResponse(
        success=True,
        filename=entry.file_path,
        restored_entry_id=entry.id,
        size=size,
    )


@router.post("/{workspace_id}/global-workspace/upload")
async def upload_global_workspace_file(
    workspace_id: str,
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(require_auth()),
):
    """上传文件到用户默认层全局工作区根目录。"""
    safe_filename = Path(file.filename).name
    if (
        not safe_filename
        or safe_filename == "."
        or ".." in safe_filename
        or safe_filename in {"metadata.json", "history.json", "file_snapshots.json"}
    ):
        raise HTTPException(status_code=400, detail="Invalid filename")

    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        safe_filename,
    )
    global_path.parent.mkdir(parents=True, exist_ok=True)
    _record_file_history(
        _resolve_user_global_workspace_root(current_user.user_id),
        safe_filename,
        operation="before_overwrite",
        current_user=current_user,
    )
    with open(global_path, "wb") as f:
        from .files_utils import _copyfileobj_with_limit

        _copyfileobj_with_limit(file.file, f)

    logger.info("全局工作区文件上传: %s/%s", current_user.user_id, safe_filename)

    return {
        "success": True,
        "filename": safe_filename,
        "path": f"/global/{safe_filename}",
        "size": global_path.stat().st_size,
        "uploaded_by": current_user.user_id,
    }


@router.delete("/{workspace_id}/global-workspace/{asset_path:path}")
async def delete_global_workspace_file(
    workspace_id: str,
    asset_path: str,
    recursive: bool = Query(default=False, description="递归删除目录"),
    current_user: UserInfo = Depends(require_auth()),
):
    """删除用户默认层全局工作区文件。目录删除需显式传入 recursive=true。"""
    global_path = _resolve_user_global_workspace_file_path(
        current_user.user_id,
        asset_path,
    )
    if not global_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")
    normalized_path = _normalize_relative_path(asset_path)
    _record_tree_history(
        _resolve_user_global_workspace_root(current_user.user_id),
        normalized_path,
        operation="before_delete",
        current_user=current_user,
    )
    if global_path.is_dir():
        if not recursive:
            raise HTTPException(
                status_code=400,
                detail="目标是一个目录，需要传入 recursive=true 才能删除",
            )
        shutil.rmtree(global_path)
    else:
        global_path.unlink()

    logger.info("全局工作区文件删除: %s/%s", current_user.user_id, asset_path)
    return {"success": True, "filename": asset_path}
