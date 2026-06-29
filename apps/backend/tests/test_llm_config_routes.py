from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.routes import llm_config as route_module
from app.main import app
from app.models.user import UserInfo
from app.services.llm.llm_config_service import LLMConfigService
from app.storage.llm_provider_storage import LLMProviderStorage


@pytest.fixture
def llm_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from app.core import config as core_config
    from app.storage import llm_provider_storage as storage_module

    def get_test_config_dir(user_id: str) -> Path:
        return tmp_path / user_id / ".aiasys"

    monkeypatch.setattr(core_config, "get_user_global_config_dir", get_test_config_dir)
    monkeypatch.setattr(storage_module, "get_user_global_config_dir", get_test_config_dir)

    service = LLMConfigService(storage=LLMProviderStorage())
    app.dependency_overrides[route_module.get_service] = lambda: service
    app.dependency_overrides[route_module.get_current_user] = lambda: UserInfo(
        user_id="route-test-user",
        role="admin",
        auth_provider="local",
    )

    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(route_module.get_service, None)
        app.dependency_overrides.pop(route_module.get_current_user, None)


def test_model_crud_accepts_namespaced_model_id(llm_client: TestClient) -> None:
    provider_response = llm_client.post(
        "/api/llm/providers",
        json={
            "id": "siliconflow",
            "name": "SiliconFlow",
            "type": "openai_chat_completions",
            "base_url": "https://api.siliconflow.example/v1",
            "api_key": "test-key",
        },
    )
    assert provider_response.status_code == 200

    model_id = "siliconflow-BAAI/bge-m3"
    create_response = llm_client.post(
        "/api/llm/models",
        json={
            "id": model_id,
            "name": "BAAI/bge-m3",
            "provider": "siliconflow",
            "model": "BAAI/bge-m3",
            "model_type": "chat",
            "max_context_size": 128000,
            "enabled": True,
            "is_default": False,
        },
    )
    assert create_response.status_code == 200

    get_response = llm_client.get(
        "/api/llm/models/by-id",
        params={"model_id": model_id},
    )
    assert get_response.status_code == 200
    assert get_response.json()["id"] == model_id

    update_response = llm_client.patch(
        "/api/llm/models/by-id",
        params={"model_id": model_id},
        json={"name": "BGE M3"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "BGE M3"

    default_response = llm_client.post(
        "/api/llm/models/by-id/default",
        params={"model_id": model_id},
    )
    assert default_response.status_code == 200
    assert default_response.json()["id"] == model_id

    delete_response = llm_client.delete(
        "/api/llm/models/by-id",
        params={"model_id": model_id},
    )
    assert delete_response.status_code == 200
    assert delete_response.json() == {"success": True}

    missing_response = llm_client.get(
        "/api/llm/models/by-id",
        params={"model_id": model_id},
    )
    assert missing_response.status_code == 404
