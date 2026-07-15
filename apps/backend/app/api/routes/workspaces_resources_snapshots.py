"""工作区快照（版本）API。"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.workspace_registry import get_workspace_registry_service
from app.services.workspace_snapshots import SwitchMode, workspace_snapshot_service

logger = logging.getLogger(__name__)

router = APIRouter()


class CreateSnapshotRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=1000)


class SnapshotResponse(BaseModel):
    id: str
    workspace_id: str
    title: str
    description: str | None
    created_at: str
    created_by: str
    source: str
    source_detail: str | None
    file_count: int


class SnapshotDetailResponse(SnapshotResponse):
    files: dict[str, str | None]


class SnapshotListResponse(BaseModel):
    workspace_id: str
    snapshots: list[SnapshotResponse]
    total: int


class ApplySnapshotRequest(BaseModel):
    mode: SwitchMode = Field(
        default="soft", description="soft 只恢复快照中存在的文件；hard 完全对齐快照状态"
    )


class ApplySnapshotResponse(BaseModel):
    success: bool
    snapshot_id: str
    backup_snapshot_id: str
    restored_files: list[str]
    deleted_files: list[str]
    unchanged_files: list[str]
    skipped_files: list[str]


class DiffSnapshotItem(BaseModel):
    file_path: str
    snapshot_entry_id: str | None
    current_entry_id: str | None


class DiffSnapshotResponse(BaseModel):
    snapshot_id: str
    workspace_id: str
    changes: list[DiffSnapshotItem]


def _snapshot_response(snapshot) -> SnapshotResponse:
    return SnapshotResponse(
        id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        title=snapshot.title,
        description=snapshot.description,
        created_at=snapshot.created_at,
        created_by=snapshot.created_by,
        source=snapshot.source,
        source_detail=snapshot.source_detail,
        file_count=len(snapshot.files),
    )


def _snapshot_detail_response(snapshot) -> SnapshotDetailResponse:
    return SnapshotDetailResponse(
        id=snapshot.id,
        workspace_id=snapshot.workspace_id,
        title=snapshot.title,
        description=snapshot.description,
        created_at=snapshot.created_at,
        created_by=snapshot.created_by,
        source=snapshot.source,
        source_detail=snapshot.source_detail,
        file_count=len(snapshot.files),
        files=dict(snapshot.files),
    )


@router.post("/{workspace_id}/snapshots", response_model=SnapshotResponse)
async def create_workspace_snapshot(
    workspace_id: str,
    request: CreateSnapshotRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """手动保存当前工作区状态为一个快照。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        snapshot = workspace_snapshot_service.create_snapshot(
            workspace_root,
            workspace_id,
            title=request.title,
            description=request.description,
            created_by=current_user.user_id,
            source="manual",
        )
    except Exception as exc:
        logger.error("创建工作区快照失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="创建快照失败") from exc

    return _snapshot_response(snapshot)


@router.get("/{workspace_id}/snapshots", response_model=SnapshotListResponse)
async def list_workspace_snapshots(
    workspace_id: str,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    source: Annotated[str | None, Query()] = None,
    current_user: UserInfo = Depends(require_auth()),
):
    """列出工作区快照，按创建时间倒序。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        snapshots = workspace_snapshot_service.list_snapshots(
            workspace_root,
            limit=limit,
            offset=offset,
            source=source,  # type: ignore[arg-type]
        )
    except Exception as exc:
        logger.error("列出工作区快照失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="列出快照失败") from exc

    all_snapshots = workspace_snapshot_service.list_snapshots(workspace_root, limit=10000)
    return SnapshotListResponse(
        workspace_id=workspace_id,
        snapshots=[_snapshot_response(s) for s in snapshots],
        total=len(all_snapshots),
    )


@router.get("/{workspace_id}/snapshots/{snapshot_id}", response_model=SnapshotDetailResponse)
async def get_workspace_snapshot(
    workspace_id: str,
    snapshot_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取单个快照详情。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        snapshot = workspace_snapshot_service.get_snapshot(workspace_root, snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="快照不存在") from exc
    except Exception as exc:
        logger.error("获取工作区快照失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="获取快照失败") from exc

    return _snapshot_detail_response(snapshot)


@router.post("/{workspace_id}/snapshots/{snapshot_id}/apply", response_model=ApplySnapshotResponse)
async def apply_workspace_snapshot(
    workspace_id: str,
    snapshot_id: str,
    request: ApplySnapshotRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """切换或重置到指定快照。操作前会自动备份当前状态。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        result = workspace_snapshot_service.apply_snapshot(
            workspace_root,
            workspace_id,
            snapshot_id,
            mode=request.mode,
            actor=current_user.user_id,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="快照不存在") from exc
    except Exception as exc:
        logger.error("应用工作区快照失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="应用快照失败") from exc

    return ApplySnapshotResponse(
        success=True,
        snapshot_id=snapshot_id,
        backup_snapshot_id=result.backup_snapshot_id or "",
        restored_files=result.restored_files,
        deleted_files=result.deleted_files,
        unchanged_files=result.unchanged_files,
        skipped_files=result.skipped_files,
    )


@router.get("/{workspace_id}/snapshots/{snapshot_id}/diff", response_model=DiffSnapshotResponse)
async def diff_workspace_snapshot(
    workspace_id: str,
    snapshot_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """对比快照与当前工作区，返回路径级差异。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        changes = workspace_snapshot_service.diff_snapshot(workspace_root, snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="快照不存在") from exc
    except Exception as exc:
        logger.error("对比工作区快照失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="对比快照失败") from exc

    return DiffSnapshotResponse(
        snapshot_id=snapshot_id,
        workspace_id=workspace_id,
        changes=[
            DiffSnapshotItem(
                file_path=file_path,
                snapshot_entry_id=snapshot_entry_id,
                current_entry_id=current_entry_id,
            )
            for file_path, snapshot_entry_id, current_entry_id in changes
        ],
    )


@router.delete("/{workspace_id}/snapshots/{snapshot_id}")
async def delete_workspace_snapshot(
    workspace_id: str,
    snapshot_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """删除快照（只删除 manifest，不删除底层文件历史）。"""
    service = get_workspace_registry_service()
    try:
        service.get_workspace(current_user.user_id, workspace_id, include_conversations=False)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="工作区不存在") from exc

    workspace_root = service.get_workspace_root(current_user.user_id, workspace_id)
    try:
        workspace_snapshot_service.delete_snapshot(workspace_root, snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="快照不存在") from exc
    except Exception as exc:
        logger.error("删除工作区快照失败: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail="删除快照失败") from exc

    return {"success": True, "snapshot_id": snapshot_id}
