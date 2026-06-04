"""
运行时数据库访问 broker 相关模型
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from app.models.database_connector import DatabaseType

RuntimeDatabaseType = DatabaseType
DatabaseHandle = str
DatabaseAction = Literal["query", "execute", "list_tables", "describe_table"]
RuntimeDatabaseErrorCategory = Literal[
    "auth",
    "request",
    "session",
    "attachment",
    "platform",
    "approval",
    "remote",
    "remote_permission",
    "remote_execution",
    "runtime",
]


class RuntimeDatabaseErrorDetail(BaseModel):
    """运行时数据库错误详情。"""

    code: str = Field(..., description="前端/调用方可识别的稳定错误码")
    category: RuntimeDatabaseErrorCategory = Field(..., description="错误大类")
    message: str = Field(..., description="面向用户的错误信息")
    retryable: bool = Field(default=False, description="是否建议调用方重试")


class RuntimeDatabaseQueryRequest(BaseModel):
    """运行时数据库查询请求"""

    handle: DatabaseHandle = Field(default="", description="数据库资源句柄")
    sql: str = Field(..., min_length=1, description="查询 SQL")
    params: list[Any] | dict[str, Any] | None = Field(
        default=None,
        description="SQL 参数",
    )
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000,
        description="结果行数上限",
    )


class RuntimeDatabaseExecuteRequest(BaseModel):
    """运行时数据库执行请求"""

    handle: DatabaseHandle = Field(default="", description="数据库资源句柄")
    sql: str = Field(..., min_length=1, description="写入/DDL SQL")
    params: list[Any] | dict[str, Any] | None = Field(
        default=None,
        description="SQL 参数",
    )


class RuntimeDatabaseHandleInfo(BaseModel):
    """运行时可访问数据库句柄信息"""

    handle: DatabaseHandle
    connector_id: str = Field(..., description="连接器 ID")
    name: str = Field(..., description="连接器名称")
    db_type: RuntimeDatabaseType = Field(..., description="数据库类型")
    description: str | None = Field(default=None, description="连接器描述")
    allow_notebook_access: bool = Field(default=False, description="是否允许 Notebook 直接连接")
    attached_at: str = Field(..., description="挂载时间")


class RuntimeDatabaseHandlesResponse(BaseModel):
    """运行时可访问数据库句柄列表响应"""

    session_id: str
    handles: list[RuntimeDatabaseHandleInfo] = Field(default_factory=list)


class RuntimeDatabaseListTablesResponse(BaseModel):
    """运行时表列表响应"""

    handle: DatabaseHandle
    audit_id: str | None = None
    duration_ms: int | None = None
    tables: list[str] = Field(default_factory=list)


class RuntimeDatabaseColumnInfo(BaseModel):
    """运行时列结构"""

    name: str
    type: str
    nullable: bool
    default: str | None = None


class RuntimeDatabaseDescribeTableResponse(BaseModel):
    """运行时表结构响应"""

    handle: DatabaseHandle
    audit_id: str | None = None
    duration_ms: int | None = None
    table: str
    columns: list[RuntimeDatabaseColumnInfo] = Field(default_factory=list)


class RuntimeDatabaseQueryResponse(BaseModel):
    """运行时查询响应"""

    handle: DatabaseHandle
    audit_id: str | None = None
    duration_ms: int | None = None
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    applied_limit: int | None = None


class RuntimeDatabaseExecuteResponse(BaseModel):
    """运行时执行响应"""

    handle: DatabaseHandle
    audit_id: str | None = None
    duration_ms: int | None = None
    affected_rows: int = 0
    message: str | None = None
