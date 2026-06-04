from __future__ import annotations

from app.services.llm.llm_config_service import LLMConfigService


class _FakeStorage:
    def __init__(self, config: dict):
        self._config = config

    def get_full_config(self, user_id: str) -> dict:
        return self._config

    def update_model_defaults(self, user_id: str, updates: dict) -> dict:
        self._config.update(updates)
        return {
            "default_model": self._config.get("default_model"),
            "default_chat_model": self._config.get("default_chat_model"),
            "default_embedding_model": self._config.get("default_embedding_model"),
        }


def test_get_full_config_prefers_default_provider_model_when_model_not_marked_default():
    service = LLMConfigService(
        storage=_FakeStorage(
            {
                "providers": [
                    {
                        "id": "krill",
                        "type": "openai_responses",
                        "base_url": "https://krill.example/v1",
                        "enabled": True,
                        "is_default": False,
                    },
                    {
                        "id": "kimi",
                        "type": "anthropic_messages",
                        "base_url": "https://api.kimi.com/coding/v1",
                        "enabled": True,
                        "is_default": True,
                    },
                ],
                "models": [
                    {
                        "id": "krill-gpt-5.4",
                        "provider": "krill",
                        "model": "gpt-5.4",
                        "enabled": True,
                        "is_default": False,
                    },
                    {
                        "id": "kimi-kimi-for-coding",
                        "provider": "kimi",
                        "model": "kimi-for-coding",
                        "enabled": True,
                        "is_default": False,
                    },
                ],
            }
        )
    )

    full_config = service.get_full_config("local_default")

    assert full_config["default_model"] == "kimi-kimi-for-coding"
    assert full_config["default_chat_model"] == "kimi-kimi-for-coding"


def test_get_model_defaults_prefers_explicit_chat_and_embedding_defaults():
    service = LLMConfigService(
        storage=_FakeStorage(
            {
                "providers": [
                    {
                        "id": "dashscope",
                        "type": "openai_chat_completions",
                        "base_url": "https://dashscope.example/v1",
                        "enabled": True,
                        "is_default": True,
                    }
                ],
                "models": [
                    {
                        "id": "dashscope-qwen-max",
                        "provider": "dashscope",
                        "model": "qwen-max",
                        "model_type": "chat",
                        "enabled": True,
                    },
                    {
                        "id": "dashscope-bge-m3",
                        "provider": "dashscope",
                        "model": "BAAI/bge-m3",
                        "model_type": "embedding",
                        "enabled": True,
                    },
                ],
                "default_chat_model": "dashscope-qwen-max",
                "default_embedding_model": "dashscope-bge-m3",
            }
        )
    )

    defaults = service.get_model_defaults("local_default")

    assert defaults.default_chat_model == "dashscope-qwen-max"
    assert defaults.default_embedding_model == "dashscope-bge-m3"


def test_update_model_defaults_rejects_wrong_model_type():
    service = LLMConfigService(
        storage=_FakeStorage(
            {
                "providers": [
                    {
                        "id": "dashscope",
                        "type": "openai_chat_completions",
                        "base_url": "https://dashscope.example/v1",
                        "enabled": True,
                    }
                ],
                "models": [
                    {
                        "id": "dashscope-qwen-max",
                        "provider": "dashscope",
                        "model": "qwen-max",
                        "model_type": "chat",
                        "enabled": True,
                    }
                ],
            }
        )
    )

    try:
        service.update_model_defaults(
            "local_default",
            default_chat_model=None,
            default_embedding_model="dashscope-qwen-max",
        )
    except ValueError as exc:
        assert "embedding" in str(exc)
    else:
        raise AssertionError("expected ValueError for wrong embedding model type")
