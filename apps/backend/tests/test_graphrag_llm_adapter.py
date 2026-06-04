from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.graphrag import llm_adapter


class _FakeConfigService:
    def __init__(self, providers, models_by_provider, provider_keys):
        self._providers = providers
        self._models_by_provider = models_by_provider
        self._provider_keys = provider_keys

    def list_providers(self, user_id, enabled_only=False):
        return list(self._providers)

    def list_models(self, user_id, enabled_only=False, provider_id=None):
        models = list(self._models_by_provider.get(provider_id, []))
        if enabled_only:
            models = [model for model in models if getattr(model, "enabled", True)]
        return models

    def get_provider_with_key(self, user_id, provider_id):
        return self._provider_keys.get(provider_id)


@pytest.mark.asyncio
async def test_create_llm_client_from_config_skips_coding_only_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = [
        SimpleNamespace(
            id="kimi",
            type="anthropic_messages",
            base_url="https://api.kimi.com/coding/v1",
            is_default=True,
            enabled=True,
        ),
        SimpleNamespace(
            id="dashscope",
            type="openai_chat_completions",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            is_default=False,
            enabled=True,
        ),
    ]
    models_by_provider = {
        "kimi": [
            SimpleNamespace(
                id="kimi",
                name="kimi-for-coding",
                model="kimi-for-coding",
                is_default=True,
                enabled=True,
                description=None,
            )
        ],
        "dashscope": [
            SimpleNamespace(
                id="dashscope-qwen-max",
                name="qwen-max",
                model="qwen-max",
                is_default=False,
                enabled=True,
                description=None,
            )
        ],
    }
    provider_keys = {
        "dashscope": SimpleNamespace(
            api_key=SecretStr("test-key"),
            custom_headers={"X-Test": "1"},
        )
    }
    captured: dict[str, str] = {}

    def _fake_create_llm_client(provider, model):
        captured.update(
            {
                "protocol": getattr(provider, "protocol", ""),
                "model": model,
                "base_url": getattr(provider, "base_url", ""),
                "api_key": getattr(provider, "api_key", ""),
            }
        )
        return SimpleNamespace(
            chat_stream=lambda **kwargs: (x async for x in []),
            aclose=lambda: None,
        )

    monkeypatch.setattr(llm_adapter, "create_llm_client", _fake_create_llm_client)

    client = await llm_adapter.create_llm_client_from_config(
        config_service=_FakeConfigService(providers, models_by_provider, provider_keys)
    )

    assert client is not None
    assert client.model == "qwen-max"
    assert captured["protocol"] == "openai_chat_completions"
    assert captured["base_url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1"


@pytest.mark.asyncio
async def test_create_llm_client_from_config_skips_unsuitable_default_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = [
        SimpleNamespace(
            id="dashscope",
            type="openai_chat_completions",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            is_default=True,
            enabled=True,
        )
    ]
    models_by_provider = {
        "dashscope": [
            SimpleNamespace(
                id="dashscope-qwen-image",
                name="qwen-image-2.0",
                model="qwen-image-2.0",
                is_default=True,
                enabled=True,
                description=None,
            ),
            SimpleNamespace(
                id="dashscope-qwen-max",
                name="qwen-max",
                model="qwen-max",
                is_default=False,
                enabled=True,
                description=None,
            ),
        ]
    }
    provider_keys = {
        "dashscope": SimpleNamespace(
            api_key=SecretStr("test-key"),
            custom_headers=None,
        )
    }
    created_models: list[str] = []

    def _fake_create_llm_client(provider, model):
        created_models.append(model)
        return SimpleNamespace(
            chat_stream=lambda **kwargs: (x async for x in []),
            aclose=lambda: None,
        )

    monkeypatch.setattr(llm_adapter, "create_llm_client", _fake_create_llm_client)

    client = await llm_adapter.create_llm_client_from_config(
        config_service=_FakeConfigService(providers, models_by_provider, provider_keys)
    )

    assert client is not None
    assert client.model == "qwen-max"
    assert created_models == ["qwen-max"]


@pytest.mark.asyncio
async def test_create_llm_client_from_config_prefers_generic_text_model_over_minimax(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = [
        SimpleNamespace(
            id="dashscope",
            type="openai_chat_completions",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            is_default=True,
            enabled=True,
        )
    ]
    models_by_provider = {
        "dashscope": [
            SimpleNamespace(
                id="dashscope-minimax",
                name="MiniMax/MiniMax-M2.7",
                model="MiniMax/MiniMax-M2.7",
                is_default=False,
                enabled=True,
                description=None,
            ),
            SimpleNamespace(
                id="dashscope-glm-5",
                name="glm-5",
                model="glm-5",
                is_default=False,
                enabled=True,
                description=None,
            ),
        ]
    }
    provider_keys = {
        "dashscope": SimpleNamespace(
            api_key=SecretStr("test-key"),
            custom_headers=None,
        )
    }
    created_models: list[str] = []

    def _fake_create_llm_client(provider, model):
        created_models.append(model)
        return SimpleNamespace(
            chat_stream=lambda **kwargs: (x async for x in []),
            aclose=lambda: None,
        )

    monkeypatch.setattr(llm_adapter, "create_llm_client", _fake_create_llm_client)

    client = await llm_adapter.create_llm_client_from_config(
        config_service=_FakeConfigService(providers, models_by_provider, provider_keys)
    )

    assert client is not None
    assert client.model == "glm-5"
    assert created_models == ["glm-5"]


@pytest.mark.asyncio
async def test_create_llm_client_from_config_returns_none_when_no_suitable_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    providers = [
        SimpleNamespace(
            id="dashscope",
            type="openai_chat_completions",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            is_default=True,
            enabled=True,
        )
    ]
    models_by_provider = {
        "dashscope": [
            SimpleNamespace(
                id="dashscope-qwen-image",
                name="qwen-image-2.0",
                model="qwen-image-2.0",
                is_default=True,
                enabled=True,
                description=None,
            ),
            SimpleNamespace(
                id="dashscope-speech",
                name="speech-02-hd",
                model="speech-02-hd",
                is_default=False,
                enabled=True,
                description=None,
            ),
        ]
    }
    provider_keys = {
        "dashscope": SimpleNamespace(
            api_key=SecretStr("test-key"),
            custom_headers=None,
        )
    }

    def _unexpected_create_client(*args, **kwargs):
        raise AssertionError("should not create client when all models are unsuitable")

    monkeypatch.setattr(llm_adapter, "create_llm_client", _unexpected_create_client)

    client = await llm_adapter.create_llm_client_from_config(
        config_service=_FakeConfigService(providers, models_by_provider, provider_keys)
    )

    assert client is None
