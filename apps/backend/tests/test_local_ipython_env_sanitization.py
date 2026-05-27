from pathlib import Path

from app.agents.tools.local_ipython_box import (
    LocalIPythonBox,
    build_sanitized_kernel_env,
    normalize_notebook_variable_payload,
    sanitize_notebook_variable_preview,
    should_strip_kernel_env_var,
)
from app.services.history import (
    current_session_id,
    current_session_root,
    current_user_id,
    current_workspace,
)


def test_should_strip_kernel_env_var_for_known_secrets():
    assert should_strip_kernel_env_var("AIASYS_LLM_PROVIDER_KIMI_API_KEY") is True
    assert should_strip_kernel_env_var("AIASYS_EMBEDDING_API_KEY") is True
    assert should_strip_kernel_env_var("OPENAI_API_KEY") is True
    assert should_strip_kernel_env_var("ANY_SERVICE_TOKEN") is True
    assert should_strip_kernel_env_var("DB_PASSWORD") is True


def test_should_strip_kernel_env_var_keeps_non_secret_values():
    assert should_strip_kernel_env_var("PATH") is False
    assert should_strip_kernel_env_var("HOME") is False
    assert should_strip_kernel_env_var("AIASYS_DB_BROKER_URL") is False


def test_build_sanitized_kernel_env_removes_secret_values():
    source_env = {
        "PATH": "/usr/bin",
        "HOME": "/tmp/demo",
        "AIASYS_LLM_PROVIDER_KIMI_API_KEY": "secret-key",
        "AIASYS_EMBEDDING_API_KEY": "embedding-key",
        "AIASYS_DB_BROKER_URL": "http://127.0.0.1:13001",
    }

    sanitized = build_sanitized_kernel_env(source_env)

    assert sanitized["PATH"] == "/usr/bin"
    assert sanitized["HOME"] == "/tmp/demo"
    assert sanitized["AIASYS_DB_BROKER_URL"] == "http://127.0.0.1:13001"
    assert "AIASYS_LLM_PROVIDER_KIMI_API_KEY" not in sanitized
    assert "AIASYS_EMBEDDING_API_KEY" not in sanitized


def test_sanitize_notebook_variable_preview_hides_sensitive_runtime_tokens():
    preview = (
        "RuntimeDatabaseClient(base_url='http://127.0.0.1:13201/api/session-database', "
        "session_token='eyJ.demo.secret')"
    )

    assert sanitize_notebook_variable_preview("db", preview) == "[已隐藏敏感变量预览]"


def test_normalize_notebook_variable_payload_filters_bootstrap_noise_and_redacts_preview():
    items = [
        {
            "name": "db",
            "type_name": "RuntimeDatabaseClient",
            "preview": "RuntimeDatabaseClient(session_token='eyJ.demo.secret')",
        },
        {
            "name": "analysis_result",
            "type_name": "dict",
            "preview": "{'ok': True}",
        },
        {
            "name": "api_token",
            "type_name": "str",
            "preview": "'super-secret-token'",
        },
    ]

    normalized = normalize_notebook_variable_payload(items)

    assert normalized == [
        {
            "name": "analysis_result",
            "type_name": "dict",
            "preview": "{'ok': True}",
        },
        {
            "name": "api_token",
            "type_name": "str",
            "preview": "[已隐藏敏感变量预览]",
        },
    ]


def test_local_ipython_box_uses_logical_workspace_for_files_and_session_root_for_journal(
    tmp_path: Path,
):
    logical_workspace_root = tmp_path / "local_default" / "task-alpha"
    session_root = tmp_path / "local_default" / "conversation-alpha"
    logical_workspace_root.mkdir(parents=True, exist_ok=True)
    session_root.mkdir(parents=True, exist_ok=True)

    tokens = {
        "workspace": current_workspace.set(logical_workspace_root),
        "session_root": current_session_root.set(session_root),
        "session_id": current_session_id.set("conversation-alpha"),
        "user_id": current_user_id.set("local_default"),
    }
    try:
        tool = LocalIPythonBox()
        journal = tool._resolve_execution_journal()

        assert tool._resolve_workspace() == logical_workspace_root
        assert journal is not None
        assert journal.session_dir == session_root
    finally:
        current_user_id.reset(tokens["user_id"])
        current_session_id.reset(tokens["session_id"])
        current_session_root.reset(tokens["session_root"])
        current_workspace.reset(tokens["workspace"])
