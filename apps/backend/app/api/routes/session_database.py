"""
运行时数据库 broker 路由
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.config import WORKSPACE_DIR
from app.models.database_access import (
    RuntimeDatabaseDescribeTableResponse,
    RuntimeDatabaseErrorDetail,
    RuntimeDatabaseExecuteRequest,
    RuntimeDatabaseExecuteResponse,
    RuntimeDatabaseHandlesResponse,
    RuntimeDatabaseListTablesResponse,
    RuntimeDatabaseQueryRequest,
    RuntimeDatabaseQueryResponse,
)
from app.services.connector import (
    DatabaseConnectorApprovalRejectedError,
    DatabaseConnectorApprovalRequiredError,
    DatabaseConnectorApprovalTimeoutError,
    DatabaseConnectorAttachmentMissingError,
    DatabaseConnectorCapabilityDeniedError,
    DatabaseConnectorGrantDeniedError,
    DatabaseConnectorNotFoundError,
    DatabaseConnectorPlatformRejectionError,
    DatabaseConnectorRemoteExecutionError,
    DatabaseConnectorRemotePermissionError,
)
from app.services.database import (
    DatabaseAccessBroker,
    decode_runtime_database_token,
)
from app.services.session import SessionManager

router = APIRouter(prefix="/session-database", tags=["session-database"])
_SESSION_MANAGER = SessionManager(WORKSPACE_DIR)
_BROKER = DatabaseAccessBroker(WORKSPACE_DIR, session_manager=_SESSION_MANAGER)


def _runtime_database_http_error(
    *,
    status_code: int,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
) -> HTTPException:
    _ = retryable
    return HTTPException(
        status_code=status_code,
        detail=RuntimeDatabaseErrorDetail(
            code=code,
            category=category,
            message=message,
        ).model_dump(include={"code", "category", "message"}),
    )


def _map_value_error(exc: ValueError) -> HTTPException:
    message = str(exc)
    if message == "目标会话不存在":
        return _runtime_database_http_error(
            status_code=404,
            code="session_not_found",
            category="session",
            message=message,
        )
    if message.startswith("不支持的数据库句柄"):
        return _runtime_database_http_error(
            status_code=400,
            code="invalid_handle",
            category="request",
            message=message,
        )
    if message == "数据库连接器句柄缺少 connector_id":
        return _runtime_database_http_error(
            status_code=400,
            code="invalid_handle",
            category="request",
            message=message,
        )
    if message == "非法表名":
        return _runtime_database_http_error(
            status_code=400,
            code="invalid_table_name",
            category="request",
            message=message,
        )
    return _runtime_database_http_error(
        status_code=400,
        code="invalid_request",
        category="request",
        message=message,
    )


def _map_connector_access_error(exc: Exception) -> HTTPException:
    message = str(exc)

    if isinstance(exc, DatabaseConnectorAttachmentMissingError):
        return _runtime_database_http_error(
            status_code=403,
            code="session_connector_not_attached",
            category="session",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorNotFoundError):
        return _runtime_database_http_error(
            status_code=404,
            code="connector_not_found",
            category="session",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorCapabilityDeniedError):
        return _runtime_database_http_error(
            status_code=403,
            code="capability_denied",
            category="platform",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorGrantDeniedError):
        return _runtime_database_http_error(
            status_code=403,
            code="platform_grant_denied",
            category="platform",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorApprovalTimeoutError):
        return _runtime_database_http_error(
            status_code=409,
            code="approval_timeout",
            category="approval",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorApprovalRejectedError):
        return _runtime_database_http_error(
            status_code=403,
            code="approval_rejected",
            category="approval",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorApprovalRequiredError):
        return _runtime_database_http_error(
            status_code=403,
            code="approval_required",
            category="approval",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorRemotePermissionError):
        return _runtime_database_http_error(
            status_code=403,
            code="remote_permission_denied",
            category="remote",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorRemoteExecutionError):
        return _runtime_database_http_error(
            status_code=502,
            code="remote_execution_error",
            category="remote",
            message=message,
        )
    if isinstance(exc, DatabaseConnectorPlatformRejectionError):
        if message == "数据库连接器不存在":
            return _runtime_database_http_error(
                status_code=404,
                code="connector_not_found",
                category="session",
                message=message,
            )
        if message == "会话未挂载该数据库连接器":
            return _runtime_database_http_error(
                status_code=403,
                code="session_connector_not_attached",
                category="session",
                message=message,
            )
        if "未获授权执行动作" in message:
            return _runtime_database_http_error(
                status_code=403,
                code="platform_grant_denied",
                category="platform",
                message=message,
            )
        if "能力上限不支持动作" in message:
            return _runtime_database_http_error(
                status_code=403,
                code="capability_denied",
                category="platform",
                message=message,
            )
        return _runtime_database_http_error(
            status_code=403,
            code="platform_rejected",
            category="platform",
            message=message,
        )

    return _runtime_database_http_error(
        status_code=502,
        code="runtime_error",
        category="runtime",
        message=message,
        retryable=True,
    )


def _get_runtime_db_context(request: Request):
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        raise _runtime_database_http_error(
            status_code=401,
            code="missing_runtime_database_token",
            category="auth",
            message="缺少 runtime database token",
        )

    token = auth_header[7:]
    context = decode_runtime_database_token(token)
    if context is None:
        raise _runtime_database_http_error(
            status_code=401,
            code="invalid_runtime_database_token",
            category="auth",
            message="runtime database token 无效",
        )
    return context


@router.get("/handles", response_model=RuntimeDatabaseHandlesResponse)
async def runtime_database_list_handles(request: Request):
    context = _get_runtime_db_context(request)
    try:
        return _BROKER.list_handles(
            user_id=context.user_id,
            session_id=context.session_id,
            sandbox_mode=context.sandbox_mode,
        )
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except RuntimeError as exc:
        raise _runtime_database_http_error(
            status_code=502,
            code="runtime_error",
            category="runtime",
            message=str(exc),
            retryable=True,
        ) from exc


@router.post("/query", response_model=RuntimeDatabaseQueryResponse)
async def runtime_database_query(
    request: Request,
    payload: RuntimeDatabaseQueryRequest,
):
    context = _get_runtime_db_context(request)
    try:
        return await _BROKER.query_async(
            user_id=context.user_id,
            session_id=context.session_id,
            handle=payload.handle,
            sql=payload.sql,
            params=payload.params,
            limit=payload.limit,
            sandbox_mode=context.sandbox_mode,
        )
    except (
        DatabaseConnectorApprovalRequiredError,
        DatabaseConnectorAttachmentMissingError,
        DatabaseConnectorCapabilityDeniedError,
        DatabaseConnectorGrantDeniedError,
        DatabaseConnectorNotFoundError,
        DatabaseConnectorPlatformRejectionError,
        DatabaseConnectorRemoteExecutionError,
        DatabaseConnectorRemotePermissionError,
    ) as exc:
        raise _map_connector_access_error(exc) from exc
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except RuntimeError as exc:
        raise _runtime_database_http_error(
            status_code=502,
            code="runtime_error",
            category="runtime",
            message=str(exc),
            retryable=True,
        ) from exc


@router.post("/execute", response_model=RuntimeDatabaseExecuteResponse)
async def runtime_database_execute(
    request: Request,
    payload: RuntimeDatabaseExecuteRequest,
):
    context = _get_runtime_db_context(request)
    try:
        return await _BROKER.execute(
            user_id=context.user_id,
            session_id=context.session_id,
            handle=payload.handle,
            sql=payload.sql,
            params=payload.params,
            sandbox_mode=context.sandbox_mode,
        )
    except (
        DatabaseConnectorApprovalRequiredError,
        DatabaseConnectorApprovalRejectedError,
        DatabaseConnectorApprovalTimeoutError,
        DatabaseConnectorAttachmentMissingError,
        DatabaseConnectorCapabilityDeniedError,
        DatabaseConnectorGrantDeniedError,
        DatabaseConnectorNotFoundError,
        DatabaseConnectorPlatformRejectionError,
        DatabaseConnectorRemoteExecutionError,
        DatabaseConnectorRemotePermissionError,
    ) as exc:
        raise _map_connector_access_error(exc) from exc
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except RuntimeError as exc:
        raise _runtime_database_http_error(
            status_code=502,
            code="runtime_error",
            category="runtime",
            message=str(exc),
            retryable=True,
        ) from exc


@router.get("/tables", response_model=RuntimeDatabaseListTablesResponse)
async def runtime_database_list_tables(
    request: Request,
    handle: str = Query("", description="数据库资源句柄"),
):
    context = _get_runtime_db_context(request)
    try:
        return await _BROKER.list_tables_async(
            user_id=context.user_id,
            session_id=context.session_id,
            handle=handle,
            sandbox_mode=context.sandbox_mode,
        )
    except (
        DatabaseConnectorApprovalRequiredError,
        DatabaseConnectorAttachmentMissingError,
        DatabaseConnectorCapabilityDeniedError,
        DatabaseConnectorGrantDeniedError,
        DatabaseConnectorNotFoundError,
        DatabaseConnectorPlatformRejectionError,
        DatabaseConnectorRemoteExecutionError,
        DatabaseConnectorRemotePermissionError,
    ) as exc:
        raise _map_connector_access_error(exc) from exc
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except RuntimeError as exc:
        raise _runtime_database_http_error(
            status_code=502,
            code="runtime_error",
            category="runtime",
            message=str(exc),
            retryable=True,
        ) from exc


@router.get("/tables/{table_name}", response_model=RuntimeDatabaseDescribeTableResponse)
async def runtime_database_describe_table(
    request: Request,
    table_name: str,
    handle: str = Query("", description="数据库资源句柄"),
):
    context = _get_runtime_db_context(request)
    try:
        return await _BROKER.describe_table_async(
            user_id=context.user_id,
            session_id=context.session_id,
            handle=handle,
            table_name=table_name,
            sandbox_mode=context.sandbox_mode,
        )
    except (
        DatabaseConnectorApprovalRequiredError,
        DatabaseConnectorAttachmentMissingError,
        DatabaseConnectorCapabilityDeniedError,
        DatabaseConnectorGrantDeniedError,
        DatabaseConnectorNotFoundError,
        DatabaseConnectorPlatformRejectionError,
        DatabaseConnectorRemoteExecutionError,
        DatabaseConnectorRemotePermissionError,
    ) as exc:
        raise _map_connector_access_error(exc) from exc
    except ValueError as exc:
        raise _map_value_error(exc) from exc
    except RuntimeError as exc:
        raise _runtime_database_http_error(
            status_code=502,
            code="runtime_error",
            category="runtime",
            message=str(exc),
            retryable=True,
        ) from exc
