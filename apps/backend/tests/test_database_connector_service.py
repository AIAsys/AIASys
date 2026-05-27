from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.agents.tools.ask_user.models import AskUserResponse, AskUserStore
from app.agents.tools.ask_user.tool import AskUser
from app.models.database_connector import (
    DatabaseConnectorDraft,
    UpdateDatabaseConnectorRequest,
)
from app.services.connector import (
    DatabaseConnectorApprovalRejectedError,
    DatabaseConnectorPlatformRejectionError,
    DatabaseConnectorRemotePermissionError,
    DatabaseConnectorService,
)
from app.services.session import SessionManager


def _get_connector_from_db(user_id: str, connector_id: str | None = None):
    """从 DuckDB 查询连接器记录（替代直接读取 JSON 文件）"""
    from app.core.database import SessionLocal, DatabaseConnectorORM
    db = SessionLocal()
    try:
        q = db.query(DatabaseConnectorORM).filter_by(user_id=user_id)
        if connector_id:
            q = q.filter_by(connector_id=connector_id)
        return q.first()
    finally:
        db.close()


def _get_attachments_from_db(session_id: str, connector_id: str | None = None):
    """从 DuckDB 查询会话挂载记录（替代直接读取 JSON 文件）"""
    from app.core.database import SessionLocal, SessionAttachmentORM
    db = SessionLocal()
    try:
        q = db.query(SessionAttachmentORM).filter_by(session_id=session_id)
        if connector_id:
            q = q.filter_by(connector_id=connector_id)
        return q.all()
    finally:
        db.close()


def test_create_connector_encrypts_secret_and_masks_response(tmp_path: Path) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))

    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="生产 PG",
            db_type="postgres",
            host="db.example.com",
            database_name="analytics",
            username="analyst",
            password="super-secret-password",
            allowed_schemas=["public", "public"],
        ),
    )

    assert connector.connector_id.startswith("dbc_")
    assert connector.has_password is True
    assert connector.password_masked is not None
    assert "super-secret-password" not in connector.password_masked
    assert connector.allowed_schemas == ["public"]

    saved_record = _get_connector_from_db("db-user", connector.connector_id)
    assert saved_record is not None
    assert saved_record.password_encrypted != "super-secret-password"
    assert "super-secret-password" not in (saved_record.password_encrypted or "")


def test_update_connector_reencrypts_secret_and_resets_test_status(tmp_path: Path) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))
    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="报表库",
            db_type="postgres",
            host="localhost",
            database_name="reporting",
            username="readonly",
            password="old-password",
        ),
    )

    updated = service.update_connector(
        "db-user",
        connector.connector_id,
        UpdateDatabaseConnectorRequest(
            host="pg.internal",
            password="new-password",
            allowed_tables=["public.orders", "public.customers"],
        ),
    )

    assert updated is not None
    assert updated.host == "pg.internal"
    assert updated.last_test_status == "untested"
    assert updated.allowed_tables == ["public.orders", "public.customers"]

    saved_record = _get_connector_from_db("db-user", connector.connector_id)
    assert saved_record is not None
    assert "new-password" not in (saved_record.password_encrypted or "")


def test_attach_and_detach_connector_for_session(tmp_path: Path) -> None:
    from uuid import uuid4
    session_manager = SessionManager(tmp_path)
    service = DatabaseConnectorService(tmp_path, session_manager=session_manager)
    session_id = f"session-{uuid4().hex[:8]}"
    session_manager.create_session(
        session_id=session_id,
        user_id="db-user",
        title="DB Attach Test",
    )
    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="会话 PG",
            db_type="postgres",
            host="localhost",
            database_name="analytics",
            username="readonly",
            password="pass",
        ),
    )

    attached = service.attach_connector("db-user", session_id, connector.connector_id)
    listed = service.list_session_attachments("db-user", session_id)

    assert attached.connector_id == connector.connector_id
    assert attached.handle == f"connector:{connector.connector_id}"
    assert len(listed) == 1
    assert listed[0].name == "会话 PG"
    assert listed[0].handle == f"connector:{connector.connector_id}"

    db_attachments = _get_attachments_from_db(session_id)
    assert len(db_attachments) == 1
    assert db_attachments[0].connector_id == connector.connector_id
    assert db_attachments[0].handle == f"connector:{connector.connector_id}"

    assert service.detach_connector("db-user", session_id, connector.connector_id) is True
    assert service.list_session_attachments("db-user", session_id) == []


