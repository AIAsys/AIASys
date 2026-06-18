from __future__ import annotations

import pytest

from app.services.llm.llm_config_service import LLMConfigService
from app.storage.llm_provider_storage import LLMProviderStorage


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


@pytest.fixture
def temp_user_config_dir(monkeypatch, tmp_path):
    """把用户全局配置目录重定向到临时目录，避免污染真实数据。"""
    from app.core import config as core_config

    def fake_dir(user_id: str) -> __import__("pathlib").Path:
        return tmp_path / str(user_id) / ".aiasys"

    monkeypatch.setattr(core_config, "get_user_global_config_dir", fake_dir)
    return tmp_path


def test_sync_config_json_to_user_with_object_models_and_capabilities(
    temp_user_config_dir, monkeypatch
):
    """验证 TOML 对象数组模型配置能正确同步 capabilities、上下文长度和默认模型。"""
    monkeypatch.setattr(
        "app.services.llm.llm_config_service.LLM_CONFIG",
        {"default_provider": "stepfun", "default_model": "step-3.7-flash"},
    )
    monkeypatch.setattr(
        "app.services.llm.llm_config_service.LLM_PROVIDERS",
        {
            "stepfun": {
                "type": "openai_chat_completions",
                "base_url": "https://api.stepfun.com/v1",
                "api_key": "test-key",
                "models": [
                    {"name": "step-router-v1", "max_context_size": 256000, "capabilities": []},
                    {"name": "step-3.5-flash", "max_context_size": 200000, "capabilities": []},
                    {
                        "name": "step-3.7-flash",
                        "max_context_size": 256000,
                        "capabilities": ["thinking", "image_in", "video_in"],
                    },
                ],
            }
        },
    )

    service = LLMConfigService(storage=LLMProviderStorage())
    service.sync_config_json_to_user("user1")

    full = service.get_full_config("user1")
    models = full["models"]

    assert len(models) == 3
    assert models["stepfun-step-router-v1"]["max_context_size"] == 256000
    assert models["stepfun-step-router-v1"].get("capabilities") in (None, [])
    assert models["stepfun-step-3.5-flash"]["max_context_size"] == 200000
    assert models["stepfun-step-3.5-flash"].get("capabilities") in (None, [])

    multimodal = models["stepfun-step-3.7-flash"]
    assert multimodal["max_context_size"] == 256000
    assert set(multimodal["capabilities"]) == {"thinking", "image_in", "video_in"}
    assert full["default_model"] == "stepfun-step-3.7-flash"


def test_sync_config_json_to_user_with_string_models_fallback(temp_user_config_dir, monkeypatch):
    """验证字符串数组模型配置仍兼容，capabilities 由接口类型推断。"""
    monkeypatch.setattr(
        "app.services.llm.llm_config_service.LLM_CONFIG",
        {"default_provider": "stepfun", "default_model": "step-3.7-flash"},
    )
    monkeypatch.setattr(
        "app.services.llm.llm_config_service.LLM_PROVIDERS",
        {
            "stepfun": {
                "type": "openai_chat_completions",
                "base_url": "https://api.stepfun.com/v1",
                "api_key": "test-key",
                "models": ["step-router-v1", "step-3.7-flash"],
            }
        },
    )

    service = LLMConfigService(storage=LLMProviderStorage())
    service.sync_config_json_to_user("user2")

    full = service.get_full_config("user2")
    models = full["models"]

    assert len(models) == 2
    assert models["stepfun-step-router-v1"]["max_context_size"] == 128000
    assert set(models["stepfun-step-router-v1"]["capabilities"]) == {"thinking", "image_in"}
    assert full["default_model"] == "stepfun-step-3.7-flash"
