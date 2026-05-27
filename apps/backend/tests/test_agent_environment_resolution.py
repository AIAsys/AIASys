from types import SimpleNamespace

from app.services.agent.mixins import environment as environment_module
from app.services.agent.mixins.environment import EnvironmentMixin


class _FakeSessionManager:
    def __init__(self, metadata):
        self._metadata = metadata

    def get_session(self, session_id: str, user_id: str):
        return self._metadata


class _FakeRegistry:
    def __init__(self, runtime_binding):
        self._runtime_binding = runtime_binding

    def find_workspace_id_by_session_id(self, user_id: str, session_id: str) -> str:
        return "workspace-a"

    def get_workspace(
        self,
        user_id: str,
        workspace_id: str,
        include_conversations: bool = False,
    ):
        return SimpleNamespace(runtime_binding=self._runtime_binding)


class _FakeAgentService(EnvironmentMixin):
    def __init__(self, metadata):
        self._session_manager = _FakeSessionManager(metadata)


def test_session_runtime_env_overrides_workspace_default(monkeypatch):
    metadata = SimpleNamespace(env_id="session-env", sandbox_mode="docker")
    service = _FakeAgentService(metadata)
    registry = _FakeRegistry(
        SimpleNamespace(env_id="workspace-env", sandbox_mode="local"),
    )
    monkeypatch.setattr(
        environment_module,
        "get_workspace_registry_service",
        lambda: registry,
    )

    assert service._resolve_env_id_for_session("u1", "s1") == "session-env"
    assert service._resolve_sandbox_mode_for_session("u1", "s1") == "docker"


def test_workspace_runtime_env_used_when_session_has_no_override(monkeypatch):
    metadata = SimpleNamespace(env_id=None, sandbox_mode=None)
    service = _FakeAgentService(metadata)
    registry = _FakeRegistry(
        SimpleNamespace(env_id="workspace-env", sandbox_mode="local"),
    )
    monkeypatch.setattr(
        environment_module,
        "get_workspace_registry_service",
        lambda: registry,
    )

    assert service._resolve_env_id_for_session("u1", "s1") == "workspace-env"
    assert service._resolve_sandbox_mode_for_session("u1", "s1") == "local"


def test_explicit_runtime_env_preferred_over_session_and_workspace(monkeypatch):
    metadata = SimpleNamespace(env_id="session-env", sandbox_mode="docker")
    service = _FakeAgentService(metadata)
    registry = _FakeRegistry(
        SimpleNamespace(env_id="workspace-env", sandbox_mode="local"),
    )
    monkeypatch.setattr(
        environment_module,
        "get_workspace_registry_service",
        lambda: registry,
    )

    assert (
        service._resolve_env_id_for_session("u1", "s1", "request-env")
        == "request-env"
    )
    assert (
        service._resolve_sandbox_mode_for_session("u1", "s1", "plain_shell")
        == "plain_shell"
    )
