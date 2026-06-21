from __future__ import annotations

import asyncio

import pytest

from app.api.routes import session_database as route_module
from app.models.database_access import (
    RuntimeDatabaseExecuteRequest,
    RuntimeDatabaseQueryRequest,
)
from app.services.connector import (
    DatabaseConnectorApprovalRejectedError,
    DatabaseConnectorApprovalTimeoutError,
    DatabaseConnectorAttachmentMissingError,
    DatabaseConnectorGrantDeniedError,
    DatabaseConnectorRemoteExecutionError,
    DatabaseConnectorRemotePermissionError,
)
from app.services.database import create_runtime_database_token


class _Request:
    def __init__(self, token: str | None = None) -> None:
        self.headers = {"authorization": f"Bearer {token}"} if token is not None else {}


class _FakeBroker:
    def __init__(self) -> None:
        self.list_handles_calls: list[dict[str, object]] = []
        self.query_calls: list[dict[str, object]] = []
        self.execute_calls: list[dict[str, object]] = []

    def list_handles(self, **kwargs):
        self.list_handles_calls.append(kwargs)
        return {
            "session_id": kwargs["session_id"],
            "handles": [
                {
                    "handle": "connector:dbc_1",
                    "connector_id": "dbc_1",
                    "name": "订单库",
                    "db_type": "postgres",
                    "grants": ["schema_read", "data_read"],
                    "capability_upper_bound": ["schema_read", "data_read"],
                    "approval_policy": "none",
                    "attached_at": "2026-03-21T08:00:00+00:00",
                }
            ],
        }

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "handle": kwargs["handle"],
            "columns": ["id"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "applied_limit": kwargs.get("limit"),
        }

    async def query_async(self, **kwargs):
        return self.query(**kwargs)

    async def execute(self, **kwargs):
        self.execute_calls.append(kwargs)
        return {
            "handle": kwargs["handle"],
            "grants": ["schema_read", "data_read", "data_write", "ddl"],
            "capability_upper_bound": ["schema_read", "data_read", "data_write", "ddl"],
            "grant_used": "data_write",
            "approval_policy": "none",
            "audit_id": "dba_exec",
            "duration_ms": 8,
            "affected_rows": 1,
            "message": "ok",
        }


class _GrantDeniedBroker(_FakeBroker):
    async def query_async(self, **kwargs):
        raise DatabaseConnectorGrantDeniedError("当前会话未获授权执行动作: data_read")


class _AttachmentMissingBroker(_FakeBroker):
    async def query_async(self, **kwargs):
        raise DatabaseConnectorAttachmentMissingError("会话未挂载该数据库连接器")


class _InvalidHandleBroker(_FakeBroker):
    async def query_async(self, **kwargs):
        raise ValueError("数据库连接器句柄缺少 connector_id")


class _RemotePermissionBroker(_FakeBroker):
    async def execute(self, **kwargs):
        raise DatabaseConnectorRemotePermissionError(
            "目标数据库账号权限不足，远端数据库拒绝了本次执行: permission denied"
        )


class _ApprovalTimeoutBroker(_FakeBroker):
    async def execute(self, **kwargs):
        raise DatabaseConnectorApprovalTimeoutError("数据库写入审批等待超时，请重新发起执行")


class _ApprovalRejectedBroker(_FakeBroker):
    async def execute(self, **kwargs):
        raise DatabaseConnectorApprovalRejectedError("数据库写入审批已拒绝，请调整 SQL 后重试")


class _RemoteExecutionBroker(_FakeBroker):
    async def execute(self, **kwargs):
        raise DatabaseConnectorRemoteExecutionError(
            "目标数据库执行失败: syntax error at or near 'broken'"
        )


def _build_request(monkeypatch, broker, *, sandbox_mode: str = "docker") -> tuple[_Request, str]:
    monkeypatch.setattr(route_module, "_BROKER", broker)

    token = create_runtime_database_token(
        user_id="demo-user",
        session_id="session-1",
        sandbox_mode=sandbox_mode,
    )
    return _Request(token), token


def test_runtime_database_query_passes_sandbox_mode_to_broker(
    monkeypatch,
) -> None:
    fake_broker = _FakeBroker()
    request, _ = _build_request(monkeypatch, fake_broker)

    response = asyncio.run(
        route_module.runtime_database_query(
            request,
            RuntimeDatabaseQueryRequest(
                handle="connector:dbc_1",
                sql="SELECT 1",
                params=[],
                limit=10,
            ),
        )
    )

    assert response["row_count"] == 1
    assert fake_broker.query_calls == [
        {
            "user_id": "demo-user",
            "session_id": "session-1",
            "handle": "connector:dbc_1",
            "sql": "SELECT 1",
            "params": [],
            "limit": 10,
            "sandbox_mode": "docker",
        }
    ]


