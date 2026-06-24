"""
工作区数据库文件查询端点
支持 SQLite (.db, .sqlite, .sqlite3) 和 DuckDB (.duckdb) 文件的
Schema 查看与 SQL 查询。
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import require_auth
from app.core.config import get_user_global_workspace_dir
from app.models.user import UserInfo
from app.utils.path_utils import as_system_path

from .files_utils import (
    _check_user_access,
    _ensure_path_within_root,
    _normalize_relative_path,
    _resolve_workspace_path,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/file-database")

# 合法的 SQL 表名/列名：字母或下划线开头，后跟字母数字下划线
_VALID_SQL_IDENTIFIER = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


def _validate_sql_identifier(name: str, context: str = "") -> bool:
    """校验 SQL 标识符，防止 f-string 拼接注入。"""
    if not _VALID_SQL_IDENTIFIER.match(name):
        logger.warning("拒绝不合法的 SQL 标识符%s: %r", f" ({context})" if context else "", name)
        return False
    return True


class FileDatabaseQueryRequest(BaseModel):
    sql: str


class FileDatabaseColumnInfo(BaseModel):
    name: str
    type: str | None = None


class FileDatabaseTableInfo(BaseModel):
    name: str
    columns: list[FileDatabaseColumnInfo]


class FileDatabaseSchemaResponse(BaseModel):
    tables: list[FileDatabaseTableInfo]


class FileDatabaseQueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int


def _get_file_path(user_id: str, session_id: str, filename: str) -> Path:
    return _resolve_workspace_path(user_id, session_id, filename)


def _get_global_file_path(user_id: str, filename: str) -> Path:
    normalized_path = _normalize_relative_path(filename)
    return _ensure_path_within_root(
        get_user_global_workspace_dir(user_id),
        normalized_path,
    )


def _detect_db_type(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".duckdb":
        return "duckdb"
    if ext in (".db", ".sqlite", ".sqlite3"):
        return "sqlite"
    # 也根据文件 magic bytes 判断
    try:
        with open(as_system_path(str(file_path)), "rb") as f:
            header = f.read(16)
        if header.startswith(b"SQLite format 3"):
            return "sqlite"
    except OSError:
        logger.debug("读取数据库文件 magic bytes 失败: %s", file_path, exc_info=True)
    return "unknown"


def _read_file_database_schema(file_path: Path) -> FileDatabaseSchemaResponse:
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    db_type = _detect_db_type(file_path)
    if db_type == "unknown":
        raise HTTPException(status_code=400, detail="不支持的数据库文件类型")

    try:
        if db_type == "sqlite":
            conn = sqlite3.connect(as_system_path(str(file_path)))
            try:
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
                table_names = [row[0] for row in cursor.fetchall()]

                tables: list[FileDatabaseTableInfo] = []
                for table_name in table_names:
                    if not _validate_sql_identifier(table_name, context="SQLite table_info"):
                        continue
                    # PRAGMA does not support parameterized queries; table_name is validated by _validate_sql_identifier above
                    cursor = conn.execute(f'PRAGMA table_info("{table_name}")')
                    columns = [
                        FileDatabaseColumnInfo(name=row[1], type=row[2])
                        for row in cursor.fetchall()
                    ]
                    tables.append(FileDatabaseTableInfo(name=table_name, columns=columns))
            finally:
                conn.close()
            return FileDatabaseSchemaResponse(tables=tables)

        import duckdb

        conn = duckdb.connect(str(file_path), read_only=True)
        try:
            result = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main' ORDER BY table_name"
            ).fetchall()
            table_names = [row[0] for row in result]

            tables = []
            for table_name in table_names:
                if not _validate_sql_identifier(table_name, context="DuckDB information_schema"):
                    continue
                result = conn.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name = ? AND table_schema = 'main' "
                    "ORDER BY ordinal_position",
                    (table_name,),
                ).fetchall()
                columns = [FileDatabaseColumnInfo(name=row[0], type=row[1]) for row in result]
                tables.append(FileDatabaseTableInfo(name=table_name, columns=columns))
        finally:
            conn.close()
        return FileDatabaseSchemaResponse(tables=tables)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取数据库 schema 失败: {e}")
        raise HTTPException(status_code=500, detail="获取 schema 失败") from e


def _query_file_database(
    file_path: Path,
    request: FileDatabaseQueryRequest,
) -> FileDatabaseQueryResponse:
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    db_type = _detect_db_type(file_path)
    if db_type == "unknown":
        raise HTTPException(status_code=400, detail="不支持的数据库文件类型")

    sql = request.sql.strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL 不能为空")

    first_word = sql.split(maxsplit=1)[0] if sql else ""
    if not re.match(r"^SELECT\b", first_word, re.IGNORECASE):
        raise HTTPException(status_code=400, detail="只允许执行 SELECT 查询")

    try:
        if db_type == "sqlite":
            conn = sqlite3.connect(as_system_path(str(file_path)))
            try:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(sql)
                columns = [desc[0] for desc in cursor.description] if cursor.description else []
                rows = [list(row) for row in cursor.fetchall()]
            finally:
                conn.close()
            return FileDatabaseQueryResponse(columns=columns, rows=rows, row_count=len(rows))

        import duckdb

        conn = duckdb.connect(str(file_path), read_only=True)
        try:
            result = conn.execute(sql).fetchdf()
            columns = list(result.columns)
            rows = [list(row) for row in result.values]
        finally:
            conn.close()
        return FileDatabaseQueryResponse(columns=columns, rows=rows, row_count=len(rows))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"数据库查询失败: {e}")
        raise HTTPException(status_code=400, detail="查询失败") from e


@router.get("/schema/{user_id}/global/{filename:path}")
async def get_global_file_database_schema(
    user_id: str,
    filename: str,
    current_user: UserInfo = Depends(require_auth()),
) -> FileDatabaseSchemaResponse:
    """获取用户默认层全局工作区数据库文件的表结构。"""
    _check_user_access(current_user, user_id)
    return await asyncio.to_thread(
        _read_file_database_schema, _get_global_file_path(user_id, filename)
    )


@router.post("/query/{user_id}/global/{filename:path}")
async def query_global_file_database(
    user_id: str,
    filename: str,
    request: FileDatabaseQueryRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> FileDatabaseQueryResponse:
    """查询用户默认层全局工作区数据库文件。"""
    _check_user_access(current_user, user_id)
    return await asyncio.to_thread(
        _query_file_database, _get_global_file_path(user_id, filename), request
    )


@router.get("/schema/{user_id}/{session_id}/{filename:path}")
async def get_file_database_schema(
    user_id: str,
    session_id: str,
    filename: str,
    current_user: UserInfo = Depends(require_auth()),
) -> FileDatabaseSchemaResponse:
    """获取数据库文件的表结构。"""
    _check_user_access(current_user, user_id)
    return await asyncio.to_thread(
        _read_file_database_schema, _get_file_path(user_id, session_id, filename)
    )


@router.post("/query/{user_id}/{session_id}/{filename:path}")
async def query_file_database(
    user_id: str,
    session_id: str,
    filename: str,
    request: FileDatabaseQueryRequest,
    current_user: UserInfo = Depends(require_auth()),
) -> FileDatabaseQueryResponse:
    """对数据库文件执行 SQL 查询。"""
    _check_user_access(current_user, user_id)
    return await asyncio.to_thread(
        _query_file_database, _get_file_path(user_id, session_id, filename), request
    )
