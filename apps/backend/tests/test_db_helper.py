from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from agent_runtime_helpers.db_helper import (
    RuntimeDatabaseClient,
    RuntimeDatabaseHelperError,
    get_db,
)


def test_get_db_requires_broker_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIASYS_DB_BROKER_URL", raising=False)
    monkeypatch.setenv("AIASYS_DB_SESSION_TOKEN", "demo-token")
    with pytest.raises(RuntimeDatabaseHelperError, match="缺少 AIASYS_DB_BROKER_URL"):
        get_db()


def test_get_db_requires_session_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIASYS_DB_BROKER_URL", "http://127.0.0.1:13001/api/session-database")
    monkeypatch.delenv("AIASYS_DB_SESSION_TOKEN", raising=False)
    with pytest.raises(RuntimeDatabaseHelperError, match="缺少 AIASYS_DB_SESSION_TOKEN"):
        get_db()


def test_get_db_returns_client_with_env_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIASYS_DB_BROKER_URL", "http://127.0.0.1:13001/api/session-database")
    monkeypatch.setenv("AIASYS_DB_SESSION_TOKEN", "demo-token")
    monkeypatch.setenv("AIASYS_DB_DEFAULT_HANDLE", "connector:dbc_default")

    client = get_db()
    assert client.base_url == "http://127.0.0.1:13001/api/session-database"
    assert client.session_token == "demo-token"
    assert client.default_handle == "connector:dbc_default"


def test_get_db_uses_builtin_db_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AIASYS_DB_BROKER_URL", "http://127.0.0.1:13001/api/session-database")
    monkeypatch.setenv("AIASYS_DB_SESSION_TOKEN", "demo-token")
    monkeypatch.delenv("AIASYS_DB_DEFAULT_HANDLE", raising=False)

    client = get_db()
    assert client.default_handle == ""


def test_client_list_handles_makes_get_request() -> None:
    client = RuntimeDatabaseClient(
        base_url="http://127.0.0.1:13001/api/session-database",
        session_token="demo-token",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        return FakeResponse(
            json.dumps(
                {
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
                            "attached_at": "2026-03-21T08:00:00Z",
                        }
                    ],
                }
            ).encode("utf-8")
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.list_handles()

    assert captured["method"] == "GET"
    assert captured["url"] == "http://127.0.0.1:13001/api/session-database/handles"
    assert result == {
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
                "attached_at": "2026-03-21T08:00:00Z",
            }
        ],
    }


def test_client_list_tables_uses_default_handle() -> None:
    client = RuntimeDatabaseClient(
        base_url="http://127.0.0.1:13001/api/session-database",
        session_token="demo-token",
        default_handle="connector:dbc_default",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        return FakeResponse(json.dumps({"tables": ["public.orders"]}).encode("utf-8"))

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.list_tables()

    assert captured["method"] == "GET"
    assert captured["url"] == (
        "http://127.0.0.1:13001/api/session-database/tables?handle=connector%3Adbc_default"
    )
    assert result == {"tables": ["public.orders"]}


def test_client_describe_table_uses_handle_override() -> None:
    client = RuntimeDatabaseClient(
        base_url="http://127.0.0.1:13001/api/session-database",
        session_token="demo-token",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        return FakeResponse(
            json.dumps(
                {
                    "columns": [
                        {"name": "id", "type": "integer", "nullable": False, "default": None},
                        {"name": "name", "type": "text", "nullable": True, "default": None},
                    ]
                }
            ).encode("utf-8")
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.describe_table("users", handle="connector:dbc_1")

    assert captured["method"] == "GET"
    assert captured["url"] == (
        "http://127.0.0.1:13001/api/session-database/tables/users?handle=connector%3Adbc_1"
    )
    assert result == {
        "columns": [
            {"name": "id", "type": "integer", "nullable": False, "default": None},
            {"name": "name", "type": "text", "nullable": True, "default": None},
        ]
    }


def test_client_query_posts_payload() -> None:
    client = RuntimeDatabaseClient(
        base_url="http://127.0.0.1:13001/api/session-database",
        session_token="demo-token",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["body"] = request.data
        return FakeResponse(
            json.dumps(
                {
                    "columns": ["id", "name"],
                    "rows": [[1, "alice"]],
                }
            ).encode("utf-8")
        )

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.query(
            "SELECT id, name FROM users WHERE id = %s",
            handle="connector:dbc_1",
            limit=50,
        )

    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:13001/api/session-database/query"
    body = json.loads(captured["body"])
    assert body == {
        "handle": "connector:dbc_1",
        "sql": "SELECT id, name FROM users WHERE id = %s",
        "limit": 50,
    }
    assert result == {
        "columns": ["id", "name"],
        "rows": [[1, "alice"]],
    }


def test_client_execute_posts_payload() -> None:
    client = RuntimeDatabaseClient(
        base_url="http://127.0.0.1:13001/api/session-database",
        session_token="demo-token",
    )

    captured: dict[str, object] = {}

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data

        def read(self) -> bytes:
            return self._data

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def fake_urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured["method"] = request.method
        captured["body"] = request.data
        return FakeResponse(json.dumps({"affected_rows": 1}).encode("utf-8"))

    with patch("urllib.request.urlopen", fake_urlopen):
        result = client.execute("DELETE FROM orders WHERE id = %s", handle="connector:dbc_1")

    assert captured["method"] == "POST"
    assert captured["url"] == "http://127.0.0.1:13001/api/session-database/execute"
    body = json.loads(captured["body"])
    assert body == {
        "handle": "connector:dbc_1",
        "sql": "DELETE FROM orders WHERE id = %s",
    }
    assert result == {"affected_rows": 1}


def test_client_raises_on_http_error() -> None:
    client = RuntimeDatabaseClient(
        base_url="http://127.0.0.1:13001/api/session-database",
        session_token="demo-token",
    )

    class FakeHTTPError(Exception):
        def __init__(self, url, code, msg, hdrs, fp):
            self.code = code
            self.reason = msg
            self.read = lambda: json.dumps(
                {
                    "detail": {
                        "code": "session_connector_not_attached",
                        "category": "session",
                        "message": "会话未挂载该数据库连接器",
                    }
                }
            ).encode("utf-8")

    import urllib.error

    original = urllib.error.HTTPError
    urllib.error.HTTPError = FakeHTTPError

    def fake_urlopen(request, **kwargs):
        raise FakeHTTPError(request.full_url, 403, "Forbidden", {}, None)

    try:
        with patch("urllib.request.urlopen", fake_urlopen):
            with pytest.raises(RuntimeDatabaseHelperError, match="数据库 broker 请求失败"):
                client.query("SELECT 1", handle="connector:dbc_1")
    finally:
        urllib.error.HTTPError = original
