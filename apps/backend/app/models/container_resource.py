"""容器资源登记模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ContainerResourceStatus = Literal["running", "stopped", "created", "missing", "error"]


class WorkspaceContainerResource(BaseModel):
    container_id: str
    name: str
    image: str
    docker_container_id: str | None = None
    container_name: str | None = None
    status: ContainerResourceStatus = "created"
    workspace_mount_path: str = "/workspace"
    command: str | None = None
    ports: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    managed: bool = False
    auto_start: bool = False
    created_at: str
    updated_at: str
    last_error: str | None = None


class WorkspaceContainerResourceRegistry(BaseModel):
    workspace_id: str
    containers: list[WorkspaceContainerResource]
    docker_available: bool
    total: int


class ContainerResourceActionResponse(BaseModel):
    workspace_id: str
    container: WorkspaceContainerResource
    refresh_required: bool = False


class ContainerLogsResponse(BaseModel):
    container_id: str
    logs: str


class RegisterContainerRequest(BaseModel):
    container_id: str | None = Field(default=None, max_length=80)
    name: str | None = Field(default=None, max_length=120)
    image: str | None = Field(default=None, max_length=300)
    container_id_or_name: str | None = Field(default=None, max_length=180)
    workspace_mount_path: str = Field(default="/workspace", min_length=1, max_length=200)
    command: str | None = None
    ports: dict[str, str] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    labels: dict[str, str] = Field(default_factory=dict)
    create_container: bool = False
    auto_start: bool = False
