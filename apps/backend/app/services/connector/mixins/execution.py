"""
执行操作 Mixin

负责写入和 DDL 执行操作
"""

import time
from typing import TYPE_CHECKING, Any

from app.models.database_access import RuntimeDatabaseExecuteResponse

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService


class ExecutionMixin:
    """执行操作功能"""

    async def execute_attached_connector(
        self: "DatabaseConnectorService",
        *,
        user_id: str,
        session_id: str,
        connector_id: str,
        sql: str,
        params: list[object] | dict[str, Any] | None = None,
    ) -> RuntimeDatabaseExecuteResponse:
        """使用会话已挂载连接器执行写入或 DDL。"""
        self._ensure_session_exists(user_id, session_id)
        started_at = time.perf_counter()
        normalized_sql = self._normalize_execute_sql(sql)
        action_context = self.resolve_attachment_action_context(
            user_id=user_id,
            session_id=session_id,
            connector_id=connector_id,
            action="execute",
        )
        connector_record = action_context.connector_record
        connector_payload = action_context.connector_payload
        timeout_seconds = int(connector_payload.get("query_timeout_seconds") or 15)

        try:
            affected_rows = self._execute_connector(
                db_type=str(connector_record["db_type"]),
                connection_mode=connector_record["connection_mode"],
                payload=connector_payload,
                sql=normalized_sql,
                params=params,
                timeout_seconds=timeout_seconds,
            )
        except Exception as exc:
            self._raise_remote_database_error(
                exc,
                action_label="执行",
                fallback_message="数据库执行失败",
            )

        return RuntimeDatabaseExecuteResponse(
            handle=action_context.handle,
            audit_id=action_context.audit_id,
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            affected_rows=max(affected_rows, 0),
            message="ok",
        )