def test_runtime_database_list_handles_passes_sandbox_mode_to_broker(
    monkeypatch,
) -> None:
    fake_broker = _FakeBroker()
    request, _ = _build_request(monkeypatch, fake_broker, sandbox_mode="local")

    response = asyncio.run(route_module.runtime_database_list_handles(request))

    assert response == {
        "session_id": "session-1",
        "handles": [
            {
                "handle": "connector:dbc_1",
                "connector_id": "dbc_1",
                "name": "订单库",
                "db_type": "postgres",
                "grants": ["schema_read", "data_read"],
                "capability_upper_bound": ["schema_read", "data_read"],
                "approval_policy": "none",
                "attached_at": "2026-03-21T08:00:00+00:00",
            }
        ],
    }
    assert fake_broker.list_handles_calls == [
        {
            "user_id": "demo-user",
            "session_id": "session-1",
            "sandbox_mode": "local",
        }
    ]


def test_runtime_database_execute_passes_sandbox_mode_to_broker(
    monkeypatch,
) -> None:
    fake_broker = _FakeBroker()
    request, _ = _build_request(monkeypatch, fake_broker)

    response = asyncio.run(
        route_module.runtime_database_execute(
            request,
            RuntimeDatabaseExecuteRequest(
                handle="connector:dbc_1",
                sql="INSERT INTO orders(id) VALUES (1)",
                params=[],
            ),
        )
    )

    assert response["affected_rows"] == 1
    assert fake_broker.execute_calls == [
        {
            "user_id": "demo-user",
            "session_id": "session-1",
            "handle": "connector:dbc_1",
            "sql": "INSERT INTO orders(id) VALUES (1)",
            "params": [],
            "sandbox_mode": "docker",
        }
    ]


def test_runtime_database_query_maps_platform_rejection_to_structured_403(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _GrantDeniedBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_query(
                request,
                RuntimeDatabaseQueryRequest(
                    handle="connector:dbc_1",
                    sql="SELECT 1",
                    params=[],
                    limit=10,
                ),
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "code": "platform_grant_denied",
        "category": "platform",
        "message": "当前会话未获授权执行动作: data_read",
    }


def test_runtime_database_query_maps_not_attached_to_structured_403(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _AttachmentMissingBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_query(
                request,
                RuntimeDatabaseQueryRequest(
                    handle="connector:dbc_1",
                    sql="SELECT 1",
                    params=[],
                    limit=10,
                ),
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "code": "session_connector_not_attached",
        "category": "session",
        "message": "会话未挂载该数据库连接器",
    }


def test_runtime_database_query_maps_empty_connector_handle_to_invalid_handle_400(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _InvalidHandleBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_query(
                request,
                RuntimeDatabaseQueryRequest(
                    handle="connector:",
                    sql="SELECT 1",
                    params=[],
                    limit=10,
                ),
            )
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == {
        "code": "invalid_handle",
        "category": "request",
        "message": "数据库连接器句柄缺少 connector_id",
    }


def test_runtime_database_execute_maps_remote_permission_to_structured_403(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _RemotePermissionBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_execute(
                request,
                RuntimeDatabaseExecuteRequest(
                    handle="connector:dbc_1",
                    sql="DELETE FROM orders WHERE id = 1",
                    params=[],
                ),
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "code": "remote_permission_denied",
        "category": "remote",
        "message": "目标数据库账号权限不足，远端数据库拒绝了本次执行: permission denied",
    }


def test_runtime_database_execute_maps_approval_timeout_to_structured_409(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _ApprovalTimeoutBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_execute(
                request,
                RuntimeDatabaseExecuteRequest(
                    handle="connector:dbc_1",
                    sql="DELETE FROM orders WHERE id = 1",
                    params=[],
                ),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "approval_timeout",
        "category": "approval",
        "message": "数据库写入审批等待超时，请重新发起执行",
    }


def test_runtime_database_execute_maps_approval_rejected_to_structured_403(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _ApprovalRejectedBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_execute(
                request,
                RuntimeDatabaseExecuteRequest(
                    handle="connector:dbc_1",
                    sql="DELETE FROM orders WHERE id = 1",
                    params=[],
                ),
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "code": "approval_rejected",
        "category": "approval",
        "message": "数据库写入审批已拒绝，请调整 SQL 后重试",
    }


def test_runtime_database_execute_maps_remote_execution_to_structured_502(
    monkeypatch,
) -> None:
    request, _ = _build_request(monkeypatch, _RemoteExecutionBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.runtime_database_execute(
                request,
                RuntimeDatabaseExecuteRequest(
                    handle="connector:dbc_1",
                    sql="DELETE broken",
                    params=[],
                ),
            )
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == {
        "code": "remote_execution_error",
        "category": "remote",
        "message": "目标数据库执行失败: syntax error at or near 'broken'",
    }


def test_runtime_database_requires_runtime_token(
    monkeypatch,
) -> None:
    monkeypatch.setattr(route_module, "_BROKER", _FakeBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(route_module.runtime_database_list_handles(_Request()))

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == {
        "code": "missing_runtime_database_token",
        "category": "auth",
        "message": "缺少 runtime database token",
    }
