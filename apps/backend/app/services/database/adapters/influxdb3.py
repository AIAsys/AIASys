from __future__ import annotations

import json
from typing import Any
from urllib import error, parse, request

from app.models.database_connector import DEFAULT_CONNECTOR_PORTS

from .base import (
    ConnectorAdapter,
    PreparedReadonlyQuery,
    QueryResult,
    ReadonlySqlParams,
    SqlParams,
)


class InfluxDb3ConnectorAdapter(ConnectorAdapter):
    """InfluxDB 3 query-only adapter。"""

    db_type = "influxdb3"

    def is_driver_available(self) -> bool:
        return True

    def test_connection(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> None:
        timeout = int(payload.get("query_timeout_seconds") or 15)
        self.query(
            connection_mode=connection_mode,
            payload=payload,
            sql="SELECT 1 AS healthcheck",
            params=[],
            limit=1,
            timeout_seconds=timeout,
        )

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
        _ = limit
        if params:
            raise ValueError("当前版本 InfluxDB 3 查询暂不支持位置参数")
        rows = self._query_json_rows(
            connection_mode=connection_mode,
            payload=payload,
            sql=sql,
            timeout_seconds=timeout_seconds,
        )
        return self._normalize_query_rows(rows)

    def execute(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        params: SqlParams,
        timeout_seconds: int,
    ) -> int:
        _ = (connection_mode, payload, sql, params, timeout_seconds)
        raise RuntimeError("InfluxDB 3 连接器仅支持 query-only，不支持 execute")

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

    def build_list_tables_query(self) -> PreparedReadonlyQuery:
        return (
            "SELECT table_schema, table_name "
            "FROM information_schema.tables "
            "WHERE table_schema <> 'information_schema' "
            "ORDER BY table_schema, table_name",
            [],
            10000,
        )

    def build_describe_table_query(
        self,
        *,
        schema_name: str,
        table_name: str,
    ) -> PreparedReadonlyQuery:
        escaped_schema = schema_name.replace("'", "''")
        escaped_table = table_name.replace("'", "''")
        return (
            "SELECT column_name, data_type, is_nullable, NULL AS column_default "
            "FROM information_schema.columns "
            f"WHERE table_schema = '{escaped_schema}' "
            f"AND table_name = '{escaped_table}' "
            "ORDER BY ordinal_position",
            [],
            2000,
        )

    def _query_json_rows(
        self,
        *,
        connection_mode: str,
        payload: dict[str, Any],
        sql: str,
        timeout_seconds: int,
    ) -> list[dict[str, Any]]:
        database_name = str(payload.get("database_name") or "").strip()
        if not database_name:
            raise ValueError("InfluxDB 3 连接器缺少 database_name")

        api_token = str(payload.get("api_token") or "").strip()
        if not api_token:
            raise ValueError("InfluxDB 3 连接器缺少 api_token")

        query_url = f"{self._resolve_base_url(connection_mode, payload)}/api/v3/query_sql"
        req = request.Request(
            query_url,
            data=json.dumps(
                {
                    "db": database_name,
                    "q": sql,
                    "format": "json",
                }
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace").strip()
            message = detail or getattr(exc, "reason", "") or f"HTTP {exc.code}"
            raise RuntimeError(f"InfluxDB 3 查询失败: {message}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"InfluxDB 3 请求失败: {exc.reason}") from exc

        try:
            decoded = json.loads(raw_body or "[]")
        except json.JSONDecodeError as exc:
            raise RuntimeError("InfluxDB 3 返回了无法解析的 JSON 响应") from exc

        if isinstance(decoded, dict):
            error_message = decoded.get("error")
            if error_message:
                raise RuntimeError(str(error_message))
            raise RuntimeError("InfluxDB 3 返回格式异常")
        if not isinstance(decoded, list):
            raise RuntimeError("InfluxDB 3 返回格式异常")

        rows: list[dict[str, Any]] = []
        for item in decoded:
            if not isinstance(item, dict):
                raise RuntimeError("InfluxDB 3 返回格式异常")
            rows.append(item)
        return rows

    def _normalize_query_rows(self, rows: list[dict[str, Any]]) -> QueryResult:
        if not rows:
            return [], []
        columns: list[str] = []
        for row in rows:
            for key in row.keys():
                key_text = str(key)
                if key_text not in columns:
                    columns.append(key_text)
        normalized_rows = [tuple(row.get(column) for column in columns) for row in rows]
        return columns, normalized_rows

    def _resolve_base_url(
        self,
        connection_mode: str,
        payload: dict[str, Any],
    ) -> str:
        if connection_mode == "url":
            raw_url = str(payload.get("connection_url") or "").strip()
            if not raw_url:
                raise ValueError("InfluxDB 3 URL 模式必须提供 connection_url")
            return self._normalize_base_url(raw_url, default_port=None)

        raw_host = str(payload.get("host") or "").strip()
        if not raw_host:
            raise ValueError("InfluxDB 3 字段模式必须提供 host")
        default_port = int(payload.get("port") or DEFAULT_CONNECTOR_PORTS["influxdb3"])
        return self._normalize_base_url(raw_host, default_port=default_port)

    def _normalize_base_url(
        self,
        raw_url: str,
        *,
        default_port: int | None,
    ) -> str:
        candidate = raw_url if "://" in raw_url else f"http://{raw_url}"
        parsed = parse.urlparse(candidate)
        if parsed.scheme not in {"http", "https"}:
            raise ValueError("InfluxDB 3 仅支持 HTTP/HTTPS 连接")
        if not parsed.hostname:
            raise ValueError("InfluxDB 3 连接地址不合法")

        base = f"{parsed.scheme}://{parsed.hostname}"
        port = parsed.port or default_port
        if port:
            base = f"{base}:{port}"
        path = parsed.path.rstrip("/")
        if path:
            base = f"{base}{path}"
        return base
