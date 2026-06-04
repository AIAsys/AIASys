from app.core.config import _apply_secret_env_overrides


def test_apply_secret_env_overrides_replaces_sensitive_values(monkeypatch):
    config = {
        "llm": {
            "providers": {
                "kimi": {
                    "api_key": "config-kimi",
                    "base_url": "https://old-kimi.example",
                },
                "dashscope": {
                    "api_key": "config-dashscope",
                    "base_url": "https://old-dashscope.example",
                },
            }
        },
        "embedding": {"api_key": "config-embedding"},
        "auth": {"jwt_secret": "config-jwt"},
        "document_extraction": {"pdf_password": "config-pdf"},
    }

    monkeypatch.setenv("AIASYS_LLM_PROVIDER_KIMI_API_KEY", "env-kimi")
    monkeypatch.setenv("AIASYS_LLM_PROVIDER_DASHSCOPE_BASE_URL", "https://env-dashscope.example")
    monkeypatch.setenv("AIASYS_EMBEDDING_API_KEY", "env-embedding")
    monkeypatch.setenv("AIASYS_AUTH_JWT_SECRET", "env-jwt")
    monkeypatch.setenv("AIASYS_DOCUMENT_EXTRACTION_PDF_PASSWORD", "env-pdf")

    result = _apply_secret_env_overrides(config)

    assert result["llm"]["providers"]["kimi"]["api_key"] == "env-kimi"
    assert result["llm"]["providers"]["dashscope"]["base_url"] == "https://env-dashscope.example"
    assert result["embedding"]["api_key"] == "env-embedding"
    assert result["auth"]["jwt_secret"] == "env-jwt"
    assert result["document_extraction"]["pdf_password"] == "env-pdf"


def test_apply_secret_env_overrides_leaves_unset_values_unchanged(monkeypatch):
    monkeypatch.delenv("AIASYS_LLM_PROVIDER_KIMI_API_KEY", raising=False)

    config = {
        "llm": {"providers": {"kimi": {"api_key": "config-kimi"}}},
        "auth": {"jwt_secret": "config-jwt"},
    }

    result = _apply_secret_env_overrides(config)

    assert result["llm"]["providers"]["kimi"]["api_key"] == "config-kimi"
    assert result["auth"]["jwt_secret"] == "config-jwt"
