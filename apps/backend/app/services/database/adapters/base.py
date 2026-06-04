from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.models.database_connector import DatabaseType

ReadonlySqlParams = list[object]
SqlParams = list[object] | dict[str, Any] | None
QueryResult = tuple[list[str], list[tuple[Any, ...]]]
PreparedReadonlyQuery = tuple[str, ReadonlySqlParams, int]


class ConnectorAdapter(ABC):
    """数据库连接器 adapter 抽象。"""

    db_type: DatabaseType

    @abstractmethod
    def is_driver_available(self) -> bool:
        """返回当前环境中驱动是否可用。"""

    @abstractmethod
    def test_connection(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> None:
        """执行连接测试。"""

    @abstractmethod
    def query(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: ReadonlySqlParams,
        limit: int,
        timeout_seconds: int,
    ) -> QueryResult:
        """执行只读查询。"""

    @abstractmethod
    def execute(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: SqlParams,
        timeout_seconds: int,
    ) -> int:
        """执行写入或 DDL。"""

    @abstractmethod
    def list_tables(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> QueryResult:
        """列出当前连接器可见表。"""

    @abstractmethod
    def describe_table(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        schema_name: str,
        table_name: str,
        timeout_seconds: int,
    ) -> QueryResult:
        """读取单表字段结构。"""

    @abstractmethod
    def build_list_tables_query(self) -> PreparedReadonlyQuery:
        """构建 list tables 所需的查询语句。"""

    @abstractmethod
    def build_describe_table_query(
        self,
        *,
        schema_name: str,
        table_name: str,
    ) -> PreparedReadonlyQuery:
        """构建 describe table 所需的查询语句。"""
