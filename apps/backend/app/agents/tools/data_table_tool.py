"""多维数据表 Agent 工具集。"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.data_table_service import (
    DataTableColumnDef,
    DataTableCreateRequest,
    add_data_table_column,
    create_data_table,
    delete_data_table_record,
    insert_data_table_records,
    read_data_table_schema,
    remove_data_table_column,
    update_data_table_column,
    update_data_table_record,
)
from app.services.history import current_global_workspace, current_workspace

logger = logging.getLogger(__name__)


DataTableScope = Literal["workspace", "global"]


def _resolve_current_workspace_dir() -> Path | None:
    workspace = current_workspace.get()
    if workspace is None:
        return None
    return Path(workspace)


def _resolve_current_global_workspace_dir() -> Path | None:
    global_workspace = current_global_workspace.get()
    if global_workspace is None:
        return None
    return Path(global_workspace)


def _resolve_root(scope: DataTableScope) -> Path:
    if scope == "global":
        root = _resolve_current_global_workspace_dir()
        if root is None:
            raise ValueError("当前上下文未设置全局工作区，无法访问 /global/ 多维表")
        return root.resolve()

    root = _resolve_current_workspace_dir()
    if root is None:
        raise ValueError("当前上下文未设置工作区，无法访问多维表")
    return root.resolve()


def _normalize_relative_path(
    path_str: str, *, expected_scope: DataTableScope | None = None
) -> tuple[DataTableScope, str]:
    normalized = str(path_str or "").replace("\\", "/").strip()
    if not normalized:
        raise ValueError("多维表路径不能为空")

    scope: DataTableScope = expected_scope or "workspace"
    if normalized.startswith("/workspace/"):
        scope = "workspace"
        normalized = normalized[len("/workspace/") :]
    elif normalized.startswith("/global/"):
        scope = "global"
        normalized = normalized[len("/global/") :]
    elif normalized.startswith("/"):
        raise ValueError("多维表路径只支持 /workspace/ 或 /global/ 前缀")

    relative = Path(normalized)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"多维表路径 `{path_str}` 包含非法路径片段")
    if not normalized.endswith(".table.db"):
        raise ValueError("多维表文件必须使用 .table.db 后缀")
    return scope, relative.as_posix()


def _resolve_table_path(
    table_path: str, *, expected_scope: DataTableScope | None = None
) -> tuple[Path, Path, DataTableScope, str]:
    scope, relative_path = _normalize_relative_path(table_path, expected_scope=expected_scope)
    root = _resolve_root(scope)
    target = (root / relative_path).resolve()
    if not (target == root or target.is_relative_to(root)):
        raise ValueError(f"多维表路径 `{table_path}` 解析后超出允许范围")
    return root, target, scope, relative_path


def _format_scope(scope: DataTableScope) -> str:
    return "全局工作区" if scope == "global" else "当前工作区"


def _column_from_params(params: "DataTableColumnParams") -> DataTableColumnDef:
    return DataTableColumnDef(
        name=params.name,
        type=params.type,
        required=params.required,
        options=params.options,
        precision=params.precision,
    )


class DataTableColumnParams(BaseModel):
    """多维表列定义。"""

    name: str = Field(description="列名", min_length=1, max_length=100)
    type: Literal[
        "text",
        "number",
        "date",
        "single_select",
        "multi_select",
        "checkbox",
        "file",
        "url",
    ] = Field(description="列类型")
    required: bool = Field(default=False, description="是否必填")
    options: list[str] = Field(default_factory=list, description="单选或多选字段的选项")
    precision: int | None = Field(default=None, description="数字字段精度")

    @field_validator("options", mode="before")
    @classmethod
    def _coerce_options(cls, value: Any) -> Any:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


class CreateDataTableParams(BaseModel):
    """创建多维表参数。"""

    name: str = Field(description="表格展示名称", min_length=1, max_length=200)
    table_id: str = Field(description="表格内部 ID", min_length=1, max_length=200)
    directory: str = Field(default="", description="创建目录，默认当前工作区根目录")
    scope: DataTableScope = Field(default="workspace", description="创建位置：workspace 或 global")
    columns: list[DataTableColumnParams] = Field(description="列定义", min_length=1)


class DataTablePathParams(BaseModel):
    """多维表路径参数。"""

    table_path: str = Field(description="多维表路径，支持相对路径、/workspace/... 或 /global/...")


class QueryDataTableParams(DataTablePathParams):
    """查询多维表参数。"""

    sql: str = Field(description="SQL 查询语句，必须以 SELECT 开头")
    max_rows: int = Field(default=500, description="最大返回行数", ge=1, le=2000)

    @field_validator("sql", mode="after")
    @classmethod
    def _validate_select_only(cls, value: str) -> str:
        stripped = value.strip()
        # 简单拦截：必须以 SELECT 开头（允许前导注释/空白）
        # 跳过前导注释行
        lines = [
            line
            for line in stripped.splitlines()
            if line.strip() and not line.strip().startswith("--")
        ]
        if not lines:
            raise ValueError("SQL 不能为空")
        first = lines[0].strip().upper()
        if not first.startswith("SELECT"):
            raise ValueError(
                "QueryDataTable 仅支持 SELECT 查询，禁止 INSERT/UPDATE/DELETE/ALTER/DROP 等写操作"
            )
        return stripped


class InsertDataTableRecordsParams(DataTablePathParams):
    """插入多维表记录参数。"""

    records: list[dict[str, Any]] = Field(description="待插入记录", min_length=1)


class UpdateDataTableRecordParams(DataTablePathParams):
    """更新多维表记录参数。"""

    record_id: str = Field(description="记录 _id", min_length=1)
    data: dict[str, Any] = Field(description="要更新的列数据", min_length=1)


class DeleteDataTableRecordParams(DataTablePathParams):
    """删除多维表记录参数。"""

    record_id: str = Field(description="记录 _id", min_length=1)


class AddDataTableColumnParams(DataTablePathParams, DataTableColumnParams):
    """新增多维表列参数。"""


class UpdateDataTableColumnParams(DataTablePathParams):
    """更新多维表列参数。"""

    column_name: str = Field(description="要更新的旧列名", min_length=1)
    column: DataTableColumnParams = Field(description="新的列定义")


class RemoveDataTableColumnParams(DataTablePathParams):
    """删除多维表列参数。"""

    column_name: str = Field(description="要删除的列名", min_length=1)


class CreateDataTable(AiasysTool):
    """创建多维数据表。"""

    name: str = "CreateDataTable"
    description: str = """
