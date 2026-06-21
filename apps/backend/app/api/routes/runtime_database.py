"""
面向前端登录态的运行时数据库 API。

说明：
- 前端使用正常登录态 + session_id 调用，不直接暴露 runtime database token
- 内部仍复用统一的 DatabaseAccessBroker，保证内置 DuckDB 与外部连接器共用一套能力边界
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from app.core.auth import require_auth
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
from app.models.user import UserInfo
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
from app.services.database import DatabaseAccessBroker
from app.services.session import SessionManager

router = APIRouter(prefix="/database/runtime", tags=["database-runtime"])
_SESSION_MANAGER = SessionManager(WORKSPACE_DIR)
_BROKER = DatabaseAccessBroker(WORKSPACE_DIR, session_manager=_SESSION_MANAGER)
_FRONTEND_SANDBOX_MODE = "analysis_ui"


class SessionRuntimeDatabaseQueryRequest(RuntimeDatabaseQueryRequest):
    """前端登录态查询请求。"""

    session_id: str = Field(..., min_length=1, description="目标会话 ID")


class SessionRuntimeDatabaseExecuteRequest(RuntimeDatabaseExecuteRequest):
    """前端登录态执行请求。"""

    session_id: str = Field(..., min_length=1, description="目标会话 ID")


def _runtime_database_http_error(
    *,
    status_code: int,
    code: str,
    category: str,
    message: str,
    retryable: bool = False,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=RuntimeDatabaseErrorDetail(
            code=code,
            category=category,
            message=message,
            retryable=retryable,
        ).model_dump(include={"code", "category", "message", "retryable"}),
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


async def _broker_query(
    *,
    user_id: str,
    session_id: str,
    handle: str,
    sql: str,
    params: list[Any] | dict[str, Any] | None,
    limit: int | None = None,
) -> RuntimeDatabaseQueryResponse:
    return await _BROKER.query_async(
        user_id=user_id,
        session_id=session_id,
        handle=handle,
        sql=sql,
        params=params,
        limit=limit,
        sandbox_mode=_FRONTEND_SANDBOX_MODE,
    )


@router.get("/handles", response_model=RuntimeDatabaseHandlesResponse)
async def list_runtime_database_handles(
    session_id: str = Query(..., min_length=1, description="目标会话 ID"),
    current_user: UserInfo = Depends(require_auth()),
):
    try:
        return _BROKER.list_handles(
            user_id=current_user.user_id,
            session_id=session_id,
            sandbox_mode=_FRONTEND_SANDBOX_MODE,
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
async def query_runtime_database(
    payload: SessionRuntimeDatabaseQueryRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    try:
        return await _broker_query(
            user_id=current_user.user_id,
            session_id=payload.session_id,
            handle=payload.handle,
            sql=payload.sql,
            params=payload.params,
            limit=payload.limit,
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
async def execute_runtime_database(
    payload: SessionRuntimeDatabaseExecuteRequest,
    current_user: UserInfo = Depends(require_auth()),
):
    try:
        return await _BROKER.execute(
            user_id=current_user.user_id,
            session_id=payload.session_id,
            handle=payload.handle,
            sql=payload.sql,
            params=payload.params,
            sandbox_mode=_FRONTEND_SANDBOX_MODE,
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
async def list_runtime_database_tables(
    session_id: str = Query(..., min_length=1, description="目标会话 ID"),
    handle: str = Query("", description="数据库资源句柄"),
    current_user: UserInfo = Depends(require_auth()),
):
    try:
        return await _BROKER.list_tables_async(
            user_id=current_user.user_id,
            session_id=session_id,
            handle=handle,
            sandbox_mode=_FRONTEND_SANDBOX_MODE,
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
async def describe_runtime_database_table(
    table_name: str,
    session_id: str = Query(..., min_length=1, description="目标会话 ID"),
    handle: str = Query("", description="数据库资源句柄"),
    current_user: UserInfo = Depends(require_auth()),
):
    try:
        return await _BROKER.describe_table_async(
            user_id=current_user.user_id,
            session_id=session_id,
            handle=handle,
            table_name=table_name,
            sandbox_mode=_FRONTEND_SANDBOX_MODE,
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
