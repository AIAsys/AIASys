"""工作区容器资源登记服务。"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.workspace_registry import WorkspaceRegistryService

from app.core.config import WORKSPACE_DIR
from app.models.container_resource import (
    WorkspaceContainerResource,
    WorkspaceContainerResourceRegistry,
)
from app.services.runtime_environment import resolve_workspace_runtime_dir


def _shell_split(command: str | list[str] | None) -> list[str] | None:
    """跨平台 shell 命令分割。

    如果已经是 list 直接返回；如果是 str，在 Windows 上用空格分割（避免
    shlex.split 按 POSIX 规则错误处理含反斜杠的路径），POSIX 上用 shlex.split。
    """
    if command is None or isinstance(command, list):
        return command
    if os.name == "nt":
        return command.split()
    import shlex

    return shlex.split(command)


_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_REGISTRY_FILE = "container_registry.json"


def _now_iso() -> str:
    return datetime.now().isoformat()


def _ensure_valid_id(value: str, field_name: str) -> None:
    if not value or not _ID_PATTERN.match(value):
        raise ValueError(f"无效的 {field_name}")


def _normalize_container_id(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    _ensure_valid_id(text, "container_id")
    return text


def _docker_fallback_id(image: str | None) -> str:
    seed = (image or "container").strip()
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", seed).strip("-").lower()
    if not normalized:
        normalized = "container"
    return f"ctr-{normalized[:32]}"


class ContainerResourceService:
    def __init__(
        self,
        workspace_root: Path = WORKSPACE_DIR,
        workspace_registry: "WorkspaceRegistryService" | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root)
        if workspace_registry is not None:
            self.workspace_registry = workspace_registry
        else:
            from app.services.workspace_registry import WorkspaceRegistryService

            self.workspace_registry = WorkspaceRegistryService(self.workspace_root)

    def list_workspace_containers(
        self,
        user_id: str,
        workspace_id: str,
    ) -> WorkspaceContainerResourceRegistry:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        registry = self._read_registry(workspace_dir)
        containers: list[WorkspaceContainerResource] = []
        for item in registry.get("containers", []):
            if not isinstance(item, dict):
                continue
            container = WorkspaceContainerResource.model_validate(item)
            containers.append(self._inspect_container(container))
        return WorkspaceContainerResourceRegistry(
            workspace_id=workspace_id,
            containers=containers,
            docker_available=self.is_docker_available(),
            total=len(containers),
        )

    def register_container(
        self,
        user_id: str,
        workspace_id: str,
        *,
        container_id: str | None = None,
        name: str | None = None,
        image: str | None = None,
        container_id_or_name: str | None = None,
        workspace_mount_path: str = "/workspace",
        create_container: bool = False,
        auto_start: bool = False,
        command: str | None = None,
        env: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
        ports: dict[str, str] | None = None,
    ) -> WorkspaceContainerResource:
        if not self.is_docker_available():
            raise RuntimeError("Docker daemon 不可用，无法登记容器资源")

        workspace_dir = self._workspace_dir(user_id, workspace_id)
        resolved_container = None
        docker_client = self._docker_client()
        normalized_labels = {
            "aiasys.managed": "true" if create_container else "false",
            "aiasys.user_id": user_id,
            "aiasys.workspace_id": workspace_id,
            **(labels or {}),
        }

        if create_container:
            if not image:
                raise ValueError("create_container=true 时必须提供 image")
            resolved_command = _shell_split(command)
            workspace_env_vars = self.workspace_registry.get_workspace_env_vars(
                user_id, workspace_id
            )
            merged_env = {**(workspace_env_vars or {}), **(env or {})}

            resolved_ports: dict[str, int | tuple[str, int]] = {}
            for k, v in (ports or {}).items():
                resolved_ports[k] = int(v)

            resolved_container = docker_client.containers.create(
                image=image,
                command=resolved_command,
                detach=True,
                tty=True,
                working_dir=workspace_mount_path,
                volumes={
                    str(workspace_dir.resolve()): {
                        "bind": workspace_mount_path,
                        "mode": "rw",
                    }
                },
                environment=merged_env,
                labels=normalized_labels,
                ports=resolved_ports,
            )
            if auto_start:
                resolved_container.start()
        elif container_id_or_name:
            resolved_container = self._get_docker_container(
                docker_client,
                container_id_or_name=container_id_or_name,
            )
        elif not image:
            raise ValueError("登记容器资源至少需要 image 或 container_id_or_name")

        if resolved_container is not None:
            resolved_container.reload()
            docker_cid = str(resolved_container.id)
            container_name = str(getattr(resolved_container, "name", "") or "")
            attrs = getattr(resolved_container, "attrs", {}) or {}
            config = attrs.get("Config") or {}
            image = image or config.get("Image")
            container_status = str(getattr(resolved_container, "status", "") or "")
            managed = bool(
                (config.get("Labels") or {}).get("aiasys.managed") == "true" or create_container
            )
        else:
            docker_cid = None
            container_name = None
            container_status = None
            managed = False

        resolved_container_id = _normalize_container_id(
            container_id,
            _docker_fallback_id(image),
        )
        now = _now_iso()
        existing = self._find_container(workspace_dir, resolved_container_id)
        container = WorkspaceContainerResource(
            container_id=resolved_container_id,
            name=(name or container_name or image or resolved_container_id).strip(),
            image=image or "",
            docker_container_id=docker_cid,
            container_name=container_name,
            status=(
                self._docker_status_to_container_status(container_status)
                if container_status is not None
                else "created"
            ),
            workspace_mount_path=workspace_mount_path,
            command=command,
            ports=ports or {},
            env=env or {},
            labels=normalized_labels,
            managed=managed,
            auto_start=auto_start,
            created_at=existing.created_at if existing else now,
            updated_at=now,
            last_error=None,
        )
        self._upsert_container(workspace_dir, container)
        return container

    def inspect_container(
        self,
        user_id: str,
        workspace_id: str,
        container_id: str,
    ) -> WorkspaceContainerResource:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        container = self._find_container(workspace_dir, container_id)
        if container is None:
            raise FileNotFoundError(f"容器资源不存在: {container_id}")
        inspected = self._inspect_container(container)
        self._upsert_container(workspace_dir, inspected)
        return inspected

    def start_container(
        self,
        user_id: str,
        workspace_id: str,
        container_id: str,
    ) -> WorkspaceContainerResource:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        container = self._find_container(workspace_dir, container_id)
        if container is None:
            raise FileNotFoundError(f"容器资源不存在: {container_id}")
        if not container.docker_container_id:
            raise ValueError("该容器资源没有关联的 Docker 容器，无法启动")
        try:
            client = self._docker_client()
            dc = client.containers.get(container.docker_container_id)
            dc.start()
        except Exception as exc:
            raise RuntimeError(f"启动容器失败: {exc}") from exc
        return self.inspect_container(user_id, workspace_id, container_id)

    def stop_container(
        self,
        user_id: str,
        workspace_id: str,
        container_id: str,
    ) -> WorkspaceContainerResource:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        container = self._find_container(workspace_dir, container_id)
        if container is None:
            raise FileNotFoundError(f"容器资源不存在: {container_id}")
        if not container.docker_container_id:
            raise ValueError("该容器资源没有关联的 Docker 容器，无法停止")
        try:
            client = self._docker_client()
            dc = client.containers.get(container.docker_container_id)
            dc.stop()
        except Exception as exc:
            raise RuntimeError(f"停止容器失败: {exc}") from exc
        return self.inspect_container(user_id, workspace_id, container_id)

    def unregister_container(
        self,
        user_id: str,
        workspace_id: str,
        container_id: str,
    ) -> WorkspaceContainerResource:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        container = self._find_container(workspace_dir, container_id)
        if container is None:
            raise FileNotFoundError(f"容器资源不存在: {container_id}")

        if container.managed and container.docker_container_id:
            try:
                client = self._docker_client()
                dc = client.containers.get(container.docker_container_id)
                dc.remove(force=True)
            except Exception:
                pass

        registry = self._read_registry(workspace_dir)
        remaining: list[dict[str, Any]] = []
        for item in registry.get("containers", []):
            if not isinstance(item, dict):
                continue
            if item.get("container_id") == container_id:
                continue
            remaining.append(item)
        registry["containers"] = remaining
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)
        container.status = "missing"
        container.updated_at = _now_iso()
        return container

    def get_container_logs(
        self,
        user_id: str,
        workspace_id: str,
        container_id: str,
        tail: int = 100,
    ) -> str:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        container = self._find_container(workspace_dir, container_id)
        if container is None:
            raise FileNotFoundError(f"容器资源不存在: {container_id}")
        if not container.docker_container_id:
            raise ValueError("该容器资源没有关联的 Docker 容器，无法获取日志")
        try:
            client = self._docker_client()
            dc = client.containers.get(container.docker_container_id)
            logs = dc.logs(tail=tail, timestamps=False)
            if isinstance(logs, bytes):
                logs = logs.decode("utf-8", errors="replace")
        except Exception as exc:
            raise RuntimeError(f"获取容器日志失败: {exc}") from exc
        return str(logs)

    def is_docker_available(self) -> bool:
        try:
            client = self._docker_client()
            client.ping()
            return True
        except Exception:
            return False

    def _workspace_dir(self, user_id: str, workspace_id: str) -> Path:
        return self.workspace_registry.get_workspace_root(user_id, workspace_id)

    def _registry_path(self, workspace_dir: Path) -> Path:
        env_dir = resolve_workspace_runtime_dir(workspace_dir, create=True)
        return env_dir / _REGISTRY_FILE

    def _read_registry(self, workspace_dir: Path) -> dict[str, Any]:
        path = self._registry_path(workspace_dir)
        if not path.exists():
            return {
                "_schema_version": 1,
                "containers": [],
                "updated_at": None,
            }
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        containers = data.get("containers")
        return {
            "_schema_version": 1,
            "containers": containers if isinstance(containers, list) else [],
            "updated_at": data.get("updated_at"),
        }

    def _write_registry(self, workspace_dir: Path, data: dict[str, Any]) -> None:
        path = self._registry_path(workspace_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _find_container(
        self,
        workspace_dir: Path,
        container_id: str,
    ) -> WorkspaceContainerResource | None:
        registry = self._read_registry(workspace_dir)
        for item in registry.get("containers", []):
            if isinstance(item, dict) and item.get("container_id") == container_id:
                return WorkspaceContainerResource.model_validate(item)
        return None

    def _upsert_container(
        self,
        workspace_dir: Path,
        container: WorkspaceContainerResource,
    ) -> None:
        registry = self._read_registry(workspace_dir)
        containers: list[dict[str, Any]] = []
        found = False
        for item in registry.get("containers", []):
            if not isinstance(item, dict):
                continue
            if item.get("container_id") == container.container_id:
                containers.append(container.model_dump(mode="json"))
                found = True
            else:
                containers.append(item)
        if not found:
            containers.append(container.model_dump(mode="json"))
        registry["containers"] = containers
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

    def _inspect_container(
        self,
        container: WorkspaceContainerResource,
    ) -> WorkspaceContainerResource:
        if not container.docker_container_id and not container.container_name:
            return container
        try:
            client = self._docker_client()
            dc = self._get_docker_container(
                client,
                container_id=container.docker_container_id,
                container_name=container.container_name,
            )
            dc.reload()
            container.docker_container_id = str(dc.id)
            container.container_name = str(getattr(dc, "name", "") or "")
            container_status = str(getattr(dc, "status", "") or "")
            attrs = getattr(dc, "attrs", {}) or {}
            config = attrs.get("Config") or {}
            container.image = container.image or config.get("Image") or ""
            container.managed = bool((config.get("Labels") or {}).get("aiasys.managed") == "true")
            container.status = self._docker_status_to_container_status(container_status)
            container.last_error = None
        except Exception as exc:
            container.status = "missing"
            container.last_error = str(exc)
        return container

    def _docker_client(self):
        import docker

        return docker.from_env()

    def _get_docker_container(
        self,
        client,
        *,
        container_id: str | None = None,
        container_name: str | None = None,
        container_id_or_name: str | None = None,
    ):
        target = (container_id_or_name or container_id or container_name or "").strip()
        if not target:
            raise ValueError("container_id/container_name 不能为空")
        return client.containers.get(target)

    def _docker_status_to_container_status(self, status: str | None) -> str:
        normalized = str(status or "").strip().lower()
        if normalized == "running":
            return "running"
        if normalized in {"created", "exited", "paused", "restarting", "removing", "dead"}:
            return "stopped"
        return "missing"


_container_resource_service: ContainerResourceService | None = None


def get_container_resource_service() -> ContainerResourceService:
    global _container_resource_service
    if _container_resource_service is None:
        _container_resource_service = ContainerResourceService(WORKSPACE_DIR)
    return _container_resource_service