创建多维数据表。

多维表以 SQLite .table.db 文件存储，可放在当前工作区或全局工作区。
支持 CRUD 操作和列管理。查询操作使用 QueryDataTable 工具执行 SELECT 语句。

参数：
- name: 表格展示名称。
- table_id: 表格内部 ID。
- directory: 创建目录，默认根目录。
- scope: workspace 或 global。
- columns: 列定义列表，支持 text、number、date、single_select、multi_select、checkbox、file、url。
"""
    params: type[BaseModel] = CreateDataTableParams
    parameters: dict[str, Any] = CreateDataTableParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = CreateDataTableParams.model_validate(kwargs)
        try:
            root = _resolve_root(params.scope)
            result = create_data_table(
                root,
                DataTableCreateRequest(
                    name=params.name,
                    id=params.table_id,
                    directory=params.directory,
                    columns=[_column_from_params(column) for column in params.columns],
                ),
            )
            display_path = (
                f"/{'global' if params.scope == 'global' else 'workspace'}/{result.relative_path}"
            )
            return ToolResult(
                content="\n".join(
                    [
                        f"多维表创建成功：{result.name}",
                        f"位置: {_format_scope(params.scope)}",
                        f"路径: {display_path}",
                        f"ID: {result.id}",
                        f"列数: {len(params.columns)}",
                    ]
                ),
                artifacts=[
                    {
                        "data_table": {
                            **result.model_dump(),
                            "scope": params.scope,
                            "display_path": display_path,
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("创建多维表失败: %s", exc, exc_info=True)
            return ToolResult(content=f"创建多维表失败: {exc}", is_error=True)


class ReadDataTableSchema(AiasysTool):
    """读取多维表 schema。"""

    name: str = "ReadDataTableSchema"
    description: str = """
读取多维表的元数据和列定义。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
"""
    params: type[BaseModel] = DataTablePathParams
    parameters: dict[str, Any] = DataTablePathParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = DataTablePathParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            schema = read_data_table_schema(table_file)
            columns = schema.get("columns", [])
            lines = [
                f"多维表: {schema.get('metadata', {}).get('name') or relative_path}",
                f"位置: {_format_scope(scope)}",
                f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}",
                f"列数: {len(columns)}",
                "",
            ]
            for column in columns:
                option_text = ""
                if column.get("options"):
                    option_text = f"，选项: {', '.join(map(str, column['options']))}"
                required_text = "，必填" if column.get("required") else ""
                lines.append(
                    f"- {column.get('name')}: {column.get('type')}{required_text}{option_text}"
                )
            return ToolResult(
                content="\n".join(lines),
                artifacts=[{"data_table_schema": schema}],
            )
        except Exception as exc:
            logger.error("读取多维表 schema 失败: %s", exc, exc_info=True)
            return ToolResult(content=f"读取多维表 schema 失败: {exc}", is_error=True)


class QueryDataTable(AiasysTool):
    """查询多维表（只读 SELECT）。"""

    name: str = "QueryDataTable"
    description: str = """
