"""多维数据表 API 路由"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core import config as config_module
from app.core.auth import require_auth
from app.models.user import UserInfo
from app.services.data_table_service import (
    DataTableColumnDef,
    DataTableCreateRequest,
    DataTableCreateResult,
    add_data_table_column,
    create_data_table,
    delete_data_table_record,
    insert_data_table_records,
    read_data_table_records,
    read_data_table_schema,
    remove_data_table_column,
    update_data_table_column,
    update_data_table_record,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/workspaces")


def _get_workspace_root(user_id: str, workspace_id: str) -> Path:
    """获取工作区根目录"""
    from app.services.workspace_registry import get_workspace_registry_service

    service = get_workspace_registry_service()
    try:
        service.get_workspace(user_id, workspace_id, include_conversations=False)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Workspace not found")

    return service.get_workspace_root(user_id, workspace_id)


def _get_global_workspace_root(user_id: str) -> Path:
    """获取用户默认层全局工作区根目录。"""
    root = config_module.get_user_global_workspace_dir(user_id)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _resolve_table_path(workspace_root: Path, table_path: str) -> Path:
    """解析数据表文件路径，防止路径穿越"""
    root = workspace_root.resolve()
    target = (root / table_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Invalid table path") from exc
    if target.suffix.lower() != ".db" or ".table." not in target.name:
        raise HTTPException(status_code=400, detail="Not a data table file")
    return target


def _create_table(root: Path, request: DataTableCreateRequest) -> DataTableCreateResult:
    try:
        return create_data_table(root, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _read_table_schema(root: Path, table_path: str) -> dict:
    file_path = _resolve_table_path(root, table_path)
    try:
        return read_data_table_schema(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data table not found")


def _read_table_records(
    root: Path, table_path: str, *, limit: int, offset: int
) -> DataTableRecordsResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        records = read_data_table_records(file_path, limit=limit, offset=offset)
        return DataTableRecordsResponse(
            records=records,
            limit=limit,
            offset=offset,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data table not found")


def _insert_records(
    root: Path, table_path: str, request: InsertRecordsRequest
) -> InsertRecordsResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        inserted_ids = insert_data_table_records(file_path, request.records)
        return InsertRecordsResponse(
            inserted_ids=inserted_ids,
            count=len(inserted_ids),
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data table not found")


def _update_record(
    root: Path, table_path: str, record_id: str, request: UpdateRecordRequest
) -> UpdateRecordResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        updated = update_data_table_record(file_path, record_id, request.data)
        return UpdateRecordResponse(updated=updated)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data table not found")


def _delete_record(root: Path, table_path: str, record_id: str) -> DeleteRecordResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        deleted = delete_data_table_record(file_path, record_id)
        return DeleteRecordResponse(deleted=deleted)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data table not found")


def _add_column(root: Path, table_path: str, request: AddColumnRequest) -> ColumnOperationResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        column_def = DataTableColumnDef(
            name=request.name,
            type=request.type,
            options=request.options or [],
            required=request.required,
            precision=request.precision,
        )
        add_data_table_column(file_path, column_def)
        return ColumnOperationResponse(success=True)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Column operation failed: %s", exc)
        raise HTTPException(status_code=400, detail="Column operation failed") from exc


def _remove_column(root: Path, table_path: str, column_name: str) -> ColumnOperationResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        remove_data_table_column(file_path, column_name)
        return ColumnOperationResponse(success=True)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Column operation failed: %s", exc)
        raise HTTPException(status_code=400, detail="Column operation failed") from exc


def _update_column(
    root: Path,
    table_path: str,
    column_name: str,
    request: UpdateColumnRequest,
) -> ColumnOperationResponse:
    file_path = _resolve_table_path(root, table_path)
    try:
        schema = read_data_table_schema(file_path)
        old_col = next((c for c in schema["columns"] if c["name"] == column_name), None)
        if not old_col:
            raise ValueError(f"列 '{column_name}' 不存在")

        new_def = DataTableColumnDef(
            name=request.name if request.name is not None else old_col["name"],
            type=request.type if request.type is not None else old_col["type"],
            options=(request.options if request.options is not None else old_col.get("options"))
            or [],
            required=(
                request.required if request.required is not None else old_col.get("required", False)
            ),
            precision=(
                request.precision if request.precision is not None else old_col.get("precision")
            ),
        )
        update_data_table_column(file_path, column_name, new_def)
        return ColumnOperationResponse(success=True)
    except (FileNotFoundError, ValueError) as exc:
        logger.error("Column operation failed: %s", exc)
        raise HTTPException(status_code=400, detail="Column operation failed") from exc


# ---------------------------------------------------------------------------
# 创建数据表
# ---------------------------------------------------------------------------


@router.post(
    "/{workspace_id}/data-tables",
    response_model=DataTableCreateResult,
)
async def create_workspace_data_table(
    workspace_id: str,
    request: DataTableCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在工作区中创建一个新的多维数据表。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(_create_table, workspace_root, request)


@router.post(
    "/{workspace_id}/global-workspace/data-tables",
    response_model=DataTableCreateResult,
)
async def create_global_workspace_data_table(
    workspace_id: str,
    request: DataTableCreateRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """在用户默认层全局工作区中创建一个新的多维数据表。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _create_table, _get_global_workspace_root(current_user.user_id), request
    )


