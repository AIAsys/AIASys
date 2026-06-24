"""多维数据表服务。

负责创建、读取和管理以 SQLite 为存储载体的结构化数据表资源。
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from app.utils.path_utils import as_system_path

logger = logging.getLogger(__name__)

# 数据表支持的字段类型
DATA_TABLE_FIELD_TYPES = {
    "text",
    "number",
    "date",
    "single_select",
    "multi_select",
    "checkbox",
    "file",
    "url",
}


class DataTableColumnDef(BaseModel):
    """数据表列定义"""

    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(
        ..., pattern=r"^(text|number|date|single_select|multi_select|checkbox|file|url)$"
    )
    required: bool = False
    options: list[str] = Field(default_factory=list)
    precision: int | None = None


class DataTableCreateRequest(BaseModel):
    """创建数据表请求"""

    name: str = Field(..., min_length=1, max_length=200)
    id: str = Field(..., min_length=1, max_length=200)
    directory: str = ""
    columns: list[DataTableColumnDef] = Field(..., min_length=1)


class DataTableCreateResult(BaseModel):
    """创建数据表结果"""

    file_path: str
    relative_path: str
    id: str
    name: str
    record_count: int = 0


def _sanitize_filename(name: str) -> str:
    """清理文件名，去除危险字符"""
    import re

    # 保留中文、英文、数字、空格、下划线、连字符
    sanitized = re.sub(r"[^\w\s\u4e00-\u9fff\-_.]", "", name)
    return sanitized.strip() or "untitled"


def create_data_table(
    workspace_root: Path,
    request: DataTableCreateRequest,
) -> DataTableCreateResult:
    """在工作区目录下创建一个新的多维数据表（SQLite .db 文件）。

    Args:
        workspace_root: 工作区根目录路径
        request: 创建请求，包含名称、ID、目录和列定义

    Returns:
        DataTableCreateResult: 创建结果，包含文件路径等信息
    """
    for column in request.columns:
        _validate_column_name(column.name)

    safe_name = _sanitize_filename(request.name)
    file_name = f"{safe_name}.table.db"

    root = workspace_root.resolve()
    if request.directory:
        directory = request.directory.replace("\\", "/").strip().strip("/")
        directory_path = Path(directory)
        if directory_path.is_absolute() or ".." in directory_path.parts:
            raise ValueError("数据表目录包含非法路径片段")
        target_dir = (root / directory_path).resolve()
    else:
        target_dir = root

    if not (target_dir == root or target_dir.is_relative_to(root)):
        raise ValueError("数据表目录超出工作区范围")

    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / file_name

    # 如果文件已存在，追加数字后缀
    counter = 1
    while file_path.exists():
        file_name = f"{safe_name}_{counter}.table.db"
        file_path = target_dir / file_name
        counter += 1

    # 创建 SQLite 文件
    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        # 使用默认的 DELETE journal 模式，避免生成 .db-wal / .db-shm 临时文件
        conn.execute("PRAGMA journal_mode=DELETE")

        # 1. 创建 _aiasys_metadata 表（key/value 格式）
        conn.execute("CREATE TABLE _aiasys_metadata (key TEXT PRIMARY KEY, value TEXT)")
        metadata_items = {
            "resource_type": "data_table",
            "id": request.id,
            "name": request.name,
            "version": "1",
            "schema_version": "1",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        for key, value in metadata_items.items():
            conn.execute(
                "INSERT INTO _aiasys_metadata (key, value) VALUES (?, ?)",
                (key, value),
            )

        # 2. 创建 _schema 表
        conn.execute(
            "CREATE TABLE _schema ("
            "column_name TEXT PRIMARY KEY,"
            "data_type TEXT NOT NULL,"
            "options_json TEXT,"
            "order_index INTEGER NOT NULL,"
            "required INTEGER NOT NULL DEFAULT 0,"
            "precision INTEGER"
            ")"
        )
        for idx, col in enumerate(request.columns):
            conn.execute(
                "INSERT INTO _schema (column_name, data_type, options_json, order_index, required, precision)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (
                    col.name,
                    col.type,
                    json.dumps(col.options, ensure_ascii=False) if col.options else None,
                    idx,
                    1 if col.required else 0,
                    col.precision,
                ),
            )

        # 3. 创建数据表 records
        # 系统字段
        column_defs = [
            "_id TEXT PRIMARY KEY",
            "_created_at TEXT NOT NULL",
            "_updated_at TEXT NOT NULL",
        ]
        # 用户定义字段
        for col in request.columns:
            if col.type in ("number", "checkbox"):
                sqlite_type = "REAL" if col.type == "number" else "INTEGER"
            else:
                sqlite_type = "TEXT"
            column_defs.append(f'"{col.name}" {sqlite_type}')

        create_table_sql = f"CREATE TABLE records ({', '.join(column_defs)})"
        conn.execute(create_table_sql)

        conn.commit()
    finally:
        conn.close()

    relative_path = file_path.relative_to(root).as_posix()
    return DataTableCreateResult(
        file_path=str(file_path),
        relative_path=relative_path,
        id=request.id,
        name=request.name,
        record_count=0,
    )


def read_data_table_schema(file_path: Path) -> dict:
    """读取数据表的 schema 定义。

    Args:
        file_path: 数据表 .db 文件路径

    Returns:
        dict: 包含 metadata 和 columns 的字典
    """
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    conn = sqlite3.connect(as_system_path(str(file_path)))
    conn.row_factory = sqlite3.Row
    try:
        # 读取 metadata
        meta_rows = conn.execute("SELECT key, value FROM _aiasys_metadata").fetchall()
        metadata = {row["key"]: row["value"] for row in meta_rows}

        # 读取 schema
        schema_rows = conn.execute(
            "SELECT column_name, data_type, options_json, order_index, required, precision"
            " FROM _schema ORDER BY order_index"
        ).fetchall()
        columns = []
        for row in schema_rows:
            col = {
                "name": row["column_name"],
                "type": row["data_type"],
                "order_index": row["order_index"],
                "required": bool(row["required"]),
            }
            if row["options_json"]:
                try:
                    col["options"] = json.loads(row["options_json"])
                except json.JSONDecodeError:
                    col["options"] = []
            if row["precision"] is not None:
                col["precision"] = row["precision"]
            columns.append(col)

        return {"metadata": metadata, "columns": columns}
    finally:
        conn.close()


def read_data_table_records(
    file_path: Path,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    """读取数据表的记录。

    Args:
        file_path: 数据表 .db 文件路径
        limit: 返回的最大记录数
        offset: 偏移量

    Returns:
        list[dict]: 记录列表
    """
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    conn = sqlite3.connect(as_system_path(str(file_path)))
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT * FROM records ORDER BY _created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def insert_data_table_records(
    file_path: Path,
    records: list[dict],
) -> list[str]:
    """向数据表插入记录。

    Args:
        file_path: 数据表 .db 文件路径
        records: 记录数据列表，每个记录是列名到值的字典

    Returns:
        list[str]: 新插入记录的 _id 列表
    """
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        # 读取 schema 确定合法列
        schema_rows = conn.execute("SELECT column_name FROM _schema").fetchall()
        valid_columns = {row[0] for row in schema_rows}
        valid_columns |= {"_id", "_created_at", "_updated_at"}

        inserted_ids: list[str] = []
        now = datetime.now(timezone.utc).isoformat()

        for record in records:
            record_id = str(uuid.uuid4())
            # 过滤掉不存在的列
            clean_record = {
                k: v for k, v in record.items() if k in valid_columns and not k.startswith("_")
            }

            columns = ["_id", "_created_at", "_updated_at"] + list(clean_record.keys())
            placeholders = ", ".join(["?"] * len(columns))
            values = [record_id, now, now] + list(clean_record.values())

            sql = f"INSERT INTO records ({', '.join(columns)}) VALUES ({placeholders})"
            conn.execute(sql, values)
            inserted_ids.append(record_id)

        conn.commit()
        return inserted_ids
    finally:
        conn.close()


def update_data_table_record(
    file_path: Path,
    record_id: str,
    data: dict,
) -> bool:
    """更新数据表中的一条记录。

    Args:
        file_path: 数据表 .db 文件路径
        record_id: 记录 ID
        data: 要更新的列数据

    Returns:
        bool: 是否成功更新
    """
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        # 读取 schema 确定合法列
        schema_rows = conn.execute("SELECT column_name FROM _schema").fetchall()
        valid_columns = {row[0] for row in schema_rows}

        clean_data = {k: v for k, v in data.items() if k in valid_columns and not k.startswith("_")}

        if not clean_data:
            return False

        now = datetime.now(timezone.utc).isoformat()
        set_clauses = ", ".join([f'"{k}" = ?' for k in clean_data.keys()])
        values = list(clean_data.values()) + [now, record_id]

        sql = f"UPDATE records SET {set_clauses}, _updated_at = ? WHERE _id = ?"
        cursor = conn.execute(sql, values)
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def delete_data_table_record(file_path: Path, record_id: str) -> bool:
    """删除数据表中的一条记录。

    Args:
        file_path: 数据表 .db 文件路径
        record_id: 记录 ID

    Returns:
        bool: 是否成功删除
    """
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        cursor = conn.execute("DELETE FROM records WHERE _id = ?", (record_id,))
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


# 安全列名验证：仅允许字母、数字、下划线、中文字符
_COLUMN_NAME_RE = re.compile(r"^[A-Za-z0-9_一-鿿]+$")


def _validate_column_name(name: str) -> None:
    if not name or not _COLUMN_NAME_RE.match(name):
        raise ValueError(f"列名包含非法字符: {name!r}")


def add_data_table_column(file_path: Path, column: DataTableColumnDef) -> None:
    """向数据表添加一列。"""
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    _validate_column_name(column.name)

    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        # 检查列名是否已存在
        existing = conn.execute(
            "SELECT 1 FROM _schema WHERE column_name = ?", (column.name,)
        ).fetchone()
        if existing:
            raise ValueError(f"列 '{column.name}' 已存在")

        # 获取当前最大 order_index
        max_order = conn.execute("SELECT MAX(order_index) FROM _schema").fetchone()[0] or -1

        # 插入 _schema
        conn.execute(
            "INSERT INTO _schema (column_name, data_type, options_json, order_index, required, precision)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                column.name,
                column.type,
                json.dumps(column.options, ensure_ascii=False) if column.options else None,
                max_order + 1,
                1 if column.required else 0,
                column.precision,
            ),
        )

        # ALTER TABLE records ADD COLUMN
        if column.type in ("number", "checkbox"):
            sqlite_type = "REAL" if column.type == "number" else "INTEGER"
        else:
            sqlite_type = "TEXT"
        conn.execute(f'ALTER TABLE records ADD COLUMN "{column.name}" {sqlite_type}')

        conn.commit()
    finally:
        conn.close()


def remove_data_table_column(file_path: Path, column_name: str) -> None:
    """从数据表删除一列。"""
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    _validate_column_name(column_name)

    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        # 不能删除系统列
        if column_name in ("_id", "_created_at", "_updated_at"):
            raise ValueError("不能删除系统列")

        # 删除 _schema 记录
        cursor = conn.execute("DELETE FROM _schema WHERE column_name = ?", (column_name,))
        if cursor.rowcount == 0:
            raise ValueError(f"列 '{column_name}' 不存在")

        # 重新排序 order_index
        rows = conn.execute("SELECT column_name FROM _schema ORDER BY order_index").fetchall()
        for idx, (name,) in enumerate(rows):
            conn.execute(
                "UPDATE _schema SET order_index = ? WHERE column_name = ?",
                (idx, name),
            )

        # ALTER TABLE records DROP COLUMN (SQLite 3.35.0+)
        conn.execute(f'ALTER TABLE records DROP COLUMN "{column_name}"')

        conn.commit()
    finally:
        conn.close()


def update_data_table_column(
    file_path: Path,
    old_name: str,
    column: DataTableColumnDef,
) -> None:
    """修改数据表的列定义。如果类型发生变化，需要重建表。"""
    if not file_path.exists():
        raise FileNotFoundError(f"数据表文件不存在: {file_path}")

    _validate_column_name(old_name)
    _validate_column_name(column.name)

    conn = sqlite3.connect(as_system_path(str(file_path)))
    try:
        if old_name in ("_id", "_created_at", "_updated_at"):
            raise ValueError("不能修改系统列")

        # 读取旧列的 order_index
        row = conn.execute(
            "SELECT order_index FROM _schema WHERE column_name = ?", (old_name,)
        ).fetchone()
        if not row:
            raise ValueError(f"列 '{old_name}' 不存在")

        # 更新 _schema
        conn.execute(
            "UPDATE _schema SET column_name = ?, data_type = ?, options_json = ?, required = ?, precision = ?"
            " WHERE column_name = ?",
            (
                column.name,
                column.type,
                json.dumps(column.options, ensure_ascii=False) if column.options else None,
                1 if column.required else 0,
                column.precision,
                old_name,
            ),
        )

        # 总是重建 records 表以确保类型正确
        # 读取当前所有列（包括系统列）
        schema_rows = conn.execute(
            "SELECT column_name, data_type FROM _schema ORDER BY order_index"
        ).fetchall()
        user_columns = [(name, dtype) for name, dtype in schema_rows]

        all_columns = [
            ("_id", "TEXT"),
            ("_created_at", "TEXT"),
            ("_updated_at", "TEXT"),
        ] + user_columns

        # 重建表
        col_defs = ", ".join([f'"{name}" {dtype}' for name, dtype in all_columns])
        conn.execute(f"CREATE TABLE records_new ({col_defs})")

        # 复制数据
        # 实际上，由于我们已经更新了 _schema，old_name 已经不存在了
        # 我们需要从旧表中复制所有能复制的列
        old_schema = conn.execute("PRAGMA table_info(records)").fetchall()
        old_col_names = [r[1] for r in old_schema]
        common_cols = [c for c in old_col_names if c != old_name or old_name == column.name]
        if common_cols:
            cols_str = ", ".join([f'"{c}"' for c in common_cols])
            conn.execute(f"INSERT INTO records_new ({cols_str}) SELECT {cols_str} FROM records")

        conn.execute("DROP TABLE records")
        conn.execute("ALTER TABLE records_new RENAME TO records")

        conn.commit()
    finally:
        conn.close()
