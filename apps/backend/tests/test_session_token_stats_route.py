from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.api.routes import sessions as sessions_route
from app.models.session import SessionBudget
from app.models.user import UserInfo
from app.services.session import SessionManager


class FakeLLMConfigService:
    def get_full_config(self, user_id: str) -> dict:
        assert user_id == "local_default"
        return {
            "models": {
                "model-session": {
                    "id": "model-session",
                    "name": "会话模型",
                    "provider": "provider-kimi",
                    "model": "kimi-session",
                    "max_context_size": 262144,
                    "model_type": "chat",
                }
            },
            "providers": {
                "provider-kimi": {
                    "name": "Kimi",
                    "type": "anthropic_messages",
                }
            },
            "default_model": "model-session",
        }


class FakeModelSelectionService:
    def resolve_effective_model_id(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        workspace_id: str | None = None,
    ) -> str | None:
        assert user_id == "local_default"
        assert session_id == "branch-token-stats"
        assert workspace_id is None
        return "model-session"


def _build_user() -> UserInfo:
    return UserInfo(user_id="local_default", role="admin", auth_provider="local")


def _write_history_snapshot(session_dir: Path, messages: list[dict]) -> None:
    path = session_dir / ".aiasys" / "session" / "_active" / "history.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "_schema_version": 1,
                "messages": messages,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_token_stats_reads_context_tokens_without_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager(tmp_path)
    monkeypatch.setattr(sessions_route, "session_manager", manager)
    monkeypatch.setattr(
        sessions_route,
        "get_model_selection_service",
        lambda: FakeModelSelectionService(),
    )
    monkeypatch.setattr(
        sessions_route,
        "get_llm_config_service",
        lambda: FakeLLMConfigService(),
    )
    monkeypatch.setattr(sessions_route.agent_service, "_active_sessions", {})

    session_id = "branch-token-stats"
    manager.create_session(
        session_id=session_id,
        user_id="local_default",
        title="Token 统计",
    )
    session_dir = manager._get_session_dir(session_id, "local_default")
    _write_history_snapshot(
        session_dir,
        [
            {"role": "user", "content": "abcd" * 100},
            {"role": "assistant", "content": "efgh" * 80},
        ],
    )

    payload = await sessions_route.get_session_token_stats(
        "local_default",
        session_id,
        user=_build_user(),
    )

    assert payload.context_tokens == 180
    assert payload.context_window == 262144
    assert payload.context_usage_pct == 0.1
    assert payload.tokens_used == 0
    assert payload.token_budget is None


@pytest.mark.asyncio
async def test_token_stats_falls_back_to_history_snapshot_envelope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager(tmp_path)
    monkeypatch.setattr(sessions_route, "session_manager", manager)
    monkeypatch.setattr(
        sessions_route,
        "get_model_selection_service",
        lambda: FakeModelSelectionService(),
    )
    monkeypatch.setattr(
        sessions_route,
        "get_llm_config_service",
        lambda: FakeLLMConfigService(),
    )
    monkeypatch.setattr(sessions_route.agent_service, "_active_sessions", {})

    session_id = "branch-token-stats"
    manager.create_session(
        session_id=session_id,
        user_id="local_default",
        title="Token 统计",
    )
    session_dir = manager._get_session_dir(session_id, "local_default")
    _write_history_snapshot(
        session_dir,
        [
            {
                "role": "user",
                "content": "hello" * 120,
                "display_content": "hello",
            },
            {
                "role": "assistant",
                "content": "world" * 80,
                "reasoning_content": "hidden" * 20,
            },
        ],
    )

    payload = await sessions_route.get_session_token_stats(
        "local_default",
        session_id,
        user=_build_user(),
    )

    assert payload.context_tokens == 250
    assert payload.context_window == 262144
    assert payload.context_usage_pct == 0.1
    assert payload.tokens_used == 0
    assert payload.token_budget is None


@pytest.mark.asyncio
async def test_token_stats_prefers_active_runtime_context_over_saved_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager(tmp_path)
    monkeypatch.setattr(sessions_route, "session_manager", manager)
    monkeypatch.setattr(
        sessions_route,
        "get_model_selection_service",
        lambda: FakeModelSelectionService(),
    )
    monkeypatch.setattr(
        sessions_route,
        "get_llm_config_service",
        lambda: FakeLLMConfigService(),
    )

    session_id = "branch-token-stats"
    manager.create_session(
        session_id=session_id,
        user_id="local_default",
        title="Token 统计",
    )
    manager.update_session_budget(
        session_id,
        "local_default",
        SessionBudget(
            token_budget=1000000,
            tokens_used=1200,
            context_tokens=500,
        ),
    )

    active_session = type("ActiveRuntimeSession", (), {"_estimated_token_count": 12345})()
    monkeypatch.setattr(
        sessions_route.agent_service,
        "_active_sessions",
        {"local_default/branch-token-stats": active_session},
    )

    payload = await sessions_route.get_session_token_stats(
        "local_default",
        session_id,
        user=_build_user(),
    )

    assert payload.context_tokens == 12345
    assert payload.context_window == 262144
    assert payload.tokens_used == 1200
    assert payload.token_budget == 1000000