对多维表执行只读 SQL 查询。

底层使用 SQLite 引擎，支持完整的 SELECT 语法：WHERE 过滤、ORDER BY 排序、GROUP BY 聚合、JOIN 关联、LIMIT 分页等。只能执行 SELECT 查询，写操作（INSERT/UPDATE/DELETE/ALTER/DROP）会被拒绝。

常用查询示例：
- 查看所有记录：SELECT * FROM records LIMIT 10
- 过滤 + 排序：SELECT * FROM records WHERE status = 'active' ORDER BY created_at DESC LIMIT 5
- 聚合统计：SELECT department, AVG(salary), COUNT(*) FROM records GROUP BY department
- 查看表结构：SELECT column_name, data_type FROM _schema ORDER BY order_index

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- sql: SQL 查询语句，必须以 SELECT 开头。
- max_rows: 最大返回行数，默认 500。
"""
    params: type[BaseModel] = QueryDataTableParams
    parameters: dict[str, Any] = QueryDataTableParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = QueryDataTableParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            conn = sqlite3.connect(str(table_file))
            conn.row_factory = sqlite3.Row
            try:
                # 安全：附加 LIMIT 防止超大结果
                sql = params.sql.strip()
                if "LIMIT" not in sql.upper():
                    sql = f"{sql} LIMIT {params.max_rows}"
                rows = conn.execute(sql).fetchall()
                records = [dict(row) for row in rows]
                columns = list(records[0].keys()) if records else []
                lines = [
                    f"多维表路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}",
                    f"SQL: {params.sql}",
                    f"返回行数: {len(records)}",
                ]
                if records:
                    lines.extend(["", " | ".join(columns), "-" * max(1, len(" | ".join(columns)))])
                    for record in records:
                        lines.append(" | ".join(str(record.get(column, "")) for column in columns))
                return ToolResult(
                    content="\n".join(lines),
                    artifacts=[
                        {
                            "data_table_query": {
                                "scope": scope,
                                "relative_path": relative_path,
                                "sql": params.sql,
                                "records": records,
                                "row_count": len(records),
                            }
                        }
                    ],
                )
            finally:
                conn.close()
        except Exception as exc:
            logger.error("查询多维表失败: %s", exc, exc_info=True)
            return ToolResult(content=f"查询多维表失败: {exc}", is_error=True)


class InsertDataTableRecords(AiasysTool):
    """向多维表插入记录。"""

    name: str = "InsertDataTableRecords"
    description: str = """
向多维表插入一条或多条记录。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- records: 记录列表。键名必须匹配多维表列名，系统字段会被忽略。
"""
    params: type[BaseModel] = InsertDataTableRecordsParams
    parameters: dict[str, Any] = InsertDataTableRecordsParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = InsertDataTableRecordsParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            inserted_ids = insert_data_table_records(table_file, params.records)
            return ToolResult(
                content="\n".join(
                    [
                        f"已插入记录：{len(inserted_ids)} 条",
                        f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}",
                        f"记录 ID: {', '.join(inserted_ids)}",
                    ]
                ),
                artifacts=[
                    {
                        "data_table_insert": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "inserted_ids": inserted_ids,
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("插入多维表记录失败: %s", exc, exc_info=True)
            return ToolResult(content=f"插入多维表记录失败: {exc}", is_error=True)


class UpdateDataTableRecord(AiasysTool):
    """更新多维表记录。"""

    name: str = "UpdateDataTableRecord"
    description: str = """
