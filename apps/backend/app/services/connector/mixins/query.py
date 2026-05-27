"""
查询操作 Mixin

负责只读查询操作
"""

import time
from typing import TYPE_CHECKING, Optional

from app.models.database_connector import ReadonlyDatabaseQueryResponse

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService


class QueryMixin:
    """查询操作功能"""

    def query_attached_connector_readonly(
        self: "DatabaseConnectorService",
        *,
        user_id: str,
        session_id: str,
        connector_id: str,
        sql: str,
        params: list[object],
        limit: Optional[int] = None,
    ) -> ReadonlyDatabaseQueryResponse:
        """
        使用会话已挂载连接器执行只读查询。

        该路径是 broker 模式：查询在后端服务内执行，避免向 agent/runtime
        暴露 external raw DSN。
        """
        self._ensure_session_exists(user_id, session_id)
        started_at = time.perf_counter()
        action_context = self.resolve_attachment_action_context(
            user_id=user_id,
            session_id=session_id,
            connector_id=connector_id,
            action="query",
        )
        connector_record = action_context.connector_record
        connector_payload = action_context.connector_payload

        normalized_sql = self._normalize_query_sql(sql)
        self._validate_readonly_sql(normalized_sql)

        connector_limit = int(connector_payload.get("row_limit") or 1000)
        applied_limit = min(limit or connector_limit, connector_limit)
        timeout_seconds = int(connector_payload.get("query_timeout_seconds") or 15)

        try:
            columns, rows = self._query_connector(
                db_type=str(connector_record["db_type"]),
                connection_mode=connector_record["connection_mode"],
                payload=connector_payload,
                sql=normalized_sql,
                params=params,
                limit=applied_limit,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="查询",
                fallback_message="只读查询失败",
            )

        truncated = len(rows) > applied_limit
        if truncated:
            rows = rows[:applied_limit]

        return ReadonlyDatabaseQueryResponse(
            session_id=session_id,
            connector_id=connector_id,
            handle=action_context.handle,
            db_type=connector_record["db_type"],  # type: ignore[arg-type]
            audit_id=action_context.audit_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            columns=columns,
            rows=[list(row) for row in rows],
            row_count=len(rows),
            truncated=truncated,
            applied_limit=applied_limit,
        )
