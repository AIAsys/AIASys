from __future__ import annotations

import asyncio

import pytest

from app.api.routes import runtime_database as route_module
from app.models.user import UserInfo
from app.services.connector import (
    DatabaseConnectorApprovalTimeoutError,
    DatabaseConnectorAttachmentMissingError,
)


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


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
                    "handle": "builtin_db",
                    "connector_id": "builtin_db",
                    "name": "平台内置 DuckDB",
                    "db_type": "duckdb",
                    "grants": ["schema_read", "data_read", "data_write", "ddl"],
                    "capability_upper_bound": [
                        "schema_read",
                        "data_read",
                        "data_write",
                        "ddl",
                    ],
                    "approval_policy": "none",
                    "attached_at": "",
                }
            ],
        }

    def query(self, **kwargs):
        self.query_calls.append(kwargs)
        return {
            "handle": kwargs["handle"],
            "grants": ["schema_read", "data_read"],
            "capability_upper_bound": ["schema_read", "data_read"],
            "grant_used": "data_read",
            "approval_policy": "none",
            "audit_id": "dbq_123",
            "duration_ms": 6,
            "columns": ["id"],
            "rows": [[1]],
            "row_count": 1,
            "truncated": False,
            "applied_limit": kwargs.get("limit"),
        }

    async def execute(self, **kwargs):
        self.execute_calls.append(kwargs)
        return {
            "handle": kwargs["handle"],
            "grants": ["schema_read", "data_read", "data_write", "ddl"],
            "capability_upper_bound": ["schema_read", "data_read", "data_write", "ddl"],
            "grant_used": "ddl",
            "approval_policy": "none",
            "audit_id": "dbe_123",
            "duration_ms": 9,
            "affected_rows": 0,
            "message": "ok",
        }


class _AttachmentMissingBroker(_FakeBroker):
    def query(self, **kwargs):
        raise DatabaseConnectorAttachmentMissingError("会话未挂载该数据库连接器")


class _ApprovalTimeoutBroker(_FakeBroker):
    async def execute(self, **kwargs):
        raise DatabaseConnectorApprovalTimeoutError("数据库写入审批等待超时，请重新发起执行")


def _patch_broker(monkeypatch, broker) -> None:
    monkeypatch.setattr(route_module, "_BROKER", broker)


def test_runtime_database_handles_use_authenticated_user(monkeypatch) -> None:
    broker = _FakeBroker()
    _patch_broker(monkeypatch, broker)

    response = asyncio.run(
        route_module.list_runtime_database_handles(
            session_id="session-1",
            current_user=_build_user(),
        )
    )

    assert response["session_id"] == "session-1"
    assert broker.list_handles_calls == [
        {
            "user_id": "local_default",
            "session_id": "session-1",
            "sandbox_mode": "analysis_ui",
        }
    ]


def test_runtime_database_query_uses_authenticated_session_scope(monkeypatch) -> None:
    broker = _FakeBroker()
    _patch_broker(monkeypatch, broker)

    response = asyncio.run(
        route_module.query_runtime_database(
            route_module.SessionRuntimeDatabaseQueryRequest(
                session_id="session-1",
                handle="builtin_db",
                sql="SELECT 1",
                params=[],
                limit=20,
            ),
            current_user=_build_user(),
        )
    )

    assert response["handle"] == "builtin_db"
    assert broker.query_calls == [
        {
            "user_id": "local_default",
            "session_id": "session-1",
            "handle": "builtin_db",
            "sql": "SELECT 1",
            "params": [],
            "limit": 20,
            "sandbox_mode": "analysis_ui",
        }
    ]


def test_runtime_database_query_maps_attachment_missing_to_structured_error(
    monkeypatch,
) -> None:
    _patch_broker(monkeypatch, _AttachmentMissingBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.query_runtime_database(
                route_module.SessionRuntimeDatabaseQueryRequest(
                    session_id="session-1",
                    handle="connector:dbc_1",
                    sql="SELECT 1",
                    params=[],
                    limit=10,
                ),
                current_user=_build_user(),
            )
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == {
        "code": "session_connector_not_attached",
        "category": "session",
        "message": "会话未挂载该数据库连接器",
        "retryable": False,
    }


def test_runtime_database_execute_maps_approval_timeout(monkeypatch) -> None:
    _patch_broker(monkeypatch, _ApprovalTimeoutBroker())

    with pytest.raises(route_module.HTTPException) as exc_info:
        asyncio.run(
            route_module.execute_runtime_database(
                route_module.SessionRuntimeDatabaseExecuteRequest(
                    session_id="session-1",
                    handle="connector:dbc_1",
                    sql="DELETE FROM orders WHERE id = 1",
                    params=[],
                ),
                current_user=_build_user(),
            )
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == {
        "code": "approval_timeout",
        "category": "approval",
        "message": "数据库写入审批等待超时，请重新发起执行",
        "retryable": False,
    }
