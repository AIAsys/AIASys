"""工作区运行环境登记模型。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

RuntimeEnvironmentKind = Literal["uv", "registered_python"]
RuntimeEnvironmentStatus = Literal[
    "registered",
    "ready",
    "running",
    "stopped",
    "missing",
    "unavailable",
    "error",
]


class RuntimeEnvCommandResult(BaseModel):
    ok: bool
    command: list[str] = Field(default_factory=list)
    cwd: str | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


class RuntimeEnvPackage(BaseModel):
    name: str
    version: str


class WorkspaceRuntimeEnv(BaseModel):
    env_id: str
    kind: RuntimeEnvironmentKind
    display_name: str
    status: RuntimeEnvironmentStatus = "registered"
    active: bool = False

    material_path: str | None = None
    python_version: str | None = None
    python_executable: str | None = None
    package_count: int = 0
    packages: list[RuntimeEnvPackage] = Field(default_factory=list)

    created_at: str | None = None
    updated_at: str | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceRuntimeEnvRegistryResponse(BaseModel):
    workspace_id: str
    default_env_id: str | None = None
    active_env_id: str | None = None
    registry_path: str
    uv_available: bool
    envs: list[WorkspaceRuntimeEnv] = Field(default_factory=list)
    total: int = 0


class EnsureWorkspaceUvEnvRequest(BaseModel):
    env_id: str = Field(default="workspace-default", min_length=1, max_length=80)
    display_name: str = Field(default="Workspace UV", min_length=1, max_length=120)
    python_version: str | None = Field(default=None, max_length=40)
    packages: list[str] = Field(default_factory=list)
    create_venv: bool = False
    sync: bool = False

    @field_validator("packages")
    @classmethod
    def _normalize_packages(cls, value: list[str]) -> list[str]:
        return _dedupe_non_empty(value)


class RegisterWorkspacePythonEnvRequest(BaseModel):
    env_id: str | None = Field(default=None, min_length=1, max_length=80)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    python_executable: str = Field(min_length=1, max_length=1000)
    source_kernel_name: str | None = Field(default=None, max_length=120)
    activate: bool = False


class InstallWorkspacePackagesRequest(BaseModel):
    env_id: str = Field(default="workspace-default", min_length=1, max_length=80)
    packages: list[str] = Field(min_length=1)
    sync: bool = True

    @field_validator("packages")
    @classmethod
    def _normalize_packages(cls, value: list[str]) -> list[str]:
        packages = _dedupe_non_empty(value)
        if not packages:
            raise ValueError("packages 不能为空")
        return packages


class BindWorkspaceRuntimeEnvRequest(BaseModel):
    env_id: str = Field(min_length=1, max_length=80)


class RuntimeEnvActionResponse(BaseModel):
    workspace_id: str
    env: WorkspaceRuntimeEnv
    refresh_required: bool = False
    command_result: RuntimeEnvCommandResult | None = None


class WorkspaceRuntimeEnvInspectionResponse(BaseModel):
    workspace_id: str
    env: WorkspaceRuntimeEnv
    registry_path: str
    material_files: dict[str, bool] = Field(default_factory=dict)


def _dedupe_non_empty(items: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        normalized.append(text)
        seen.add(text)
    return normalized
