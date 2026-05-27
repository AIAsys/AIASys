"""
数据库连接器相关数据模型
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

DatabaseType = Literal["postgres", "mysql", "influxdb3"]
ConnectorFamily = Literal["relational", "timeseries"]
ConnectionMode = Literal["fields", "url"]
ConnectorTestStatus = Literal["untested", "passed", "failed"]
_DATABASE_FAMILY_BY_TYPE: dict[DatabaseType, ConnectorFamily] = {
    "postgres": "relational",
    "mysql": "relational",
    "influxdb3": "timeseries",
}

DEFAULT_CONNECTOR_PORTS: dict[DatabaseType, int] = {
    "postgres": 5432,
    "mysql": 3306,
    "influxdb3": 8181,
}


def _utcnow_iso() -> str:
    """返回 UTC ISO 时间字符串。"""
    return datetime.now(timezone.utc).isoformat()


def get_connector_family(db_type: DatabaseType) -> ConnectorFamily:
    """根据数据库引擎返回连接器家族。"""
    return _DATABASE_FAMILY_BY_TYPE[db_type]


class DatabaseConnectorDraft(BaseModel):
    """数据库连接器草稿/创建请求"""

    name: str = Field(..., min_length=1, max_length=128, description="连接器名称")
    db_type: DatabaseType = Field(..., description="数据库类型")
    connection_mode: ConnectionMode = Field(
        default="fields",
        description="连接录入模式",
    )
    host: Optional[str] = Field(default=None, max_length=255, description="数据库主机")
    port: Optional[int] = Field(default=None, ge=1, le=65535, description="数据库端口")
    database_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="数据库名",
    )
    username: Optional[str] = Field(
        default=None,
        max_length=255,
        description="目标数据库已有账号",
    )
    password: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="目标数据库账号密码",
    )
    api_token: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="Token 型认证凭证（如 InfluxDB 3 API token）",
    )
    connection_url: Optional[str] = Field(
        default=None,
        max_length=4096,
        description="高级模式连接 URL（包含目标数据库已有账号）",
    )
    description: Optional[str] = Field(
        default=None,
        max_length=1024,
        description="连接器用途描述（纯文本）",
    )
    allow_notebook_access: bool = Field(
        default=False,
        description="是否允许 Notebook 直接获取密码连接",
    )
    allowed_schemas: list[str] = Field(
        default_factory=list,
        description="允许访问的 schema 白名单",
    )
    allowed_tables: list[str] = Field(
        default_factory=list,
        description="允许访问的表白名单",
    )
    query_timeout_seconds: int = Field(
        default=15,
        ge=1,
        le=60,
        description="默认查询超时时间",
    )
    row_limit: int = Field(
        default=1000,
        ge=1,
        le=10000,
        description="默认返回行数上限",
    )

    @model_validator(mode="after")
    def validate_payload(self) -> "DatabaseConnectorDraft":
        """校验不同录入模式下的必填字段。"""
        if self.connection_mode == "url":
            if not self.connection_url:
                raise ValueError("URL 模式必须提供 connection_url")
            if self.db_type == "influxdb3" and not self.api_token:
                raise ValueError("InfluxDB 3 URL 模式必须提供 api_token")
        else:
            missing_fields: list[str] = []
            if not self.host:
                missing_fields.append("host")
            if not self.database_name:
                missing_fields.append("database_name")
            if self.db_type == "influxdb3":
                if not self.api_token:
                    missing_fields.append("api_token")
            else:
                if not self.username:
                    missing_fields.append("username")
            if missing_fields:
                raise ValueError(f"字段模式缺少必填项: {', '.join(missing_fields)}")

        if self.port is None:
            self.port = DEFAULT_CONNECTOR_PORTS[self.db_type]
        return self


class UpdateDatabaseConnectorRequest(BaseModel):
    """数据库连接器更新请求"""

    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    connection_mode: Optional[ConnectionMode] = Field(default=None)
    host: Optional[str] = Field(default=None, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    database_name: Optional[str] = Field(default=None, max_length=255)
    username: Optional[str] = Field(default=None, max_length=255)
    password: Optional[str] = Field(default=None, max_length=4096)
    api_token: Optional[str] = Field(default=None, max_length=4096)
    connection_url: Optional[str] = Field(default=None, max_length=4096)
    description: Optional[str] = Field(default=None, max_length=1024)
    allow_notebook_access: Optional[bool] = Field(default=None)
    allowed_schemas: Optional[list[str]] = Field(default=None)
    allowed_tables: Optional[list[str]] = Field(default=None)
    query_timeout_seconds: Optional[int] = Field(default=None, ge=1, le=60)
    row_limit: Optional[int] = Field(default=None, ge=1, le=10000)


class DatabaseConnectorCapability(BaseModel):
    """平台支持的数据库类型能力"""

    db_type: DatabaseType = Field(..., description="数据库类型")
    connector_family: ConnectorFamily = Field(..., description="连接器家族")
    label: str = Field(..., description="展示名称")
    connection_modes: list[ConnectionMode] = Field(
        default_factory=lambda: ["fields", "url"],
        description="支持的录入模式",
    )
    readonly_enforced: bool = Field(
        default=True, description="该数据库类型是否只支持只读（由数据库特性决定，非应用层控制）"
    )
    driver_available: bool = Field(default=True, description="当前环境驱动是否可用")
    driver_name: Optional[str] = Field(default=None, description="底层驱动名称")
    note: Optional[str] = Field(default=None, description="补充说明")


class DatabaseConnector(BaseModel):
    """数据库连接器对外响应模型"""

    connector_id: str = Field(..., description="连接器 ID")
    name: str = Field(..., description="连接器名称")
    db_type: DatabaseType = Field(..., description="数据库类型")
    connector_family: ConnectorFamily = Field(..., description="连接器家族")
    connection_mode: ConnectionMode = Field(..., description="连接录入模式")
    host: Optional[str] = Field(default=None, description="数据库主机")
    port: Optional[int] = Field(default=None, description="数据库端口")
    database_name: Optional[str] = Field(default=None, description="数据库名")
    username: Optional[str] = Field(default=None, description="目标数据库已有账号")
    description: Optional[str] = Field(default=None, description="连接器用途描述")
    allow_notebook_access: bool = Field(
        default=False, description="是否允许 Notebook 直接获取密码连接"
    )
    allowed_schemas: list[str] = Field(default_factory=list, description="schema 白名单")
    allowed_tables: list[str] = Field(default_factory=list, description="表白名单")
    query_timeout_seconds: int = Field(default=15, description="默认超时秒数")
    row_limit: int = Field(default=1000, description="默认行数限制")
    has_password: bool = Field(default=False, description="是否已配置密码")
    has_api_token: bool = Field(default=False, description="是否已配置 API token")
    has_connection_url: bool = Field(default=False, description="是否已配置 URL")
    password_masked: Optional[str] = Field(default=None, description="脱敏密码提示")
    api_token_masked: Optional[str] = Field(default=None, description="脱敏 token 提示")
    connection_url_masked: Optional[str] = Field(default=None, description="脱敏 URL")
    last_test_status: ConnectorTestStatus = Field(
        default="untested",
        description="最近一次测试状态",
    )
    last_test_message: Optional[str] = Field(default=None, description="最近一次测试信息")
    last_tested_at: Optional[str] = Field(default=None, description="最近测试时间")
    created_at: str = Field(
        default_factory=_utcnow_iso,
        description="创建时间",
    )
    updated_at: str = Field(
        default_factory=_utcnow_iso,
        description="更新时间",
    )


class DatabaseConnectorTestResult(BaseModel):
    """数据库连接器测试结果"""

    success: bool = Field(..., description="是否成功")
    db_type: DatabaseType = Field(..., description="数据库类型")
    message: str = Field(..., description="结果说明")
    latency_ms: Optional[int] = Field(default=None, description="连通性耗时")


class SessionDatabaseAttachmentRequest(BaseModel):
    """会话挂载请求"""

    connector_id: str = Field(..., min_length=1, description="待挂载的连接器 ID")
    sync_defaults: bool = Field(
        default=False,
        description="是否按当前连接器默认策略重建挂载权限",
    )


class SessionDatabaseAttachment(BaseModel):
    """会话数据库挂载信息"""

    session_id: str = Field(..., description="会话 ID")
    connector_id: str = Field(..., description="连接器 ID")
    handle: str = Field(..., description="运行时数据库句柄")
    name: str = Field(..., description="连接器名称")
    db_type: DatabaseType = Field(..., description="数据库类型")
    attached_at: str = Field(..., description="挂载时间")


class ReadonlyDatabaseQueryRequest(BaseModel):
    """会话级只读查询请求"""

    connector_id: str = Field(..., min_length=1, description="已挂载的连接器 ID")
    sql: str = Field(..., min_length=1, description="只读 SQL 查询语句")
    params: list[object] = Field(default_factory=list, description="位置参数")
    limit: Optional[int] = Field(
        default=None,
        ge=1,
        le=10000,
        description="本次查询行数上限，默认走连接器 row_limit",
    )


class ReadonlyDatabaseQueryResponse(BaseModel):
    """会话级只读查询响应"""

    session_id: str = Field(..., description="会话 ID")
    connector_id: str = Field(..., description="连接器 ID")
    handle: str = Field(..., description="运行时数据库句柄")
    db_type: DatabaseType = Field(..., description="数据库类型")
    audit_id: str = Field(..., description="审计 ID")
    duration_ms: int = Field(default=0, description="本次操作耗时")
    columns: list[str] = Field(default_factory=list, description="结果列名")
    rows: list[list[object]] = Field(default_factory=list, description="结果行")
    row_count: int = Field(default=0, description="返回行数")
    truncated: bool = Field(default=False, description="结果是否被行数上限截断")
    applied_limit: int = Field(default=0, description="实际应用的行数上限")


class DatabaseTableInfo(BaseModel):
    """数据库表信息"""

    schema_name: str = Field(..., serialization_alias="schema", description="schema 名称")
    table: str = Field(..., description="表名")
    full_name: str = Field(..., description="完整表名（schema.table）")


class DatabaseTableColumnInfo(BaseModel):
    """数据库字段信息"""

    name: str = Field(..., description="字段名")
    data_type: str = Field(..., description="字段类型")
    nullable: bool = Field(..., description="是否可空")
    default: Optional[str] = Field(default=None, description="默认值")


class DatabaseListTablesRequest(BaseModel):
    """会话级列出表请求"""

    connector_id: str = Field(..., min_length=1, description="已挂载的连接器 ID")


class DatabaseListTablesResponse(BaseModel):
    """会话级列出表响应"""

    session_id: str = Field(..., description="会话 ID")
    connector_id: str = Field(..., description="连接器 ID")
    handle: str = Field(..., description="运行时数据库句柄")
    db_type: DatabaseType = Field(..., description="数据库类型")
    audit_id: str = Field(..., description="审计 ID")
    duration_ms: int = Field(default=0, description="本次操作耗时")
    tables: list[DatabaseTableInfo] = Field(default_factory=list, description="表列表")


class DatabaseDescribeTableRequest(BaseModel):
    """会话级表结构请求"""

    connector_id: str = Field(..., min_length=1, description="已挂载的连接器 ID")
    table_name: str = Field(..., min_length=1, description="目标表名，可为 schema.table")


class DatabaseDescribeTableResponse(BaseModel):
    """会话级表结构响应"""

    session_id: str = Field(..., description="会话 ID")
    connector_id: str = Field(..., description="连接器 ID")
    handle: str = Field(..., description="运行时数据库句柄")
    db_type: DatabaseType = Field(..., description="数据库类型")
    audit_id: str = Field(..., description="审计 ID")
    duration_ms: int = Field(default=0, description="本次操作耗时")
    schema_name: str = Field(..., serialization_alias="schema", description="schema 名称")
    table: str = Field(..., description="表名")
    columns: list[DatabaseTableColumnInfo] = Field(default_factory=list, description="字段列表")
