"""
数据库查询工具集

允许 Agent 查询外部数据库连接器、探索库结构。
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.database import DatabaseAccessBroker
from app.services.history import current_session_id, current_user_id

logger = logging.getLogger(__name__)

DEFAULT_TOOL_ROW_LIMIT = 50
MAX_TOOL_ROW_LIMIT = 1000
MAX_TOOL_COLUMN_COUNT = 50


def _resolve_current_user_id() -> str:
    user_id = current_user_id.get()
    if user_id:
        return user_id
    return "anonymous"


def _resolve_current_session_id() -> str | None:
    return current_session_id.get()


# ==================== DatabaseQuery ====================


class DatabaseQueryParams(BaseModel):
    """数据库查询参数"""

    handle: str = Field(
        ...,
        description='数据库句柄，格式为 "connector:{连接器ID}"',
    )
    sql: str = Field(
        ...,
        description="要执行的 SQL 语句",
    )
    params: list[Any] | None = Field(
        default=None,
        description="SQL 位置参数列表（可选），当前仅支持 list 格式",
    )
    limit: Optional[int] = Field(
        default=None,
        description=f"返回行数上限，默认 {DEFAULT_TOOL_ROW_LIMIT}，最大 {MAX_TOOL_ROW_LIMIT}",
        ge=1,
        le=MAX_TOOL_ROW_LIMIT,
    )


class DatabaseQuery(AiasysTool):
    """
    数据库查询工具 - 对挂载的外部数据库执行 SQL。

    使用场景：
    - 用户要求查询某个外部数据库的数据
    - Agent 需要验证数据分析假设
    - 获取表结构信息外的实际数据

    注意：
    - 必须先通过 ListDatabaseConnectors 获取可用的 handle
    - 默认只返回前 50 行，如需更多可显式指定 limit
    - 如果 connector 配置了 allow_notebook_access，也可在 Notebook 中用 Python 直接连接
    """

    name: str = "DatabaseQuery"
    description: str = """
对挂载的外部数据库执行 SQL 查询或写入操作。

参数说明：
- handle: 数据库句柄，格式为 "connector:{连接器ID}"
- sql: 要执行的 SQL 语句
- params: SQL 参数（可选）
- limit: 返回行数上限，默认 50 行，最大 1000

返回结果包含：
- 列名列表
- 数据行（默认最多 50 行）
- 实际返回行数
- 是否被截断

如果不知道有哪些连接器可用，先调用 ListDatabaseConnectors。
"""
    params: type[BaseModel] = DatabaseQueryParams
    parameters: dict[str, Any] = DatabaseQueryParams.model_json_schema()

    def __init__(self):
        self._broker = DatabaseAccessBroker()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = DatabaseQueryParams.model_validate(kwargs)
        user_id = _resolve_current_user_id()
        session_id = _resolve_current_session_id()
        if not session_id:
            return ToolResult(
                content="无法获取当前会话 ID，请确保在有效会话中调用。",
                is_error=True,
            )

        try:
            effective_limit = params.limit or DEFAULT_TOOL_ROW_LIMIT
            effective_limit = min(effective_limit, MAX_TOOL_ROW_LIMIT)

            result = self._broker.query(
                user_id=user_id,
                session_id=session_id,
                handle=params.handle,
                sql=params.sql,
                params=params.params,
                limit=effective_limit,
            )

            lines: list[str] = [
                f"句柄: {result.handle}",
                f"返回行数: {result.row_count}{' (已截断)' if result.truncated else ''}",
                "",
            ]
            # 表头
            header = " | ".join(result.columns)
            lines.append(header)
            lines.append("-" * len(header))
            # 数据行
            for row in result.rows:
                cells = [str(cell) if cell is not None else "NULL" for cell in row]
                lines.append(" | ".join(cells))

            if result.truncated:
                lines.append("")
                lines.append(
                    f"提示: 结果超过 {effective_limit} 行，已截断。如需查看更多数据，可增大 limit 参数重新查询。"
                )

            return ToolResult(content="\n".join(lines))

        except Exception as e:
            logger.error("数据库查询失败: %s", e, exc_info=True)
            return ToolResult(content=f"数据库查询失败: {str(e)}", is_error=True)


# ==================== ListDatabaseConnectors ====================


class ListDatabaseConnectorsParams(BaseModel):
    """列出数据库连接器参数（无参数）"""

    pass


class ListDatabaseConnectors(AiasysTool):
    """
    列出当前会话可用的外部数据库连接器。

    使用场景：
    - 用户提到"查一下数据库"但没有指定具体库
    - Agent 需要确认有哪些外部数据库可用
    - 获取 connector handle 用于后续 DatabaseQuery 调用
    """

    name: str = "ListDatabaseConnectors"
    description: str = """
列出当前用户可用的外部数据库连接器。

返回每个连接器的：
- handle: 运行时句柄（如 "connector:my_pg"）
- name: 连接器名称
- description: 用途描述
- db_type: 数据库类型（postgres/mysql/influxdb3）
- allow_notebook_access: 是否允许 Notebook 直接连接