def test_test_connector_draft_uses_postgres_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))
    captured: dict[str, str] = {}

    def fake_test(connection_mode: str, payload: dict[str, object]) -> None:
        captured["connection_mode"] = connection_mode
        captured["host"] = str(payload["host"])
        captured["database_name"] = str(payload["database_name"])

    monkeypatch.setattr(service, "_test_postgres_connection", fake_test)

    result = service.test_connector_draft(
        DatabaseConnectorDraft(
            name="测试 PG",
            db_type="postgres",
            host="127.0.0.1",
            database_name="demo",
            username="readonly",
            password="pass",
        )
    )

    assert result.success is True
    assert captured == {
        "connection_mode": "fields",
        "host": "127.0.0.1",
        "database_name": "demo",
    }


def test_mysql_capability_reports_missing_driver_when_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))
    monkeypatch.setattr(service, "_is_mysql_driver_available", lambda: False)

    capabilities = service.list_capabilities()
    mysql_capability = next(item for item in capabilities if item.db_type == "mysql")

    assert mysql_capability.driver_available is False
    assert mysql_capability.note is not None


def test_influxdb3_capability_reports_timeseries_query_only(tmp_path: Path) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))

    capabilities = service.list_capabilities()
    influx_capability = next(item for item in capabilities if item.db_type == "influxdb3")

    assert influx_capability.connector_family == "timeseries"
    assert influx_capability.readonly_enforced is True
    assert influx_capability.driver_available is True
    assert influx_capability.driver_name == "http-api"


def test_list_session_attachments_persists_to_duckdb(tmp_path: Path) -> None:
    from uuid import uuid4
    session_manager = SessionManager(tmp_path)
    service = DatabaseConnectorService(tmp_path, session_manager=session_manager)
    session_id = f"session-{uuid4().hex[:8]}"
    session_manager.create_session(
        session_id=session_id,
        user_id="db-user",
        title="DuckDB Attach Test",
    )
    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="测试 PG",
            db_type="postgres",
            host="localhost",
            database_name="analytics",
            username="readonly",
            password="pass",
        ),
    )

    service.attach_connector("db-user", session_id, connector.connector_id)
    attachments = service.list_session_attachments("db-user", session_id)

    assert len(attachments) == 1
    assert attachments[0].handle == f"connector:{connector.connector_id}"

    db_attachments = _get_attachments_from_db(session_id)
    assert len(db_attachments) == 1
    assert db_attachments[0].handle == f"connector:{connector.connector_id}"


