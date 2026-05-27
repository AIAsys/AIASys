from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy.engine import make_url

from app.models.database_connector import DEFAULT_CONNECTOR_PORTS

from .base import (
    ConnectorAdapter,
    PreparedReadonlyQuery,
    QueryResult,
    ReadonlySqlParams,
    SqlParams,
)


class RelationalSqlConnectorAdapter(ConnectorAdapter, ABC):
    """关系型 SQL connector 的共用 adapter。"""

    def list_tables(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> QueryResult:
        sql, params, limit = self.build_list_tables_query()
        return self.query(
            connection_mode=connection_mode,
            payload=payload,
            sql=sql,
            params=params,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

    def build_list_tables_query(self) -> PreparedReadonlyQuery:
        return self._build_list_tables_sql(), [], 10000

    def build_describe_table_query(
        self,
        *,
        schema_name: str,
        table_name: str,
    ) -> PreparedReadonlyQuery:
        sql = (
            "SELECT column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position"
        )
        return sql, [schema_name, table_name], 2000

    def describe_table(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        schema_name: str,
        table_name: str,
        timeout_seconds: int,
    ) -> QueryResult:
        sql, params, limit = self.build_describe_table_query(
            schema_name=schema_name,
            table_name=table_name,
        )
        return self.query(
            connection_mode=connection_mode,
            payload=payload,
            sql=sql,
            params=params,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

    @abstractmethod
    def _build_list_tables_sql(self) -> str:
        """构建列出表的 SQL。"""


class PostgresConnectorAdapter(RelationalSqlConnectorAdapter):
    db_type = "postgres"

    def is_driver_available(self) -> bool:
        return True

    def test_connection(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> None:
        timeout = int(payload.get("query_timeout_seconds") or 15)
        conn = self._connect(
            connection_mode=connection_mode,
            payload=payload,
            timeout_seconds=timeout,
            apply_statement_timeout=False,
        )
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
            cur.close()
        finally:
            conn.close()

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
        conn = self._connect(
            connection_mode=connection_mode,
            payload=payload,
            timeout_seconds=timeout_seconds,
            apply_statement_timeout=True,
        )
        try:
            cur = conn.cursor()
            cur.execute(sql, tuple(params))
            columns = [item[0] for item in (cur.description or [])]
            rows = cur.fetchmany(limit + 1)
            cur.close()
            return columns, rows
        finally:
            conn.close()

    def execute(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: SqlParams,
        timeout_seconds: int,
    ) -> int:
        conn = self._connect(
            connection_mode=connection_mode,
            payload=payload,
            timeout_seconds=timeout_seconds,
            apply_statement_timeout=True,
        )
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            affected_rows = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
            cur.close()
            return affected_rows
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _build_list_tables_sql(self) -> str:
        return (
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema NOT IN ('pg_catalog', 'information_schema') "
            "ORDER BY table_schema, table_name"
        )

    def _connect(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        apply_statement_timeout: bool,
    ):
        import psycopg2

        connect_kwargs: dict[str, Any] = {
            "connect_timeout": timeout_seconds,
        }
        if apply_statement_timeout:
            connect_kwargs["options"] = f"-c statement_timeout={timeout_seconds * 1000}"

        if connection_mode == "url":
            return psycopg2.connect(payload["connection_url"], **connect_kwargs)

        return psycopg2.connect(
            host=payload["host"],
            port=payload["port"],
            user=payload["username"],
            password=payload.get("password"),
            database=payload["database_name"],
            **connect_kwargs,
        )


class MySqlConnectorAdapter(RelationalSqlConnectorAdapter):
    db_type = "mysql"

    def is_driver_available(self) -> bool:
        try:
            import pymysql  # noqa: F401
        except ModuleNotFoundError:
            return False
        return True

    def test_connection(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> None:
        timeout = int(payload.get("query_timeout_seconds") or 15)
        conn = self._connect(
            connection_mode=connection_mode,
            payload=payload,
            timeout_seconds=timeout,
            missing_driver_message="当前环境缺少 PyMySQL，暂时无法测试 MySQL 连接",
        )
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        finally:
            conn.close()

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
        conn = self._connect(
            connection_mode=connection_mode,
            payload=payload,
            timeout_seconds=timeout_seconds,
            missing_driver_message="当前环境缺少 PyMySQL，暂时无法执行 MySQL 只读查询",
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, tuple(params))
                columns = [item[0] for item in (cur.description or [])]
                rows = cur.fetchmany(limit + 1)
            return columns, rows
        finally:
            conn.close()

    def execute(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: SqlParams,
        timeout_seconds: int,
    ) -> int:
        conn = self._connect(
            connection_mode=connection_mode,
            payload=payload,
            timeout_seconds=timeout_seconds,
            missing_driver_message="当前环境缺少 PyMySQL，暂时无法执行 MySQL 写入",
        )
        try:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                affected_rows = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
            return affected_rows
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _build_list_tables_sql(self) -> str:
        return (
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_type = 'BASE TABLE' "
            "AND table_schema = DATABASE() "
            "ORDER BY table_schema, table_name"
        )

    def _build_connect_kwargs(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if connection_mode == "url":
            url = make_url(payload["connection_url"])
            return {
                "host": url.host,
                "port": int(url.port or DEFAULT_CONNECTOR_PORTS["mysql"]),
                "user": url.username,
                "password": url.password,
                "database": url.database,
            }

        return {
            "host": payload["host"],
            "port": int(payload["port"] or DEFAULT_CONNECTOR_PORTS["mysql"]),
            "user": payload["username"],
            "password": payload.get("password"),
            "database": payload["database_name"],
        }

    def _connect(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        timeout_seconds: int,
        missing_driver_message: str,
    ):
        pymysql = self._require_driver(missing_driver_message)
        connect_kwargs = self._build_connect_kwargs(
            connection_mode=connection_mode,
            payload=payload,
        )
        return pymysql.connect(
            **connect_kwargs,
            connect_timeout=timeout_seconds,
            read_timeout=timeout_seconds,
            write_timeout=timeout_seconds,
            charset="utf8mb4",
        )

    def _require_driver(self, missing_driver_message: str):
        try:
            import pymysql
        except ModuleNotFoundError as exc:
            raise RuntimeError(missing_driver_message) from exc
        return pymysql
