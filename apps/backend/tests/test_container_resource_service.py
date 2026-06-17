from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.workspace import ExecutionResourceGroup, WorkspaceRuntimeBinding
from app.services.container_resource import ContainerResourceService
from app.services.session import SessionManager
from app.services.workspace_registry import WorkspaceRegistryService


class _FakeDockerContainer:
    def __init__(
        self,
        *,
        container_id: str,
        name: str,
        image: str,
        status: str = "created",
        labels: dict[str, str] | None = None,
    ) -> None:
        self.id = container_id
        self.name = name
        self.status = status
        self.attrs = {
            "Config": {
                "Image": image,
                "Labels": labels or {},
            },
            "State": {"Status": status},
            "NetworkSettings": {"Ports": {}},
        }
        self.start_calls = 0
        self.reload_calls = 0

    def reload(self) -> None:
        self.reload_calls += 1
        self.attrs["State"]["Status"] = self.status

    def start(self) -> None:
        self.start_calls += 1
        self.status = "running"
        self.attrs["State"]["Status"] = self.status

    def stop(self) -> None:
        self.status = "exited"
        self.attrs["State"]["Status"] = self.status

    def remove(self, force: bool = False) -> None:
        self.attrs["State"]["Removed"] = force


class _FakeContainersAPI:
    def __init__(self) -> None:
        self.created_kwargs: dict[str, object] | None = None
        self._containers: dict[str, _FakeDockerContainer] = {}

    def register(self, container: _FakeDockerContainer) -> None:
        self._containers[container.id] = container
        self._containers[container.name] = container

    def create(self, **kwargs):
        self.created_kwargs = kwargs
        image = str(kwargs["image"])
        container = _FakeDockerContainer(
            container_id="created-container-id",
            name="created-container",
            image=image,
        )
        self.register(container)
        return container

    def get(self, key: str) -> _FakeDockerContainer:
        return self._containers[key]


class _FakeDockerClient:
    def __init__(self) -> None:
        self.containers = _FakeContainersAPI()

    def ping(self) -> bool:
        return True


def _build_service(tmp_path: Path) -> ContainerResourceService:
    workspace_registry = WorkspaceRegistryService(
        tmp_path,
        session_manager=SessionManager(tmp_path),
    )
    return ContainerResourceService(tmp_path, workspace_registry=workspace_registry)


def _create_workspace(
    service: ContainerResourceService,
    *,
    workspace_id: str = "task-env",
) -> None:
    service.workspace_registry.create_workspace(
        user_id="local_default",
        workspace_id=workspace_id,
        title="Docker 沙盒验证",
        initial_conversation_title="默认对话",
    )


def test_register_existing_docker_container_persists_workspace_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    fake_client = _FakeDockerClient()
    existing = _FakeDockerContainer(
        container_id="abc123",
        name="sandbox-alpha",
        image="python:3.11-slim",
        status="running",
        labels={"aiasys.managed": "false"},
    )
    fake_client.containers.register(existing)
    monkeypatch.setattr(service, "_docker_client", lambda: fake_client)

    resource = service.register_container(
        "local_default",
        "task-env",
        container_id="sandbox-alpha-resource",
        name="Alpha 沙盒",
        container_id_or_name="sandbox-alpha",
        workspace_mount_path="/workspace",
    )

    assert resource.container_id == "sandbox-alpha-resource"
    assert resource.name == "Alpha 沙盒"
    assert resource.image == "python:3.11-slim"
    assert resource.docker_container_id == "abc123"
    assert resource.container_name == "sandbox-alpha"
    assert resource.status == "running"
    assert resource.managed is False

    registry_path = (
        tmp_path
        / "local_default"
        / "task-env"
        / ".env"
        / "container_registry.json"
    )
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert payload["containers"][0]["container_id"] == "sandbox-alpha-resource"
    assert payload["containers"][0]["docker_container_id"] == "abc123"


def test_register_docker_container_from_image_uses_workspace_env_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _build_service(tmp_path)
    _create_workspace(service)
    service.workspace_registry.update_workspace(
        user_id="local_default",
        workspace_id="task-env",
        runtime_binding=WorkspaceRuntimeBinding(
            resources=ExecutionResourceGroup(python_env_id="workspace-default"),
            env_vars={"TOKEN": "workspace-secret"},
        ),
    )
    fake_client = _FakeDockerClient()
    monkeypatch.setattr(service, "_docker_client", lambda: fake_client)

    resource = service.register_container(
        "local_default",
        "task-env",
        container_id="sandbox-create",
        name="Create 沙盒",
        image="python:3.11-slim",
        create_container=True,
        auto_start=True,
        command="sleep infinity",
        env={"EXTRA": "value"},
        labels={"purpose": "test"},
        ports={"8080/tcp": "18080"},
    )

    assert resource.container_id == "sandbox-create"
    assert resource.image == "python:3.11-slim"
    assert resource.docker_container_id == "created-container-id"
    assert resource.container_name == "created-container"
    assert resource.status == "running"
    assert resource.managed is True
    assert resource.auto_start is True
    assert resource.command == "sleep infinity"
    assert resource.labels["purpose"] == "test"
    assert resource.labels["aiasys.managed"] == "true"
    assert resource.labels["aiasys.user_id"] == "local_default"
    assert resource.labels["aiasys.workspace_id"] == "task-env"

    created_kwargs = fake_client.containers.created_kwargs
    assert created_kwargs is not None
    assert created_kwargs["image"] == "python:3.11-slim"
    assert created_kwargs["command"] == ["sleep", "infinity"]
    assert created_kwargs["working_dir"] == "/workspace"
    assert created_kwargs["environment"] == {
        "TOKEN": "workspace-secret",
        "EXTRA": "value",
    }
    assert created_kwargs["ports"] == {"8080/tcp": 18080}
