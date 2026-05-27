"""
适配器管理 Mixin

负责数据库适配器的管理和数据库操作处理
"""

import time
from typing import TYPE_CHECKING, Any

from app.models.database_connector import DatabaseConnectorTestResult
from app.services.connector.errors import DatabaseConnectorPlatformRejectionError
from app.services.database.adapters import (
    ConnectorAdapter,
    InfluxDb3ConnectorAdapter,
    MySqlConnectorAdapter,
    PostgresConnectorAdapter,
)

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService


class AdapterMixin:
    """适配器管理功能"""

    def _build_connector_adapters(self: "DatabaseConnectorService") -> dict[str, ConnectorAdapter]:
        return {
            "postgres": PostgresConnectorAdapter(),
            "mysql": MySqlConnectorAdapter(),
            "influxdb3": InfluxDb3ConnectorAdapter(),
        }

    def _get_connector_adapter(self: "DatabaseConnectorService", db_type: str) -> ConnectorAdapter:
        adapter = self._connector_adapters.get(str(db_type))
        if adapter is None:
            raise ValueError(f"暂不支持的数据库类型: {db_type}")
        return adapter

    def _get_connection_test_handler(self: "DatabaseConnectorService", db_type: str):
        handlers = {
            "postgres": self._test_postgres_connection,
            "mysql": self._test_mysql_connection,
            "influxdb3": self._test_influxdb3_connection,
        }
        handler = handlers.get(str(db_type))
        if handler is None:
            raise ValueError(f"暂不支持的数据库类型: {db_type}")
        return handler

    def _get_query_handler(self: "DatabaseConnectorService", db_type: str):
        handlers = {
            "postgres": self._query_postgres,
            "mysql": self._query_mysql,
            "influxdb3": self._query_influxdb3,
        }
        handler = handlers.get(str(db_type))
        if handler is None:
            raise ValueError(f"暂不支持的数据库类型: {db_type}")
        return handler

    def _get_execute_handler(self: "DatabaseConnectorService", db_type: str):
        handlers = {
            "postgres": self._execute_postgres,
            "mysql": self._execute_mysql,
            "influxdb3": self._execute_influxdb3,
        }
        handler = handlers.get(str(db_type))
        if handler is None:
            raise ValueError(f"暂不支持的数据库类型: {db_type}")
        return handler

    def _query_connector(
        self: "DatabaseConnectorService",
        *,
        db_type: str,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object],
        limit: int,
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        handler = self._get_query_handler(db_type)
        return handler(
            connection_mode=connection_mode,
            payload=payload,
            sql=sql,
            params=params,
            limit=limit,
            timeout_seconds=timeout_seconds,
        )

    def _execute_connector(
        self: "DatabaseConnectorService",
        *,
        db_type: str,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object] | dict[str, Any] | None,
        timeout_seconds: int,
    ) -> int:
        handler = self._get_execute_handler(db_type)
        return handler(
            connection_mode=connection_mode,
            payload=payload,
            sql=sql,
            params=params,
            timeout_seconds=timeout_seconds,
        )

    def _run_connection_test(
        self: "DatabaseConnectorService",
        db_type: str,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> DatabaseConnectorTestResult:
        started_at = time.perf_counter()
        try:
            handler = self._get_connection_test_handler(db_type)
            handler(connection_mode, payload)

            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return DatabaseConnectorTestResult(
                success=True,
                db_type=db_type,  # type: ignore[arg-type]
                message="连接测试成功：目标数据库账号可连通",
                latency_ms=latency_ms,
            )
        except Exception as exc:
            message = self._redact_error_text(str(exc)) or "连接测试失败"
            return DatabaseConnectorTestResult(
                success=False,
                db_type=db_type,  # type: ignore[arg-type]
                message=f"目标数据库账号连接失败：{message}",
                latency_ms=int((time.perf_counter() - started_at) * 1000),
            )

    def _test_postgres_connection(
        self: "DatabaseConnectorService", connection_mode: str, payload: dict[str, Any]
    ) -> None:
        self._get_connector_adapter("postgres").test_connection(
            connection_mode=connection_mode,
            payload=payload,
        )

    def _test_mysql_connection(
        self: "DatabaseConnectorService", connection_mode: str, payload: dict[str, Any]
    ) -> None:
        self._get_connector_adapter("mysql").test_connection(
            connection_mode=connection_mode,
            payload=payload,
        )

    def _test_influxdb3_connection(
        self: "DatabaseConnectorService", connection_mode: str, payload: dict[str, Any]
    ) -> None:
        self._get_connector_adapter("influxdb3").test_connection(
            connection_mode=connection_mode,
            payload=payload,
        )

    def _query_postgres(
        self: "DatabaseConnectorService",
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object],
        limit: int,
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        try:
            return self._get_connector_adapter("postgres").query(
                connection_mode=connection_mode,
                payload=payload,
                sql=sql,
                params=params,
                limit=limit,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="查询",
                fallback_message="只读查询失败",
            )

    def _query_mysql(
        self: "DatabaseConnectorService",
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object],
        limit: int,
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        try:
            return self._get_connector_adapter("mysql").query(
                connection_mode=connection_mode,
                payload=payload,
                sql=sql,
                params=params,
                limit=limit,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="查询",
                fallback_message="只读查询失败",
            )

    def _query_influxdb3(
        self: "DatabaseConnectorService",
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object],
        limit: int,
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        try:
            return self._get_connector_adapter("influxdb3").query(
                connection_mode=connection_mode,
                payload=payload,
                sql=sql,
                params=params,
                limit=limit,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="查询",
                fallback_message="只读查询失败",
            )

    def _execute_postgres(
        self: "DatabaseConnectorService",
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object] | dict[str, Any] | None,
        timeout_seconds: int,
    ) -> int:
        try:
            return self._get_connector_adapter("postgres").execute(
                connection_mode=connection_mode,
                payload=payload,
                sql=sql,
                params=params,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="写入",
                fallback_message="写入执行失败",
            )

    def _execute_mysql(
        self: "DatabaseConnectorService",
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object] | dict[str, Any] | None,
        timeout_seconds: int,
    ) -> int:
        try:
            return self._get_connector_adapter("mysql").execute(
                connection_mode=connection_mode,
                payload=payload,
                sql=sql,
                params=params,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="写入",
                fallback_message="写入执行失败",
            )

    def _execute_influxdb3(
        self: "DatabaseConnectorService",
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: list[object] | dict[str, Any] | None,
        timeout_seconds: int,
    ) -> int:
        _ = (connection_mode, payload, sql, params, timeout_seconds)
        raise DatabaseConnectorPlatformRejectionError(
            "InfluxDB 3 连接器仅支持只读 query/list/describe，不支持 execute"
        )
