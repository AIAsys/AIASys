from __future__ import annotations

from pathlib import Path

from app.services.connector import DatabaseConnectorService
from app.services.session import SessionManager


class _KeywordOnlyAdapter:
    def is_driver_available(self) -> bool:
        return True

    def test_connection(self, *, connection_mode: str, payload: dict[str, object]) -> None:
        assert connection_mode == "fields"
        assert payload == {"host": "127.0.0.1"}

    def query(self, **_: object):
        raise NotImplementedError

    def execute(self, **_: object):
        raise NotImplementedError

    def list_tables(self, **_: object):
        raise NotImplementedError

    def describe_table(self, **_: object):
        raise NotImplementedError

    def build_list_tables_query(self):
        raise NotImplementedError

    def build_describe_table_query(self, **_: object):
        raise NotImplementedError


def test_database_connector_service_invokes_test_connection_with_keywords(
    tmp_path: Path,
) -> None:
    service = DatabaseConnectorService(tmp_path, session_manager=SessionManager(tmp_path))
    service._connector_adapters["postgres"] = _KeywordOnlyAdapter()  # type: ignore[assignment]

    result = service._run_connection_test(
        "postgres",
        "fields",
        {"host": "127.0.0.1"},
    )

    assert result.success is True