更新多维表中的一条记录。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- record_id: 记录 _id。
- data: 要更新的列数据。
"""
    params: type[BaseModel] = UpdateDataTableRecordParams
    parameters: dict[str, Any] = UpdateDataTableRecordParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = UpdateDataTableRecordParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            updated = update_data_table_record(table_file, params.record_id, params.data)
            return ToolResult(
                content=(
                    f"多维表记录{'已更新' if updated else '未更新'}：{params.record_id}\n"
                    f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}"
                ),
                is_error=not updated,
                artifacts=[
                    {
                        "data_table_record_update": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "record_id": params.record_id,
                            "updated": updated,
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("更新多维表记录失败: %s", exc, exc_info=True)
            return ToolResult(content=f"更新多维表记录失败: {exc}", is_error=True)


class DeleteDataTableRecord(AiasysTool):
    """删除多维表记录。"""

    name: str = "DeleteDataTableRecord"
    description: str = """
删除多维表中的一条记录。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- record_id: 记录 _id。
"""
    params: type[BaseModel] = DeleteDataTableRecordParams
    parameters: dict[str, Any] = DeleteDataTableRecordParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = DeleteDataTableRecordParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            deleted = delete_data_table_record(table_file, params.record_id)
            return ToolResult(
                content=(
                    f"多维表记录{'已删除' if deleted else '未删除'}：{params.record_id}\n"
                    f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}"
                ),
                is_error=not deleted,
                artifacts=[
                    {
                        "data_table_record_delete": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "record_id": params.record_id,
                            "deleted": deleted,
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("删除多维表记录失败: %s", exc, exc_info=True)
            return ToolResult(content=f"删除多维表记录失败: {exc}", is_error=True)


class AddDataTableColumn(AiasysTool):
    """新增多维表列。"""

    name: str = "AddDataTableColumn"
    description: str = """
向多维表新增一列。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- name/type/required/options/precision: 新列定义。
"""
    params: type[BaseModel] = AddDataTableColumnParams
    parameters: dict[str, Any] = AddDataTableColumnParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = AddDataTableColumnParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            add_data_table_column(table_file, _column_from_params(params))
            return ToolResult(
                content="\n".join(
                    [
                        f"多维表列已新增：{params.name}",
                        f"类型: {params.type}",
                        f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}",
                    ]
                ),
                artifacts=[
                    {
                        "data_table_column_add": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "column": _column_from_params(params).model_dump(),
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("新增多维表列失败: %s", exc, exc_info=True)
            return ToolResult(content=f"新增多维表列失败: {exc}", is_error=True)


class UpdateDataTableColumn(AiasysTool):
    """更新多维表列。"""

    name: str = "UpdateDataTableColumn"
    description: str = """
更新多维表列定义。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- column_name: 要更新的旧列名。
- column: 新列定义。
"""
    params: type[BaseModel] = UpdateDataTableColumnParams
    parameters: dict[str, Any] = UpdateDataTableColumnParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = UpdateDataTableColumnParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            column = _column_from_params(params.column)
            update_data_table_column(table_file, params.column_name, column)
            return ToolResult(
                content="\n".join(
                    [
                        f"多维表列已更新：{params.column_name} -> {column.name}",
                        f"类型: {column.type}",
                        f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}",
                    ]
                ),
                artifacts=[
                    {
                        "data_table_column_update": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "old_name": params.column_name,
                            "column": column.model_dump(),
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("更新多维表列失败: %s", exc, exc_info=True)
            return ToolResult(content=f"更新多维表列失败: {exc}", is_error=True)


class RemoveDataTableColumn(AiasysTool):
    """删除多维表列。"""

    name: str = "RemoveDataTableColumn"
    description: str = """
删除多维表列。

参数：
- table_path: 多维表路径，支持相对路径、/workspace/... 或 /global/...。
- column_name: 要删除的列名。
"""
    params: type[BaseModel] = RemoveDataTableColumnParams
    parameters: dict[str, Any] = RemoveDataTableColumnParams.model_json_schema()

    async def invoke(self, ctx: dict[str, Any] | None = None, **kwargs: Any) -> ToolResult:
        del ctx
        params = RemoveDataTableColumnParams.model_validate(kwargs)
        try:
            _, table_file, scope, relative_path = _resolve_table_path(params.table_path)
            remove_data_table_column(table_file, params.column_name)
            return ToolResult(
                content="\n".join(
                    [
                        f"多维表列已删除：{params.column_name}",
                        f"路径: /{'global' if scope == 'global' else 'workspace'}/{relative_path}",
                    ]
                ),
                artifacts=[
                    {
                        "data_table_column_remove": {
                            "scope": scope,
                            "relative_path": relative_path,
                            "column_name": params.column_name,
                        }
                    }
                ],
            )
        except Exception as exc:
            logger.error("删除多维表列失败: %s", exc, exc_info=True)
            return ToolResult(content=f"删除多维表列失败: {exc}", is_error=True)
