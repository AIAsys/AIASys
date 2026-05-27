"""
元数据查询 Mixin

负责表结构、列信息等元数据查询
"""

import time
from typing import TYPE_CHECKING, Any

from app.models.database_connector import (
    DatabaseDescribeTableResponse,
    DatabaseListTablesResponse,
    DatabaseTableColumnInfo,
    DatabaseTableInfo,
)
from app.services.connector.constants import _IDENTIFIER_RE

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService


class MetadataMixin:
    """元数据查询功能"""

    def list_attached_connector_tables(
        self: "DatabaseConnectorService",
        *,
        user_id: str,
        session_id: str,
        connector_id: str,
    ) -> DatabaseListTablesResponse:
        """列出会话已挂载连接器可见表。"""
        self._ensure_session_exists(user_id, session_id)
        started_at = time.perf_counter()
        action_context = self.resolve_attachment_action_context(
            user_id=user_id,
            session_id=session_id,
            connector_id=connector_id,
            action="list_tables",
        )
        connector_record = action_context.connector_record
        connector_payload = action_context.connector_payload

        columns, rows = self._list_connector_tables_via_adapter(
            db_type=str(connector_record["db_type"]),
            connection_mode=connector_record["connection_mode"],
            payload=connector_payload,
            timeout_seconds=int(connector_payload.get("query_timeout_seconds") or 15),
        )

        if len(columns) < 2:
            raise RuntimeError("表结构查询返回格式异常")

        allowed_schemas = set(connector_payload.get("allowed_schemas") or [])
        allowed_tables = set(connector_payload.get("allowed_tables") or [])

        tables: list[DatabaseTableInfo] = []
        for schema_value, table_value, *_ in rows:
            schema_name = str(schema_value)
            table_name = str(table_value)
            full_name = f"{schema_name}.{table_name}"
            if allowed_schemas and schema_name not in allowed_schemas:
                continue
            if allowed_tables and full_name not in allowed_tables:
                continue
            tables.append(
                DatabaseTableInfo(
                    schema_name=schema_name,
                    table=table_name,
                    full_name=full_name,
                )
            )

        return DatabaseListTablesResponse(
            session_id=session_id,
            connector_id=connector_id,
            handle=action_context.handle,
            db_type=connector_record["db_type"],  # type: ignore[arg-type]
            audit_id=action_context.audit_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            tables=tables,
        )

    def describe_attached_connector_table(
        self: "DatabaseConnectorService",
        *,
        user_id: str,
        session_id: str,
        connector_id: str,
        table_name: str,
    ) -> DatabaseDescribeTableResponse:
        """查看会话已挂载连接器的单表字段结构。"""
        self._ensure_session_exists(user_id, session_id)
        started_at = time.perf_counter()
        action_context = self.resolve_attachment_action_context(
            user_id=user_id,
            session_id=session_id,
            connector_id=connector_id,
            action="describe_table",
        )
        connector_record = action_context.connector_record
        connector_payload = action_context.connector_payload

        schema_name, pure_table_name = self._split_table_name(
            connector_record["db_type"],
            table_name,
            default_schema=str(connector_payload.get("database_name") or "default"),
        )
        full_name = f"{schema_name}.{pure_table_name}"
        self._validate_table_scope(
            connector_payload=connector_payload,
            schema_name=schema_name,
            full_name=full_name,
        )

        timeout_seconds = int(connector_payload.get("query_timeout_seconds") or 15)
        columns, rows = self._describe_connector_table_via_adapter(
            db_type=str(connector_record["db_type"]),
            connection_mode=connector_record["connection_mode"],
            payload=connector_payload,
            schema_name=schema_name,
            table_name=pure_table_name,
            timeout_seconds=timeout_seconds,
        )

        if not rows:
            raise ValueError("目标表不存在或当前连接器无权限访问该表")

        column_positions = {
            str(column).strip().lower(): index for index, column in enumerate(columns)
        }
        required_columns = {"column_name", "data_type", "is_nullable"}
        if not required_columns.issubset(column_positions):
            raise RuntimeError("表结构查询返回格式异常")

        table_columns: list[DatabaseTableColumnInfo] = []
        for row in rows:
            name = row[column_positions["column_name"]]
            data_type = row[column_positions["data_type"]]
            is_nullable = row[column_positions["is_nullable"]]
            if name is None or data_type is None or is_nullable is None:
                raise RuntimeError("表结构查询返回格式异常")
            default_index = column_positions.get("column_default")
            default_value = (
                row[default_index]
                if default_index is not None and default_index < len(row)
                else None
            )
            nullable_text = str(is_nullable).lower()
            table_columns.append(
                DatabaseTableColumnInfo(
                    name=str(name),
                    data_type=str(data_type),
                    nullable=nullable_text in {"yes", "true", "1"},
                    default=None if default_value is None else str(default_value),
                )
            )

        return DatabaseDescribeTableResponse(
            session_id=session_id,
            connector_id=connector_id,
            handle=action_context.handle,
            db_type=connector_record["db_type"],  # type: ignore[arg-type]
            audit_id=action_context.audit_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            schema_name=schema_name,
            table=pure_table_name,
            columns=table_columns,
        )

    def _list_connector_tables_via_adapter(
        self: "DatabaseConnectorService",
        *,
        db_type: str,
        connection_mode: str,
        payload: dict[str, Any],
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        adapter = self._get_connector_adapter(db_type)
        try:
            sql, params, limit = adapter.build_list_tables_query()
            return self._query_connector(
                db_type=db_type,
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

    def _describe_connector_table_via_adapter(
        self: "DatabaseConnectorService",
        *,
        db_type: str,
        connection_mode: str,
        payload: dict[str, Any],
        schema_name: str,
        table_name: str,
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[Any, ...]]]:
        adapter = self._get_connector_adapter(db_type)
        try:
            sql, params, limit = adapter.build_describe_table_query(
                schema_name=schema_name,
                table_name=table_name,
            )
            return self._query_connector(
                db_type=db_type,
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

    def _split_table_name(
        self: "DatabaseConnectorService",
        db_type: str,
        table_name: str,
        *,
        default_schema: str,
    ) -> tuple[str, str]:
        cleaned = str(table_name or "").strip()
        if not cleaned:
            raise ValueError("table_name 不能为空")

        if "." in cleaned:
            schema_name, pure_table_name = cleaned.split(".", 1)
        else:
            if db_type == "postgres":
                schema_name = "public"
            elif db_type == "influxdb3":
                schema_name = "iox"
            else:
                schema_name = default_schema
            pure_table_name = cleaned

        schema_name = schema_name.strip()
        pure_table_name = pure_table_name.strip()
        if not _IDENTIFIER_RE.match(schema_name):
            raise ValueError("schema 名称不合法")
        if not _IDENTIFIER_RE.match(pure_table_name):
            raise ValueError("table 名称不合法")
        return schema_name, pure_table_name

    def _validate_table_scope(
        self: "DatabaseConnectorService",
        *,
        connector_payload: dict[str, Any],
        schema_name: str,
        full_name: str,
    ) -> None:
        allowed_schemas = set(connector_payload.get("allowed_schemas") or [])
        allowed_tables = set(connector_payload.get("allowed_tables") or [])
        if allowed_schemas and schema_name not in allowed_schemas:
            raise ValueError("当前连接器无权限访问该 schema")
        if allowed_tables and full_name not in allowed_tables:
            raise ValueError("当前连接器无权限访问该表")
