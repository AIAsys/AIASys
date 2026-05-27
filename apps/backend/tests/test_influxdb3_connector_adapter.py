from __future__ import annotations

import json

import pytest

from app.services.database.adapters import influxdb3 as influxdb3_module
from app.services.database.adapters.influxdb3 import InfluxDb3ConnectorAdapter


class _FakeResponse:
    def __init__(self, body: str) -> None:
        self._body = body.encode("utf-8")

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def test_influxdb3_adapter_query_uses_http_api(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = InfluxDb3ConnectorAdapter()
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout: int):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(req.header_items())
        captured["body"] = json.loads(req.data.decode("utf-8"))
        return _FakeResponse(
            json.dumps(
                [
                    {"time": "2026-03-22T00:00:00Z", "host": "edge-1"},
                    {"time": "2026-03-22T00:01:00Z", "host": "edge-2"},
                ]
            )
        )

    monkeypatch.setattr(influxdb3_module.request, "urlopen", fake_urlopen)

    columns, rows = adapter.query(
        connection_mode="fields",
        payload={
            "host": "metrics.internal",
            "port": 8181,
            "database_name": "telemetry",
            "api_token": "token-123",
        },
        sql="SELECT time, host FROM cpu",
        params=[],
        limit=10,
        timeout_seconds=7,
    )

    assert columns == ["time", "host"]
    assert rows == [
        ("2026-03-22T00:00:00Z", "edge-1"),
        ("2026-03-22T00:01:00Z", "edge-2"),
    ]
    assert captured["url"] == "http://metrics.internal:8181/api/v3/query_sql"
    assert captured["timeout"] == 7
    assert captured["headers"] == {
        "Accept": "application/json",
        "Authorization": "Bearer token-123",
        "Content-type": "application/json",
    }
    assert captured["body"] == {
        "db": "telemetry",
        "q": "SELECT time, host FROM cpu",
        "format": "json",
    }


def test_influxdb3_adapter_query_supports_connection_url_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = InfluxDb3ConnectorAdapter()
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout: int):
        captured["url"] = req.full_url
        return _FakeResponse("[]")

    monkeypatch.setattr(influxdb3_module.request, "urlopen", fake_urlopen)

    columns, rows = adapter.query(
        connection_mode="url",
        payload={
            "connection_url": "https://metrics.example.com/base",
            "database_name": "telemetry",
            "api_token": "token-123",
        },
        sql="SELECT 1",
        params=[],
        limit=5,
        timeout_seconds=3,
    )

    assert columns == []
    assert rows == []
    assert captured["url"] == "https://metrics.example.com/base/api/v3/query_sql"


def test_influxdb3_adapter_build_describe_query_stabilizes_column_default_alias() -> None:
    adapter = InfluxDb3ConnectorAdapter()

    sql, params, limit = adapter.build_describe_table_query(
        schema_name="iox",
        table_name="cpu",
    )

    assert "NULL AS column_default" in sql
    assert "table_schema = 'iox'" in sql
    assert "table_name = 'cpu'" in sql
    assert params == []
    assert limit == 2000


def test_influxdb3_adapter_query_keeps_sparse_columns_from_later_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = InfluxDb3ConnectorAdapter()

    def fake_urlopen(req, timeout: int):
        return _FakeResponse(
            json.dumps(
                [
                    {"host": "edge-1"},
                    {"host": "edge-2", "usage": 0.91},
                ]
            )
        )

    monkeypatch.setattr(influxdb3_module.request, "urlopen", fake_urlopen)

    columns, rows = adapter.query(
        connection_mode="fields",
        payload={
            "host": "metrics.internal",
            "port": 8181,
            "database_name": "telemetry",
            "api_token": "token-123",
        },
        sql="SELECT host, usage FROM cpu",
        params=[],
        limit=10,
        timeout_seconds=7,
    )

    assert columns == ["host", "usage"]
    assert rows == [
        ("edge-1", None),
        ("edge-2", 0.91),
    ]


def test_influxdb3_adapter_rejects_positional_params() -> None:
    adapter = InfluxDb3ConnectorAdapter()

    with pytest.raises(ValueError, match="暂不支持位置参数"):
        adapter.query(
            connection_mode="fields",
            payload={
                "host": "metrics.internal",
                "port": 8181,
                "database_name": "telemetry",
                "api_token": "token-123",
            },
            sql="SELECT * FROM cpu WHERE host = $host",
            params=["edge-1"],
            limit=10,
            timeout_seconds=5,
        )
