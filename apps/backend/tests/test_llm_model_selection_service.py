from __future__ import annotations

from app.services.llm.model_selection_service import ModelSelectionService
from app.services.session import SessionManager


class StubLLMConfigService:
    def get_full_config(self, user_id: str | None):
        assert user_id == "local_default"
        return {
            "providers": {
                "provider-kimi": {
                    "name": "Kimi",
                    "type": "anthropic_messages",
                }
            },
            "models": {
                "model-global": {
                    "id": "model-global",
                    "name": "全局模型",
                    "provider": "provider-kimi",
                    "model": "kimi-global",
                },
                "model-workspace": {
                    "id": "model-workspace",
                    "name": "工作区模型",
                    "provider": "provider-kimi",
                    "model": "kimi-workspace",
                },
                "model-session": {
                    "id": "model-session",
                    "name": "会话模型",
                    "provider": "provider-kimi",
                    "model": "kimi-session",
                },
            },
            "default_model": "model-global",
        }


class FakeWorkspaceRegistry:
    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager
        self._workspace_model_ids: dict[str, str | None] = {}
        self._session_to_workspace: dict[str, str] = {}

    def bind_session(self, session_id: str, workspace_id: str) -> None:
        self._session_to_workspace[session_id] = workspace_id

    def find_workspace_id_by_session_id(
        self,
        user_id: str,
        session_id: str,
    ) -> str | None:
        assert user_id == "local_default"
        return self._session_to_workspace.get(session_id)

    def get_workspace_preferred_model_id(
        self,
        user_id: str,
        workspace_id: str,
    ) -> str | None:
        assert user_id == "local_default"
        return self._workspace_model_ids.get(workspace_id)

    def update_workspace_preferred_model_id(
        self,
        user_id: str,
        workspace_id: str,
        preferred_model_id: str | None,
    ) -> str | None:
        assert user_id == "local_default"
        self._workspace_model_ids[workspace_id] = preferred_model_id
        return preferred_model_id


def _build_registry(tmp_path):
    session_manager = SessionManager(tmp_path)
    registry = FakeWorkspaceRegistry(session_manager)
    session_manager.create_session(
        session_id="branch-llm-priority",
        user_id="local_default",
    )
    registry.bind_session("branch-llm-priority", "task-llm-priority")
    session_manager.create_session(
        session_id="branch-llm-missing",
        user_id="local_default",
    )
    registry.bind_session("branch-llm-missing", "task-llm-missing")
    return registry


def test_model_selection_service_resolves_session_over_workspace_over_global(
    tmp_path,
) -> None:
    registry = _build_registry(tmp_path)
    service = ModelSelectionService(
        llm_config_service=StubLLMConfigService(),
        workspace_registry=registry,
    )

    initial = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-priority",
    )
    assert initial.effective.model_id == "model-global"
    assert initial.session_scope.inherited_from == "workspace"
    assert initial.workspace_scope.inherited_from == "global"

    registry.update_workspace_preferred_model_id(
        "local_default",
        "task-llm-priority",
        "model-workspace",
    )
    workspace_level = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-priority",
    )
    assert workspace_level.effective.model_id == "model-workspace"
    assert workspace_level.workspace_scope.configured_model_id == "model-workspace"

    registry.session_manager.update_session_preferred_model_id(
        session_id="branch-llm-priority",
        user_id="local_default",
        preferred_model_id="model-session",
    )
    session_level = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-priority",
    )
    assert session_level.effective.model_id == "model-session"
    assert session_level.session_scope.configured_model_id == "model-session"

    registry.session_manager.update_session_preferred_model_id(
        session_id="branch-llm-priority",
        user_id="local_default",
        preferred_model_id=None,
    )
    back_to_workspace = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-priority",
    )
    assert back_to_workspace.effective.model_id == "model-workspace"

    registry.update_workspace_preferred_model_id(
        "local_default",
        "task-llm-priority",
        None,
    )
    back_to_global = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-priority",
    )
    assert back_to_global.effective.model_id == "model-global"


def test_model_selection_service_marks_missing_configured_model_and_falls_back(
    tmp_path,
) -> None:
    registry = _build_registry(tmp_path)
    registry.update_workspace_preferred_model_id(
        "local_default",
        "task-llm-missing",
        "model-gone",
    )

    service = ModelSelectionService(
        llm_config_service=StubLLMConfigService(),
        workspace_registry=registry,
    )
    selection = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-missing",
    )

    assert selection.workspace_scope.configured_model_id == "model-gone"
    assert selection.workspace_scope.configured_missing is True
    assert selection.effective.model_id == "model-global"


def test_model_selection_service_ignores_embedding_models_for_chat_selection(
    tmp_path,
) -> None:
    class EmbeddingAwareStubLLMConfigService:
        def get_full_config(self, user_id: str | None):
            assert user_id == "local_default"
            return {
                "providers": {
                    "provider-kimi": {
                        "name": "Kimi",
                        "type": "anthropic_messages",
                    }
                },
                "models": {
                    "model-global": {
                        "id": "model-global",
                        "name": "全局模型",
                        "provider": "provider-kimi",
                        "model": "kimi-global",
                        "model_type": "chat",
                    },
                    "embedding-global": {
                        "id": "embedding-global",
                        "name": "默认向量模型",
                        "provider": "provider-kimi",
                        "model": "text-embedding",
                        "model_type": "embedding",
                    },
                },
                "default_model": "model-global",
                "default_embedding_model": "embedding-global",
            }

    registry = _build_registry(tmp_path)
    service = ModelSelectionService(
        llm_config_service=EmbeddingAwareStubLLMConfigService(),
        workspace_registry=registry,
    )

    selection = service.get_session_selection(
        user_id="local_default",
        session_id="branch-llm-priority",
    )

    assert selection.effective.model_id == "model-global"
    try:
        service.validate_model_id("local_default", "embedding-global")
    except ValueError as exc:
        assert "模型不存在" in str(exc)
    else:
        raise AssertionError("expected embedding model to be rejected by chat selection service")