# ---------------------------------------------------------------------------
# 读取数据表 Schema
# ---------------------------------------------------------------------------


class DataTableSchemaResponse(BaseModel):
    metadata: dict
    columns: list[dict]


@router.get("/{workspace_id}/data-tables/{table_path:path}/schema")
async def get_data_table_schema(
    workspace_id: str,
    table_path: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取数据表的 schema 定义。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(_read_table_schema, workspace_root, table_path)


@router.get("/{workspace_id}/global-workspace/data-tables/{table_path:path}/schema")
async def get_global_data_table_schema(
    workspace_id: str,
    table_path: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取用户默认层全局工作区数据表的 schema 定义。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _read_table_schema,
        _get_global_workspace_root(current_user.user_id),
        table_path,
    )


# ---------------------------------------------------------------------------
# 读取数据表记录
# ---------------------------------------------------------------------------


class DataTableRecordsResponse(BaseModel):
    records: list[dict]
    limit: int
    offset: int


@router.get("/{workspace_id}/data-tables/{table_path:path}/records")
async def get_data_table_records(
    workspace_id: str,
    table_path: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取数据表的记录列表。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _read_table_records,
        workspace_root,
        table_path,
        limit=limit,
        offset=offset,
    )


@router.get("/{workspace_id}/global-workspace/data-tables/{table_path:path}/records")
async def get_global_data_table_records(
    workspace_id: str,
    table_path: str,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
    current_user: UserInfo = Depends(require_auth()),
):
    """获取用户默认层全局工作区数据表的记录列表。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _read_table_records,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        limit=limit,
        offset=offset,
    )


# ---------------------------------------------------------------------------
# 插入记录
# ---------------------------------------------------------------------------


class InsertRecordsRequest(BaseModel):
    records: list[dict] = Field(..., min_length=1)


class InsertRecordsResponse(BaseModel):
    inserted_ids: list[str]
    count: int


@router.post("/{workspace_id}/data-tables/{table_path:path}/records")
async def post_data_table_records(
    workspace_id: str,
    table_path: str,
    request: InsertRecordsRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """向数据表插入新记录。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(_insert_records, workspace_root, table_path, request)


@router.post("/{workspace_id}/global-workspace/data-tables/{table_path:path}/records")
async def post_global_data_table_records(
    workspace_id: str,
    table_path: str,
    request: InsertRecordsRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """向用户默认层全局工作区数据表插入新记录。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _insert_records,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        request,
    )


# ---------------------------------------------------------------------------
# 更新记录
# ---------------------------------------------------------------------------


class UpdateRecordRequest(BaseModel):
    data: dict = Field(..., min_length=1)


class UpdateRecordResponse(BaseModel):
    updated: bool


@router.put("/{workspace_id}/data-tables/{table_path:path}/records/{record_id}")
async def put_data_table_record(
    workspace_id: str,
    table_path: str,
    record_id: str,
    request: UpdateRecordRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新数据表中的一条记录。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _update_record, workspace_root, table_path, record_id, request
    )


@router.put("/{workspace_id}/global-workspace/data-tables/{table_path:path}/records/{record_id}")
async def put_global_data_table_record(
    workspace_id: str,
    table_path: str,
    record_id: str,
    request: UpdateRecordRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """更新用户默认层全局工作区数据表中的一条记录。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _update_record,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        record_id,
        request,
    )


# ---------------------------------------------------------------------------
# 删除记录
# ---------------------------------------------------------------------------


class DeleteRecordResponse(BaseModel):
    deleted: bool


@router.delete("/{workspace_id}/data-tables/{table_path:path}/records/{record_id}")
async def delete_data_table_record_endpoint(
    workspace_id: str,
    table_path: str,
    record_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """删除数据表中的一条记录。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(_delete_record, workspace_root, table_path, record_id)


@router.delete("/{workspace_id}/global-workspace/data-tables/{table_path:path}/records/{record_id}")
async def delete_global_data_table_record_endpoint(
    workspace_id: str,
    table_path: str,
    record_id: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """删除用户默认层全局工作区数据表中的一条记录。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _delete_record,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        record_id,
    )


# ---------------------------------------------------------------------------
# Schema 列管理
# ---------------------------------------------------------------------------


class AddColumnRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(
        ..., pattern="^(text|number|date|single_select|multi_select|checkbox|file|url)$"
    )
    options: list[str] | None = None
    required: bool = False
    precision: int | None = None


class UpdateColumnRequest(BaseModel):
    name: str | None = None
    type: str | None = None
    options: list[str] | None = None
    required: bool | None = None
    precision: int | None = None


class ColumnOperationResponse(BaseModel):
    success: bool


@router.post("/{workspace_id}/data-tables/{table_path:path}/schema/columns")
async def add_column_endpoint(
    workspace_id: str,
    table_path: str,
    request: AddColumnRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """向数据表添加一列。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(_add_column, workspace_root, table_path, request)


@router.post("/{workspace_id}/global-workspace/data-tables/{table_path:path}/schema/columns")
async def add_global_column_endpoint(
    workspace_id: str,
    table_path: str,
    request: AddColumnRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """向用户默认层全局工作区数据表添加一列。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _add_column,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        request,
    )


@router.delete("/{workspace_id}/data-tables/{table_path:path}/schema/columns/{column_name}")
async def remove_column_endpoint(
    workspace_id: str,
    table_path: str,
    column_name: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """从数据表删除一列。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(_remove_column, workspace_root, table_path, column_name)


@router.delete(
    "/{workspace_id}/global-workspace/data-tables/{table_path:path}/schema/columns/{column_name}"
)
async def remove_global_column_endpoint(
    workspace_id: str,
    table_path: str,
    column_name: str,
    current_user: UserInfo = Depends(require_auth()),
):
    """从用户默认层全局工作区数据表删除一列。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _remove_column,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        column_name,
    )


@router.put("/{workspace_id}/data-tables/{table_path:path}/schema/columns/{column_name}")
async def update_column_endpoint(
    workspace_id: str,
    table_path: str,
    column_name: str,
    request: UpdateColumnRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """修改数据表的一列定义。"""
    workspace_root = _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _update_column, workspace_root, table_path, column_name, request
    )


@router.put(
    "/{workspace_id}/global-workspace/data-tables/{table_path:path}/schema/columns/{column_name}"
)
async def update_global_column_endpoint(
    workspace_id: str,
    table_path: str,
    column_name: str,
    request: UpdateColumnRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    """修改用户默认层全局工作区数据表的一列定义。"""
    _get_workspace_root(current_user.user_id, workspace_id)
    return await asyncio.to_thread(
        _update_column,
        _get_global_workspace_root(current_user.user_id),
        table_path,
        column_name,
        request,
    )
