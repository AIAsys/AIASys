from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from app.core.config import DATA_DIR, PORT, WORKSPACE_DIR
from app.core.security import create_access_token, decode_access_token
from app.models.database_access import (
    RuntimeDatabaseColumnInfo,
    RuntimeDatabaseDescribeTableResponse,
    RuntimeDatabaseExecuteResponse,
    RuntimeDatabaseHandleInfo,
    RuntimeDatabaseHandlesResponse,
    RuntimeDatabaseListTablesResponse,
    RuntimeDatabaseQueryResponse,
)

if TYPE_CHECKING:
    from app.services.connector import DatabaseConnectorService
    from app.services.session import SessionManager

logger = logging.getLogger(__name__)

RUNTIME_DB_SCOPE = "runtime_db"
DEFAULT_RUNTIME_DB_QUERY_LIMIT = 1000
RUNTIME_DB_BROKER_BASE_URL_ENV_KEYS = (
    "AIASYS_RUNTIME_DATABASE_BROKER_BASE_URL",
    "AIASYS_BACKEND_BASE_URL",
)
_TABLE_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class RuntimeDatabaseContext:
    user_id: str
    session_id: str
    sandbox_mode: str


def create_runtime_database_token(
    *,
    user_id: str,
    session_id: str,
    sandbox_mode: str,
) -> str:
    return create_access_token(
        {
            "sub": user_id,
            "sid": session_id,
            "scope": RUNTIME_DB_SCOPE,
            "sandbox_mode": sandbox_mode,
        },
        expires_delta=timedelta(hours=8),
    )


def decode_runtime_database_token(token: str) -> RuntimeDatabaseContext | None:
    payload = decode_access_token(token)
    if not payload:
        return None

    if payload.get("scope") != RUNTIME_DB_SCOPE:
        return None

    user_id = payload.get("sub")
    session_id = payload.get("sid")
    sandbox_mode = payload.get("sandbox_mode") or "unknown"
    if not user_id or not session_id:
        return None

    return RuntimeDatabaseContext(
        user_id=str(user_id),
        session_id=str(session_id),
        sandbox_mode=str(sandbox_mode),
    )


def get_connector_credentials_path(session_id: str) -> Path:
    """返回会话级连接器凭据配置文件路径。"""
    return DATA_DIR / "runtime" / "connectors" / f"{session_id}.json"


def build_runtime_database_helper_env(
    *,
    user_id: str,
    session_id: str,
    sandbox_mode: str,
    backend_base_url: str | None = None,
    default_handle: str = "",
) -> dict[str, str]:
    base_url = (backend_base_url or f"http://127.0.0.1:{PORT}").rstrip("/")
    return {
        "AIASYS_DB_BROKER_URL": f"{base_url}/api/session-database",
        "AIASYS_DB_SESSION_TOKEN": create_runtime_database_token(
            user_id=user_id,
            session_id=session_id,
            sandbox_mode=sandbox_mode,
        ),
        "AIASYS_DB_DEFAULT_HANDLE": default_handle,
    }