def test_query_attached_connector_readonly_executes_postgres_with_guardrails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_manager = SessionManager(tmp_path)
    service = DatabaseConnectorService(tmp_path, session_manager=session_manager)
    session_manager.create_session(
        session_id="session-1",
        user_id="db-user",
        title="Query Test",
    )
    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="只读 PG",
            db_type="postgres",
            host="localhost",
            database_name="analytics",
            username="readonly",
            password="pass",
            row_limit=50,
            query_timeout_seconds=8,
        ),
    )
    service.attach_connector("db-user", "session-1", connector.connector_id)

    captured: dict[str, object] = {}

    def fake_query_postgres(
        *,
        connection_mode: str,
        payload: dict[str, object],
        sql: str,
        params: list[object],
        limit: int,
        timeout_seconds: int,
    ) -> tuple[list[str], list[tuple[object, ...]]]:
        captured["connection_mode"] = connection_mode
        captured["sql"] = sql
        captured["params"] = params
        captured["limit"] = limit
        captured["timeout_seconds"] = timeout_seconds
        captured["db_name"] = payload["database_name"]
        return ["id", "name"], [(1, "alice"), (2, "bob"), (3, "carol")]

    monkeypatch.setattr(service, "_query_postgres", fake_query_postgres)

    result = service.query_attached_connector_readonly(
        user_id="db-user",
        session_id="session-1",
        connector_id=connector.connector_id,
        sql="SELECT id, name FROM users",
        params=[],
        limit=2,
    )

    assert result.columns == ["id", "name"]
    assert result.handle == f"connector:{connector.connector_id}"
    assert result.audit_id.startswith("dba_")
    assert result.row_count == 2
    assert result.truncated is True
    assert result.applied_limit == 2
    assert result.rows == [[1, "alice"], [2, "bob"]]
    assert captured == {
        "connection_mode": "fields",
        "sql": "SELECT id, name FROM users",
        "params": [],
        "limit": 2,
        "timeout_seconds": 8,
        "db_name": "analytics",
    }


def test_query_attached_connector_readonly_allows_writable_connector_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_manager = SessionManager(tmp_path)
    service = DatabaseConnectorService(tmp_path, session_manager=session_manager)
    session_manager.create_session(
        session_id="session-1",
        user_id="db-user",
        title="Writable Query Test",
    )
    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="可写 PG",
            db_type="postgres",
            host="localhost",
            database_name="analytics",
            username="writer",
            password="pass",
        ),
    )
    service.attach_connector("db-user", "session-1", connector.connector_id)

    monkeypatch.setattr(
        service,
        "_query_postgres",
        lambda **kwargs: (["id"], [(1,), (2,)]),
    )

    result = service.query_attached_connector_readonly(
        user_id="db-user",
        session_id="session-1",
        connector_id=connector.connector_id,
        sql="SELECT id FROM smoke_customers ORDER BY id",
        params=[],
        limit=10,
    )

    assert result.rows == [[1], [2]]




def test_create_connector_can_persist_explicit_write_access_policy(tmp_path: Path) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))

    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="写入 PG",
            db_type="postgres",
            host="localhost",
            database_name="analytics",
            username="writer",
            password="pass",
        ),
    )

    pass



def test_create_influxdb3_connector_persists_token_and_family(tmp_path: Path) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))

    connector = service.create_connector(
        "db-user",
        DatabaseConnectorDraft(
            name="时序库",
            db_type="influxdb3",
            host="metrics.internal",
            database_name="telemetry",
            api_token="super-secret-token",
            allowed_schemas=["iox"],
        ),
    )

    assert connector.db_type == "influxdb3"
    assert connector.connector_family == "timeseries"
    assert connector.has_password is False
    assert connector.has_api_token is True
    assert connector.api_token_masked is not None
    assert "super-secret-token" not in connector.api_token_masked

    saved_record = _get_connector_from_db("db-user", connector.connector_id)
    assert saved_record is not None
    assert saved_record.api_token_encrypted != "super-secret-token"
    assert "super-secret-token" not in (saved_record.api_token_encrypted or "")



def test_test_connector_draft_uses_influxdb3_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))
    captured: dict[str, str] = {}

    def fake_test(connection_mode: str, payload: dict[str, object]) -> None:
        captured["connection_mode"] = connection_mode
        captured["host"] = str(payload["host"])
        captured["database_name"] = str(payload["database_name"])
        captured["api_token"] = str(payload["api_token"])

    monkeypatch.setattr(service, "_test_influxdb3_connection", fake_test)

    result = service.test_connector_draft(
        DatabaseConnectorDraft(
            name="测试 Influx",
            db_type="influxdb3",
            host="127.0.0.1",
            database_name="telemetry",
            api_token="token-123",
        )
    )

    assert result.success is True
    assert captured == {
        "connection_mode": "fields",
        "host": "127.0.0.1",
        "database_name": "telemetry",
        "api_token": "token-123",
    }
