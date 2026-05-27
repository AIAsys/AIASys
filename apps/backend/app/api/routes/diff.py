"""通用差异对比 API。"""

from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Literal

import anyio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.core.config import get_user_global_workspace_dir
from app.models.user import UserInfo
from app.services.diff_service import (
    DiffTooLargeError,
    DirectoryDiffEntry,
    DirectoryDiffResult,
    FileDiffResult,
    TextDiffResult,
    diff_service,
)
from app.services.workspace_registry import get_workspace_registry_service

router = APIRouter(prefix="/diff", tags=["diff"])


class DiffStatsResponse(BaseModel):
    additions: int = 0
    deletions: int = 0
    left_lines: int = 0
    right_lines: int = 0


class TextDiffSide(BaseModel):
    content: str
    label: str | None = None


class TextDiffRequest(BaseModel):
    left: TextDiffSide
    right: TextDiffSide
    include_text: bool = True


class TextDiffResponse(BaseModel):
    left_label: str
    right_label: str
    left_text: str | None = None
    right_text: str | None = None
    unified_diff: str
    status: Literal["added", "deleted", "modified", "unchanged", "skipped"]
    format: Literal["unified"] = "unified"
    can_show_content: bool = True
    skip_reason: str | None = None
    stats: DiffStatsResponse


class DiffPathRef(BaseModel):
    scope: Literal["workspace", "global"]
    path: str
    workspace_id: str | None = None
    label: str | None = None


class FileDiffRequest(BaseModel):
    left: DiffPathRef
    right: DiffPathRef
    include_text: bool = True


class FileDiffResponse(TextDiffResponse):
    left_exists: bool
    right_exists: bool
    left_size: int | None = None
    right_size: int | None = None
    left_sha256: str | None = None
    right_sha256: str | None = None
    is_binary: bool = False
    is_too_large: bool = False


class DirectoryDiffRequest(BaseModel):
    left: DiffPathRef
    right: DiffPathRef
    include_unchanged: bool = False
    max_files: int = Field(default=1000, ge=1, le=5000)


class DirectoryDiffEntryResponse(BaseModel):
    path: str
    status: Literal["added", "deleted", "modified", "unchanged", "skipped"]
    left_size: int | None = None
    right_size: int | None = None
    left_sha256: str | None = None
    right_sha256: str | None = None


class DirectoryDiffResponse(BaseModel):
    left_label: str
    right_label: str
    files: list[DirectoryDiffEntryResponse]
    counts: dict[str, int]
    total_files: int
    included_files: int
    include_unchanged: bool
    max_files: int


def _normalize_relative_path(relative_path: str) -> Path:
    normalized = Path(relative_path.replace("\\", "/"))
    if (
        not relative_path.strip()
        or normalized.is_absolute()
        or any(part == ".." for part in normalized.parts)
    ):
        raise HTTPException(status_code=400, detail="无效的文件路径")
    return normalized


def _ensure_path_within_root(root: Path, relative_path: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    target = (root / relative_path).resolve()
    root_resolved = root.resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Access denied") from exc
    return target


def _resolve_path_ref(ref: DiffPathRef, current_user: UserInfo) -> tuple[Path, str]:
    normalized_path = _normalize_relative_path(ref.path)
    if ref.scope == "global":
        root = get_user_global_workspace_dir(current_user.user_id)
        label = ref.label or f"/global/{normalized_path.as_posix()}"
        return _ensure_path_within_root(root, normalized_path), label

    if not ref.workspace_id:
        raise HTTPException(status_code=400, detail="workspace scope 需要 workspace_id")
    service = get_workspace_registry_service()
    try:
        service.get_workspace(
            current_user.user_id,
            ref.workspace_id,
            include_conversations=False,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Operation failed") from exc
    root = service.get_workspace_root(current_user.user_id, ref.workspace_id)
    label = ref.label or f"/workspace/{normalized_path.as_posix()}"
    return _ensure_path_within_root(root, normalized_path), label


def _stats_response(stats) -> DiffStatsResponse:
    return DiffStatsResponse(
        additions=stats.additions,
        deletions=stats.deletions,
        left_lines=stats.left_lines,
        right_lines=stats.right_lines,
    )


def _text_response(result: TextDiffResult) -> TextDiffResponse:
    return TextDiffResponse(
        left_label=result.left_label,
        right_label=result.right_label,
        left_text=result.left_text,
        right_text=result.right_text,
        unified_diff=result.unified_diff,
        status=result.status,
        format=result.format,
        can_show_content=result.can_show_content,
        skip_reason=result.skip_reason,
        stats=_stats_response(result.stats),
    )


def _file_response(result: FileDiffResult) -> FileDiffResponse:
    return FileDiffResponse(
        left_label=result.left_label,
        right_label=result.right_label,
        left_text=result.left_text,
        right_text=result.right_text,
        unified_diff=result.unified_diff,
        status=result.status,
        format=result.format,
        can_show_content=result.can_show_content,
        skip_reason=result.skip_reason,
        stats=_stats_response(result.stats),
        left_exists=result.left_exists,
        right_exists=result.right_exists,
        left_size=result.left_size,
        right_size=result.right_size,
        left_sha256=result.left_sha256,
        right_sha256=result.right_sha256,
        is_binary=result.is_binary,
        is_too_large=result.is_too_large,
    )


def _directory_entry_response(entry: DirectoryDiffEntry) -> DirectoryDiffEntryResponse:
    return DirectoryDiffEntryResponse(
        path=entry.path,
        status=entry.status,
        left_size=entry.left_size,
        right_size=entry.right_size,
        left_sha256=entry.left_sha256,
        right_sha256=entry.right_sha256,
    )


def _directory_response(result: DirectoryDiffResult) -> DirectoryDiffResponse:
    return DirectoryDiffResponse(
        left_label=result.left_label,
        right_label=result.right_label,
        files=[_directory_entry_response(entry) for entry in result.files],
        counts=result.counts,
        total_files=result.total_files,
        included_files=result.included_files,
        include_unchanged=result.include_unchanged,
        max_files=result.max_files,
    )


@router.post("/text", response_model=TextDiffResponse)
async def compare_text_diff(
    request: TextDiffRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    del current_user
    result = await anyio.to_thread.run_sync(
        partial(
            diff_service.compare_text,
            left_label=request.left.label or "left",
            right_label=request.right.label or "right",
            include_text=request.include_text,
        ),
        request.left.content,
        request.right.content,
    )
    return _text_response(result)


@router.post("/files", response_model=FileDiffResponse)
async def compare_file_diff(
    request: FileDiffRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    left_path, left_label = _resolve_path_ref(request.left, current_user)
    right_path, right_label = _resolve_path_ref(request.right, current_user)
    try:
        result = await anyio.to_thread.run_sync(
            partial(
                diff_service.compare_files,
                left_label=left_label,
                right_label=right_label,
                include_text=request.include_text,
            ),
            left_path,
            right_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DiffTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _file_response(result)


@router.post("/directories", response_model=DirectoryDiffResponse)
async def compare_directory_diff(
    request: DirectoryDiffRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    left_path, left_label = _resolve_path_ref(request.left, current_user)
    right_path, right_label = _resolve_path_ref(request.right, current_user)
    try:
        result = await anyio.to_thread.run_sync(
            partial(
                diff_service.compare_directories,
                left_label=left_label,
                right_label=right_label,
                include_unchanged=request.include_unchanged,
                max_files=request.max_files,
            ),
            left_path,
            right_path,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DiffTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _directory_response(result)
