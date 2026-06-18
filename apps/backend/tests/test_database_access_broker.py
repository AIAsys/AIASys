from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.models.database_access import (
    RuntimeDatabaseDescribeTableResponse,
    RuntimeDatabaseHandlesResponse,
    RuntimeDatabaseListTablesResponse,
)
from app.models.database_connector import (
    DatabaseConnector,
    DatabaseDescribeTableResponse,
    DatabaseListTablesResponse,
    DatabaseTableInfo,
    ReadonlyDatabaseQueryResponse,
    SessionDatabaseAttachment,
)
from app.services.database import database_access_broker as broker_module
from app.services.database import (
    DatabaseAccessBroker,
    build_runtime_database_helper_env,
    create_runtime_database_token,
    decode_runtime_database_token,
    get_default_runtime_database_broker_url_for_local,
)
from app.services.connector import (
    DatabaseConnectorApprovalRejectedError,
    DatabaseConnectorRemotePermissionError,
)
from app.services.session import SessionManager


class _FakeAccess:
    def __init__(self, connection: "_FakeConnection") -> None:
        self._connection = connection

    def connect(self) -> "_FakeConnection":
        return self._connection


class _FakeCursor:
    def __init__(
        self,
        *,
        rows: list[tuple[object, ...]] | None = None,
        description: list[tuple[object, ...]] | None = None,
        rowcount: int = 0,
    ) -> None:
        self.rows = rows or []
        self.description = description or []
        self.rowcount = rowcount
        self.executed: list[tuple[str, object]] = []

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, params))

    def fetchmany(self, size: int) -> list[tuple[object, ...]]:
        return self.rows[:size]

    def fetchall(self) -> list[tuple[object, ...]]:
        return list(self.rows)

    def close(self) -> None:
        return None


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor
        self.began = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, sql: str, params=None):
        if sql == "BEGIN TRANSACTION":
            self.began = True
            return self._cursor
        if sql == "COMMIT":
            self.committed = True
            return self._cursor
        if sql == "ROLLBACK":
            self.rolled_back = True
            return self._cursor
        self._cursor.execute(sql, params)
        return self._cursor

    def close(self) -> None:
        self.closed = True


def _build_broker(tmp_path: Path) -> DatabaseAccessBroker:
    session_manager = SessionManager(tmp_path)
    session_manager.create_session(
        session_id="session-1",
        user_id="demo-user",
        title="broker",
    )
    return DatabaseAccessBroker(tmp_path, session_manager=session_manager)


def test_database_access_broker_can_create_default_session_manager(
    tmp_path: Path,
) -> None:
    broker = DatabaseAccessBroker(tmp_path)

    assert isinstance(broker.session_manager, SessionManager)


def test_runtime_database_token_roundtrip() -> None:
    token = create_runtime_database_token(
        user_id="demo-user",
        session_id="session-1",
        sandbox_mode="local",
    )
    context = decode_runtime_database_token(token)
    assert context is not None
    assert context.user_id == "demo-user"
    assert context.session_id == "session-1"
    assert context.sandbox_mode == "local"


def test_build_runtime_database_helper_env_contains_broker_fields() -> None:
    env = build_runtime_database_helper_env(
        user_id="demo-user",
        session_id="session-1",
        sandbox_mode="docker",
        backend_base_url="http://127.0.0.1:13001",
    )
    assert env["AIASYS_DB_BROKER_URL"] == "http://127.0.0.1:13001/api/session-database"
    assert env["AIASYS_DB_DEFAULT_HANDLE"] == ""
    assert decode_runtime_database_token(env["AIASYS_DB_SESSION_TOKEN"]) is not None


def test_get_default_runtime_database_broker_url_for_local_prefers_env_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "AIASYS_BACKEND_BASE_URL",
        "http://127.0.0.1:13201/",
    )

    assert get_default_runtime_database_broker_url_for_local() == "http://127.0.0.1:13201"


def test_connector_credentials_path_uses_runtime_data_dir() -> None:
    path = broker_module.get_connector_credentials_path("session-1")

    assert path == broker_module.DATA_DIR / "runtime" / "connectors" / "session-1.json"
    assert path.is_absolute()
    assert "/tmp/aiasys/connectors" not in path.as_posix()


def test_query_connector_handle_requires_non_empty_connector_id(
    tmp_path: Path,
) -> None:
    broker = _build_broker(tmp_path)

    with pytest.raises(ValueError, match="数据库连接器句柄缺少 connector_id"):
        broker.query(
            user_id="demo-user",
            session_id="session-1",
            handle="connector:",
            sql="SELECT 1",
            params=[],
            limit=5,
        )


def test_query_external_connector_remote_permission_denial_emits_rejected_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = _build_broker(tmp_path)

    def fake_query(**kwargs):
        raise DatabaseConnectorRemotePermissionError(
            "目标数据库账号权限不足，远端数据库拒绝了本次查询: permission denied for table orders"
        )

    monkeypatch.setattr(
        broker.connector_service,
        "query_attached_connector_readonly",
        fake_query,
    )

    with caplog.at_level(logging.WARNING, logger=broker_module.logger.name):
        with pytest.raises(DatabaseConnectorRemotePermissionError, match="权限不足"):
            broker.query(
                user_id="demo-user",
                session_id="session-1",
                handle="connector:dbc_1",
                sql="SELECT * FROM orders",
                params=[],
                limit=20,
                sandbox_mode="docker",
            )

    messages = [record.getMessage() for record in caplog.records]
    assert any("runtime_db_audit outcome=rejected action=query" in msg for msg in messages)
    assert any("rejection_reason=remote_permission_denied" in msg for msg in messages)
    assert any("connector_id=dbc_1" in msg for msg in messages)