调用 DatabaseQuery 前，先用此工具确认有哪些句柄可用。
"""
    params: type[BaseModel] = ListDatabaseConnectorsParams
    parameters: dict[str, Any] = ListDatabaseConnectorsParams.model_json_schema()

    def __init__(self):
        self._broker = DatabaseAccessBroker()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx, kwargs
        user_id = _resolve_current_user_id()
        session_id = _resolve_current_session_id()
        if not session_id:
            return ToolResult(
                content="无法获取当前会话 ID。",
                is_error=True,
            )

        try:
            result = self._broker.list_handles(
                user_id=user_id,
                session_id=session_id,
            )

            if not result.handles:
                return ToolResult(content="当前没有可用的数据库连接器。")

            lines: list[str] = [f"共 {len(result.handles)} 个可用连接器：", ""]
            for i, h in enumerate(result.handles, 1):
                desc = h.description or "无描述"
                notebook_tag = " [Notebook可直连]" if h.allow_notebook_access else ""
                lines.append(
                    f"[{i}] {h.name}{notebook_tag}\n"
                    f"    handle: {h.handle}\n"
                    f"    类型: {h.db_type}\n"
                    f"    描述: {desc}"
                )

            return ToolResult(content="\n\n".join(lines))

        except Exception as e:
            logger.error("列出连接器失败: %s", e, exc_info=True)
            return ToolResult(content=f"列出连接器失败: {str(e)}", is_error=True)


# ==================== ListDatabaseTables ====================


class ListDatabaseTablesParams(BaseModel):
    """列出数据库表参数"""

    handle: str = Field(
        ...,
        description='数据库句柄，格式为 "connector:{连接器ID}"',
    )


class ListDatabaseTables(AiasysTool):
    """
    列出指定连接器中的表。

    使用场景：
    - 写 SQL 前需要知道有哪些表可用
    - 探索陌生数据库的结构
    """

    name: str = "ListDatabaseTables"
    description: str = """
列出指定数据库连接器中的所有表。

参数：
- handle: 数据库句柄，格式为 "connector:{连接器ID}"

返回表名列表（最多 50 个），截断时会提示。
"""
    params: type[BaseModel] = ListDatabaseTablesParams
    parameters: dict[str, Any] = ListDatabaseTablesParams.model_json_schema()

    def __init__(self):
        self._broker = DatabaseAccessBroker()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = ListDatabaseTablesParams.model_validate(kwargs)
        user_id = _resolve_current_user_id()
        session_id = _resolve_current_session_id()
        if not session_id:
            return ToolResult(content="无法获取当前会话 ID。", is_error=True)

        try:
            result = self._broker.list_tables(
                user_id=user_id,
                session_id=session_id,
                handle=params.handle,
            )

            tables = result.tables[:50]
            truncated = len(result.tables) > 50

            if not tables:
                return ToolResult(content="该数据库中没有发现表。")

            lines = [f"共发现 {len(result.tables)} 个表：", ""]
            for i, t in enumerate(tables, 1):
                lines.append(f"{i}. {t}")

            if truncated:
                lines.append("")
                lines.append("提示: 仅展示前 50 个表。")

            return ToolResult(content="\n".join(lines))

        except Exception as e:
            logger.error("列出表失败: %s", e, exc_info=True)
            return ToolResult(content=f"列出表失败: {str(e)}", is_error=True)


# ==================== DescribeDatabaseTable ====================


class DescribeDatabaseTableParams(BaseModel):
    """查看表结构参数"""

    handle: str = Field(
        ...,
        description='数据库句柄，格式为 "connector:{连接器ID}"',
    )
    table_name: str = Field(
        ...,
        description="目标表名，可为 schema.table 格式",
    )


class DescribeDatabaseTable(AiasysTool):
    """
    查看指定表的结构（字段名、类型、可空性、默认值）。

    使用场景：
    - 写 SQL 前确认字段名和类型
    - 了解表结构以决定查询策略
    """

    name: str = "DescribeDatabaseTable"
    description: str = """
查看指定数据库表的结构信息。

参数：
- handle: 数据库句柄，格式为 "connector:{连接器ID}"
- table_name: 目标表名，可为 schema.table 格式

返回每个字段的：
- name: 字段名
- type: 字段类型
- nullable: 是否可空
- default: 默认值（如有）

最多返回 50 个字段。
"""
    params: type[BaseModel] = DescribeDatabaseTableParams
    parameters: dict[str, Any] = DescribeDatabaseTableParams.model_json_schema()

    def __init__(self):
        self._broker = DatabaseAccessBroker()

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        del ctx
        params = DescribeDatabaseTableParams.model_validate(kwargs)
        user_id = _resolve_current_user_id()
        session_id = _resolve_current_session_id()
        if not session_id:
            return ToolResult(content="无法获取当前会话 ID。", is_error=True)

        try:
            result = self._broker.describe_table(
                user_id=user_id,
                session_id=session_id,
                handle=params.handle,
                table_name=params.table_name,
            )

            columns = result.columns[:MAX_TOOL_COLUMN_COUNT]
            truncated = len(result.columns) > MAX_TOOL_COLUMN_COUNT

            if not columns:
                return ToolResult(content=f"表 {result.table} 中没有发现字段。")

            lines = [f"表: {result.table}", f"字段数: {len(result.columns)}", ""]
            lines.append("| 字段名 | 类型 | 可空 | 默认值 |")
            lines.append("| --- | --- | --- | --- |")
            for col in columns:
                nullable_str = "是" if col.nullable else "否"
                default_str = col.default or "-"
                lines.append(f"| {col.name} | {col.type} | {nullable_str} | {default_str} |")

            if truncated:
                lines.append("")
                lines.append(f"提示: 仅展示前 {MAX_TOOL_COLUMN_COUNT} 个字段。")

            return ToolResult(content="\n".join(lines))

        except Exception as e:
            logger.error("查看表结构失败: %s", e, exc_info=True)
            return ToolResult(content=f"查看表结构失败: {str(e)}", is_error=True)