class DatabaseAccessBroker:
    """统一的运行时数据库访问 broker。"""

    def __init__(
        self,
        workspace_root=WORKSPACE_DIR,
        *,
        session_manager: Optional[SessionManager] = None,
        connector_service: Optional[DatabaseConnectorService] = None,
    ) -> None:
        self.workspace_root = workspace_root
        if session_manager is not None:
            self.session_manager = session_manager
        else:
            from app.services.session import SessionManager

            self.session_manager = SessionManager(self.workspace_root)
        if connector_service is not None:
            self.connector_service = connector_service
        else:
            # 延迟导入避免循环
            from app.services.connector import DatabaseConnectorService

            self.connector_service = DatabaseConnectorService(
                self.workspace_root,
                session_manager=self.session_manager,
            )

    def list_handles(
        self,
        *,
        user_id: str,
        session_id: str,
        sandbox_mode: str | None = None,
    ) -> RuntimeDatabaseHandlesResponse:
        self._ensure_session_exists(user_id, session_id)
        session = self.session_manager.get_session(session_id, user_id)
        workspace_id = session.workspace_id if session else None
        connector_handles: list[RuntimeDatabaseHandleInfo] = []
        for conn in self.connector_service.list_connectors(user_id, workspace_id=workspace_id):
            connector_handles.append(
                RuntimeDatabaseHandleInfo(
                    handle=f"connector:{conn.connector_id}",
                    connector_id=conn.connector_id,
                    name=conn.name or conn.connector_id,
                    db_type=conn.db_type or "unknown",
                    description=conn.description,
                    allow_notebook_access=conn.allow_notebook_access,
                    attached_at="",
                )
            )
        return RuntimeDatabaseHandlesResponse(
            session_id=session_id,
            handles=connector_handles,
        )

    def query(
        self,
        *,
        user_id: str,
        session_id: str,
        handle: str,
        sql: str,
        params: list[Any] | dict[str, Any] | None = None,
        limit: int | None = None,
        sandbox_mode: str | None = None,
    ) -> RuntimeDatabaseQueryResponse:
        self._ensure_session_exists(user_id, session_id)
        resolved_handle = handle or ""
        if resolved_handle.startswith("connector:"):
            connector_id = self._parse_connector_handle(resolved_handle)
            try:
                result = self.connector_service.query_attached_connector_readonly(
                    user_id=user_id,
                    session_id=session_id,
                    connector_id=connector_id,
                    sql=sql,
                    params=self._normalize_connector_params(params),
                    limit=limit,
                )
            except Exception as exc:
                outcome, rejection_reason = self._resolve_connector_error_outcome(exc)
                self._audit_connector_access(
                    action="query",
                    outcome=outcome,
                    rejection_reason=rejection_reason,
                    user_id=user_id,
                    session_id=session_id,
                    sandbox_mode=sandbox_mode,
                    handle=resolved_handle,
                    connector_id=connector_id,
                    sql=sql,
                    requested_limit=limit,
                    error=exc,
                )
                raise

            response = RuntimeDatabaseQueryResponse(
                handle=resolved_handle,
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
                columns=result.columns,
                rows=result.rows,
                row_count=result.row_count,
                truncated=result.truncated,
                applied_limit=result.applied_limit,
            )
            self._audit_connector_access(
                action="query",
                outcome="success",
                user_id=user_id,
                session_id=session_id,
                sandbox_mode=sandbox_mode,
                handle=resolved_handle,
                connector_id=connector_id,
                sql=sql,
                requested_limit=limit,
                applied_limit=result.applied_limit,
                row_count=result.row_count,
                truncated=result.truncated,
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
            )
            return response
        raise ValueError(f"不支持的数据库句柄: {resolved_handle}")

    async def execute(
        self,
        *,
        user_id: str,
        session_id: str,
        handle: str,
        sql: str,
        params: list[Any] | dict[str, Any] | None = None,
        sandbox_mode: str | None = None,
    ) -> RuntimeDatabaseExecuteResponse:
        self._ensure_session_exists(user_id, session_id)
        resolved_handle = handle or ""
        if resolved_handle.startswith("connector:"):
            connector_id = self._parse_connector_handle(resolved_handle)
            try:
                result = await self.connector_service.execute_attached_connector(
                    user_id=user_id,
                    session_id=session_id,
                    connector_id=connector_id,
                    sql=sql,
                    params=params,
                )
            except Exception as exc:
                outcome, rejection_reason = self._resolve_connector_error_outcome(exc)
                self._audit_connector_access(
                    action="execute",
                    outcome=outcome,
                    rejection_reason=rejection_reason,
                    user_id=user_id,
                    session_id=session_id,
                    sandbox_mode=sandbox_mode,
                    handle=resolved_handle,
                    connector_id=connector_id,
                    sql=sql,
                    error=exc,
                )
                raise

            self._audit_connector_access(
                action="execute",
                outcome="success",
                user_id=user_id,
                session_id=session_id,
                sandbox_mode=sandbox_mode,
                handle=resolved_handle,
                connector_id=connector_id,
                sql=sql,
                row_count=result.affected_rows,
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
            )
            return result
        raise ValueError(f"不支持的数据库句柄: {resolved_handle}")

    def list_tables(
        self,
        *,
        user_id: str,
        session_id: str,
        handle: str,
        sandbox_mode: str | None = None,
    ) -> RuntimeDatabaseListTablesResponse:
        self._ensure_session_exists(user_id, session_id)
        resolved_handle = handle or ""
        if resolved_handle.startswith("connector:"):
            connector_id = self._parse_connector_handle(resolved_handle)
            try:
                result = self.connector_service.list_attached_connector_tables(
                    user_id=user_id,
                    session_id=session_id,
                    connector_id=connector_id,
                )
            except Exception as exc:
                outcome, rejection_reason = self._resolve_connector_error_outcome(exc)
                self._audit_connector_access(
                    action="list_tables",
                    outcome=outcome,
                    rejection_reason=rejection_reason,
                    user_id=user_id,
                    session_id=session_id,
                    sandbox_mode=sandbox_mode,
                    handle=resolved_handle,
                    connector_id=connector_id,
                    error=exc,
                )
                raise

            response = RuntimeDatabaseListTablesResponse(
                handle=resolved_handle,
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
                tables=[getattr(table, "full_name", str(table)) for table in result.tables],
            )
            self._audit_connector_access(
                action="list_tables",
                outcome="success",
                user_id=user_id,
                session_id=session_id,
                sandbox_mode=sandbox_mode,
                handle=resolved_handle,
                connector_id=connector_id,
                row_count=len(response.tables),
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
            )
            return response
        raise ValueError(f"不支持的数据库句柄: {resolved_handle}")

    def describe_table(
        self,
        *,
        user_id: str,
        session_id: str,
        handle: str,
        table_name: str,
        sandbox_mode: str | None = None,
    ) -> RuntimeDatabaseDescribeTableResponse:
        self._ensure_session_exists(user_id, session_id)
        resolved_handle = handle or ""
        if resolved_handle.startswith("connector:"):
            connector_id = self._parse_connector_handle(resolved_handle)
            try:
                result = self.connector_service.describe_attached_connector_table(
                    user_id=user_id,
                    session_id=session_id,
                    connector_id=connector_id,
                    table_name=table_name,
                )
            except Exception as exc:
                outcome, rejection_reason = self._resolve_connector_error_outcome(exc)
                self._audit_connector_access(
                    action="describe_table",
                    outcome=outcome,
                    rejection_reason=rejection_reason,
                    user_id=user_id,
                    session_id=session_id,
                    sandbox_mode=sandbox_mode,
                    handle=resolved_handle,
                    connector_id=connector_id,
                    error=exc,
                )
                raise

            response = RuntimeDatabaseDescribeTableResponse(
                handle=resolved_handle,
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
                table=result.table,
                columns=[
                    RuntimeDatabaseColumnInfo(
                        name=getattr(column, "name", ""),
                        type=getattr(column, "data_type", getattr(column, "type", "")),
                        nullable=bool(getattr(column, "nullable", False)),
                        default=getattr(column, "default", None),
                    )
                    for column in result.columns
                ],
            )
            self._audit_connector_access(
                action="describe_table",
                outcome="success",
                user_id=user_id,
                session_id=session_id,
                sandbox_mode=sandbox_mode,
                handle=resolved_handle,
                connector_id=connector_id,
                row_count=len(response.columns),
                audit_id=result.audit_id,
                duration_ms=result.duration_ms,
            )
            return response
        raise ValueError(f"不支持的数据库句柄: {resolved_handle}")

    def _ensure_session_exists(self, user_id: str, session_id: str) -> None:
        if self.session_manager.get_session(session_id, user_id) is None:
            raise ValueError("目标会话不存在")

    def _normalize_connector_params(
        self,
        params: list[Any] | dict[str, Any] | None,
    ) -> list[Any]:
        if params is None:
            return []
        if isinstance(params, dict):
            raise ValueError("当前版本外部连接器 query 仅支持位置参数 list")
        return list(params)

    def _serialize_row(self, row: Any) -> list[Any]:
        return [self._serialize_value(value) for value in row]

    def _serialize_value(self, value: Any) -> Any:
        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                return str(value)
        return value

    def _parse_connector_handle(self, handle: str) -> str:
        connector_id = handle.split(":", 1)[1].strip()
        if not connector_id:
            raise ValueError("数据库连接器句柄缺少 connector_id")
        return connector_id

    def _audit_connector_access(
        self,
        *,
        action: str,
        outcome: str,
        user_id: str,
        session_id: str,
        sandbox_mode: str | None,
        handle: str,
        connector_id: str,
        sql: str | None = None,
        requested_limit: int | None = None,
        applied_limit: int | None = None,
        row_count: int | None = None,
        truncated: bool | None = None,
        audit_id: str | None = None,
        duration_ms: int | None = None,
        error: Exception | str | None = None,
        rejection_reason: str | None = None,
    ) -> None:
        sql_kind, sql_fingerprint = self._build_sql_audit_fields(sql)
        error_text = self._sanitize_audit_text(error)
        log_fn = logger.warning if outcome in {"error", "rejected"} else logger.info
        log_fn(
            "runtime_db_audit outcome=%s action=%s source=connector "
            "rejection_reason=%s user_id=%s session_id=%s sandbox_mode=%s handle=%s connector_id=%s "
            "sql_kind=%s sql_fingerprint=%s requested_limit=%s applied_limit=%s "
            "row_count=%s truncated=%s "
            "audit_id=%s duration_ms=%s error=%s",
            outcome,
            action,
            rejection_reason or "-",
            user_id,
            session_id,
            sandbox_mode or "unknown",
            handle,
            connector_id,
            sql_kind or "-",
            sql_fingerprint or "-",
            requested_limit,
            applied_limit,
            row_count,
            truncated,
            audit_id or "-",
            duration_ms,
            error_text or "-",
        )

    def _resolve_connector_error_outcome(self, exc: Exception) -> tuple[str, str | None]:
        # 延迟导入避免循环
        from app.services.connector import (
            DatabaseConnectorAccessError,
            DatabaseConnectorApprovalRejectedError,
            DatabaseConnectorApprovalRequiredError,
            DatabaseConnectorApprovalTimeoutError,
            DatabaseConnectorPlatformRejectionError,
            DatabaseConnectorRemoteExecutionError,
            DatabaseConnectorRemotePermissionError,
        )

        if isinstance(exc, DatabaseConnectorApprovalRejectedError):
            return "rejected", exc.audit_reason
        if isinstance(exc, DatabaseConnectorApprovalTimeoutError):
            return "rejected", exc.audit_reason
        if isinstance(exc, DatabaseConnectorApprovalRequiredError):
            return "rejected", exc.audit_reason
        if isinstance(exc, DatabaseConnectorPlatformRejectionError):
            return "rejected", exc.audit_reason
        if isinstance(exc, DatabaseConnectorRemotePermissionError):
            return "rejected", exc.audit_reason
        if isinstance(exc, DatabaseConnectorRemoteExecutionError):
            return "error", exc.audit_reason
        if isinstance(exc, DatabaseConnectorAccessError):
            return "error", getattr(exc, "audit_reason", "connector_error")
        if isinstance(exc, ValueError):
            return "rejected", "invalid_request"
        return "error", None

    def _build_sql_audit_fields(self, sql: str | None) -> tuple[str | None, str | None]:
        if sql is None:
            return None, None

        try:
            normalized_sql = self.connector_service._normalize_query_sql(sql)
        except Exception:
            normalized_sql = str(sql or "").strip()
            if not normalized_sql:
                return None, None

        first_token = normalized_sql.split(None, 1)[0].lower() if normalized_sql else None
        fingerprint = hashlib.sha256(normalized_sql.encode("utf-8")).hexdigest()[:16]
        return first_token, fingerprint

    def _sanitize_audit_text(self, error: Exception | str | None) -> str | None:
        if error is None:
            return None
        text = str(error)
        text = self.connector_service._redact_error_text(text) or text
        return text


def _resolve_runtime_database_broker_base_url(default_url: str) -> str:
    for env_name in RUNTIME_DB_BROKER_BASE_URL_ENV_KEYS:
        override = (os.environ.get(env_name) or "").strip()
        if override:
            return override.rstrip("/")
    return default_url.rstrip("/")


def get_default_runtime_database_broker_url_for_local() -> str:
    return _resolve_runtime_database_broker_base_url(f"http://127.0.0.1:{PORT}")


def get_default_runtime_database_broker_url_for_docker() -> str:
    return _resolve_runtime_database_broker_base_url(f"http://host.docker.internal:{PORT}")
