from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.routes import sessions_branches as sessions_branches_module
from app.api.routes import workspaces_core as workspaces_core_module
from app.api.routes.sessions_branches import (
    get_session_llm_selection,
    update_session_llm_selection,
)
from app.api.routes.workspaces_core import (
    get_workspace_llm_selection,
    update_workspace_llm_selection,
)
from app.models.llm_selection import (
    LLMModelIdentity,
    LLMModelScopeSelection,
    SessionLLMSelectionResponse,
    UpdateScopedModelSelectionRequest,
    WorkspaceLLMSelectionResponse,
)
from app.models.user import UserInfo


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _build_scope(scope: str, model_id: str | None) -> LLMModelScopeSelection:
    identity = LLMModelIdentity(
        model_id=model_id,
        display_name=model_id,
        model_name=model_id,
        provider="provider-kimi" if model_id else None,
        provider_name="Kimi" if model_id else None,
    )
    return LLMModelScopeSelection(
        scope=scope,  # type: ignore[arg-type]
        configured_model_id=model_id,
        inherited_from=None,
        effective=identity,
    )


class FakeWorkspaceRegistry:
    def get_workspace(self, user_id: str, workspace_id: str, include_conversations: bool = False):
        assert user_id == "local_default"
        assert workspace_id == "task-route-llm"
        return SimpleNamespace(workspace_id=workspace_id)


class FakeModelSelectionService:
    def __init__(self) -> None:
        self.updated_workspace_model_id: str | None = None
        self.updated_session_model_id: str | None = None

    def get_workspace_selection(self, *, user_id: str, workspace_id: str):
        assert user_id == "local_default"
        assert workspace_id == "task-route-llm"
        return WorkspaceLLMSelectionResponse(
            workspace_id=workspace_id,
            global_scope=_build_scope("global", "model-global"),
            workspace_scope=_build_scope("workspace", "model-workspace"),
            effective=LLMModelIdentity(
                model_id="model-workspace",
                display_name="model-workspace",
            ),
        )

    def update_workspace_model_selection(
        self,
        *,
        user_id: str,
        workspace_id: str,
        model_id: str | None,
    ):
        assert user_id == "local_default"
        assert workspace_id == "task-route-llm"
        self.updated_workspace_model_id = model_id
        return self.get_workspace_selection(user_id=user_id, workspace_id=workspace_id)

    def get_session_selection(self, *, user_id: str, session_id: str):
        assert user_id == "local_default"
        assert session_id == "branch-route-llm"
        return SessionLLMSelectionResponse(
            session_id=session_id,
            workspace_id="task-route-llm",
            global_scope=_build_scope("global", "model-global"),
            workspace_scope=_build_scope("workspace", "model-workspace"),
            session_scope=_build_scope("session", "model-session"),
            effective=LLMModelIdentity(
                model_id="model-session",
                display_name="model-session",
            ),
        )

    def update_session_model_selection(
        self,
        *,
        user_id: str,
        session_id: str,
        model_id: str | None,
    ):
        assert user_id == "local_default"
        assert session_id == "branch-route-llm"
        self.updated_session_model_id = model_id
        return self.get_session_selection(user_id=user_id, session_id=session_id)


@pytest.mark.asyncio
async def test_workspace_llm_selection_routes_dispatch_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeModelSelectionService()
    monkeypatch.setattr(
        workspaces_core_module,
        "get_workspace_registry_service",
        lambda: FakeWorkspaceRegistry(),
    )
    monkeypatch.setattr(
        workspaces_core_module,
        "get_model_selection_service",
        lambda: fake_service,
    )

    response = await get_workspace_llm_selection(
        "task-route-llm",
        current_user=_build_user(),
    )
    assert response.effective.model_id == "model-workspace"

    updated = await update_workspace_llm_selection(
        "task-route-llm",
        UpdateScopedModelSelectionRequest(model_id="model-workspace"),
        current_user=_build_user(),
    )
    assert fake_service.updated_workspace_model_id == "model-workspace"
    assert updated.workspace_scope.configured_model_id == "model-workspace"


@pytest.mark.asyncio
async def test_session_llm_selection_routes_dispatch_to_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_service = FakeModelSelectionService()
    fake_metadata = SimpleNamespace(session_id="branch-route-llm")
    monkeypatch.setattr(
        sessions_branches_module.session_manager,
        "get_session",
        lambda session_id, user_id: fake_metadata,
    )
    monkeypatch.setattr(
        sessions_branches_module,
        "get_model_selection_service",
        lambda: fake_service,
    )

    response = await get_session_llm_selection(
        "local_default",
        "branch-route-llm",
        current_user=_build_user(),
    )
    assert response.effective.model_id == "model-session"

    updated = await update_session_llm_selection(
        "local_default",
        "branch-route-llm",
        UpdateScopedModelSelectionRequest(model_id="model-session"),
        current_user=_build_user(),
    )
    assert fake_service.updated_session_model_id == "model-session"
    assert updated.session_scope.configured_model_id == "model-session"
