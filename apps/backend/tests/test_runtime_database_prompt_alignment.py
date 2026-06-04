from pathlib import Path

from app.services.runtime.execution_support import build_local_runtime_bootstrap_code


def test_runtime_bootstrap_code_preloads_database_helper() -> None:
    code = build_local_runtime_bootstrap_code(
        {
            "AIASYS_DB_BROKER_URL": "http://127.0.0.1:13001/api/session-database",
            "AIASYS_DB_SESSION_TOKEN": "test-token",
            "AIASYS_DB_DEFAULT_HANDLE": "builtin_db",
        }
    )

    assert "from db_helper import get_db" in code
    assert "db = get_db()" in code
    assert 'AIASYS_DB_BROKER_URL' in code
    assert 'AIASYS_DB_SESSION_TOKEN' in code
    assert 'AIASYS_DB_DEFAULT_HANDLE' in code


def test_general_host_prompt_documents_runtime_db_helper_instead_of_legacy_dsn() -> None:
    prompt_path = Path(__file__).resolve().parents[1] / "app" / "agents" / "local_sandbox_agent_config" / "general_host_prompt.md"
    prompt = prompt_path.read_text(encoding="utf-8")

    assert "db = get_db()" in prompt
    assert "db.list_handles()" in prompt
    assert "connector:<connector_id>" in prompt
    assert "`DB_DSN` - " not in prompt
    assert "`DB_NAME` - " not in prompt
    assert "os.environ.get('DB_DSN')" not in prompt
    assert "os.environ.get('DB_NAME')" not in prompt
    assert "psycopg2.connect(dsn)" not in prompt
    assert "create_engine(dsn)" not in prompt
    assert "df.to_sql(" not in prompt
