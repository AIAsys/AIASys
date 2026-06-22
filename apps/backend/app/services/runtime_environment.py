"""工作区 UV 运行环境登记服务。"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.core.subprocess_utils import subprocess_kwargs
from app.utils.path_utils import as_system_path

if TYPE_CHECKING:
    from app.services.workspace_registry import WorkspaceRegistryService

from app.core.config import WORKSPACE_DIR
from app.core.encoding_utils import smart_decode
from app.models.runtime_environment import (
    RuntimeEnvCommandResult,
    RuntimeEnvPackage,
    WorkspaceRuntimeEnv,
    WorkspaceRuntimeEnvRegistryResponse,
)
from app.models.workspace import ExecutionResourceGroup, WorkspaceRuntimeBinding

logger = logging.getLogger(__name__)


DEFAULT_UV_ENV_ID = "workspace-default"
WORKSPACE_RUNTIME_DIR_NAME = ".env"
_REGISTRY_FILE = "environments.json"
_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")
_PYPROJECT_TEMPLATE = """[project]
name = "{project_name}"
version = "0.1.0"
description = "AIASys workspace Python environment"
requires-python = "{requires_python}"
dependencies = [
]

[tool.uv]
package = false
"""


def _now_iso() -> str:
    return datetime.now().isoformat()


def _ensure_valid_id(value: str, field_name: str) -> None:
    if not value or not _ID_PATTERN.match(value):
        raise ValueError(f"无效的 {field_name}")


def _normalize_env_id(value: str | None, fallback: str) -> str:
    text = str(value or "").strip()
    if not text:
        text = fallback
    _ensure_valid_id(text, "env_id")
    return text


def _safe_tail(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


# 危险字符：可能引发 shell 注入或破坏命令行解析
_INVALID_PACKAGE_CHARS = set(";|&$`\"'\n\r\x00")


def _validate_package_names(packages: list[str]) -> None:
    """校验 UV 依赖包名/版本规范，防止命令行选项注入或 shell 元字符注入。"""
    for package in packages:
        if not package or not isinstance(package, str):
            raise ValueError("依赖包名不能为空")
        # uv add 会把以 '-' 开头的参数识别为选项，必须拒绝
        if package.startswith("-"):
            raise ValueError(f"非法的依赖包名（不能以 '-' 开头）: {package}")
        if any(ch in _INVALID_PACKAGE_CHARS for ch in package):
            raise ValueError(f"非法的依赖包名（包含危险字符）: {package}")


def _python_bin_for_venv(venv_dir: Path) -> Path:
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def resolve_workspace_runtime_dir(workspace_dir: Path, *, create: bool = False) -> Path:
    runtime_dir = workspace_dir / WORKSPACE_RUNTIME_DIR_NAME
    if create:
        os.makedirs(as_system_path(runtime_dir), exist_ok=True)
    return runtime_dir


def _normalize_registered_env_id(value: str | None, python_executable: str) -> str:
    text = str(value or "").strip()
    if not text:
        stem = Path(python_executable).parent.name or Path(python_executable).stem or "python"
        text = f"python-{stem}"
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", text).strip("-").lower()
    if not text:
        text = "python"
    return _normalize_env_id(text, "python")


def _requires_python_spec(python_version: str | None) -> str:
    text = str(python_version or "").strip()
    if not text:
        return f">={sys.version_info.major}.{sys.version_info.minor}"
    if any(operator in text for operator in ("<", ">", "=", "!", "~", "*")):
        return text
    return f">={text}"


class RuntimeEnvironmentService:
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

    def list_workspace_envs(
        self,
        user_id: str,
        workspace_id: str,
        *,
        inspect: bool = True,
    ) -> WorkspaceRuntimeEnvRegistryResponse:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        registry = self._read_registry(workspace_dir)
        envs = [
            (
                self._inspect_env(workspace_dir, env)
                if inspect
                else WorkspaceRuntimeEnv.model_validate(env)
            )
            for env in registry.get("envs", [])
            if isinstance(env, dict)
        ]
        envs.sort(key=lambda item: (0 if item.active else 1, item.kind, item.env_id))
        return WorkspaceRuntimeEnvRegistryResponse(
            workspace_id=workspace_id,
            default_env_id=registry.get("default_env_id"),
            active_env_id=registry.get("active_env_id"),
            registry_path=str(self._registry_path(workspace_dir)),
            uv_available=self.is_uv_available(),
            envs=envs,
            total=len(envs),
        )

    def ensure_uv_env(
        self,
        user_id: str,
        workspace_id: str,
        *,
        env_id: str = DEFAULT_UV_ENV_ID,
        display_name: str = "Workspace UV",
        python_version: str | None = None,
        packages: list[str] | None = None,
        create_venv: bool = False,
        sync: bool = False,
    ) -> tuple[WorkspaceRuntimeEnv, RuntimeEnvCommandResult | None]:
        if not self.is_uv_available():
            # uv 缺失时自动安装，避免用户手动操作
            from app.core.uv_utils import install_uv, is_desktop_mode

            installer_mirror = ""
            try:
                from app.core.aiasys_config import load_aiasys_config

                cfg = load_aiasys_config(user_id)
                installer_mirror = cfg.uv.installer_mirror
            except Exception:
                pass

            ok, path, version, message = install_uv(installer_mirror=installer_mirror or None)
            if not ok:
                if is_desktop_mode():
                    raise RuntimeError(
                        f"uv CLI 不可用且自动安装失败，无法创建工作区 UV 环境。错误: {message}"
                    )
                else:
                    raise RuntimeError(
                        f"uv CLI 不可用且自动安装失败，无法创建工作区 UV 环境。"
                        f"错误: {message}"
                        f"建议管理员在服务器上预装 uv（curl -LsSf https://astral.sh/uv/install.sh | sh）。"
                    )

        env_id = _normalize_env_id(env_id, DEFAULT_UV_ENV_ID)
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env_dir = self._env_dir(workspace_dir)
        os.makedirs(as_system_path(env_dir), exist_ok=True)
        now = _now_iso()

        pyproject_path = env_dir / "pyproject.toml"
        if not os.path.exists(as_system_path(pyproject_path)):
            requires_python = _requires_python_spec(python_version)
            Path(as_system_path(pyproject_path)).write_text(
                _PYPROJECT_TEMPLATE.format(
                    project_name=self._project_name(workspace_id),
                    requires_python=requires_python,
                ),
                encoding="utf-8",
            )

        if python_version:
            Path(as_system_path(env_dir / ".python-version")).write_text(
                f"{python_version.strip()}\n",
                encoding="utf-8",
            )

        if packages:
            _validate_package_names(packages)
        result: RuntimeEnvCommandResult | None = None
        if packages:
            result = self._run_uv(
                ["uv", "add", "--no-sync", *packages],
                cwd=env_dir,
            )
            if not result.ok:
                raise RuntimeError(result.stderr or result.error or "uv add 失败")

        if create_venv or sync:
            result = self._run_uv(["uv", "sync"], cwd=env_dir)
            if not result.ok:
                raise RuntimeError(result.stderr or result.error or "uv sync 失败")

        existing = self._find_env(workspace_dir, env_id)
        env = WorkspaceRuntimeEnv(
            env_id=env_id,
            kind="uv",
            display_name=display_name.strip() or "Workspace UV",
            status="registered",
            active=bool(existing.active if existing else False),
            material_path=str(env_dir),
            python_version=python_version or self._read_python_version(env_dir),
            python_executable=str(_python_bin_for_venv(env_dir / ".venv")),
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                **(existing.metadata if existing else {}),
                "manager": "uv",
                "pyproject": str(pyproject_path),
            },
        )
        inspected = self._inspect_uv_env(workspace_dir, env)
        self._upsert_env(workspace_dir, inspected)
        return inspected, result

    def install_workspace_packages(
        self,
        user_id: str,
        workspace_id: str,
        *,
        env_id: str,
        packages: list[str],
        sync: bool = True,
    ) -> tuple[WorkspaceRuntimeEnv, RuntimeEnvCommandResult]:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        existing = self._find_env(workspace_dir, env_id)
        if existing is not None and existing.kind != "uv":
            raise ValueError(f"环境不是工作区 UV，不能用 uv 安装依赖: {env_id}")
        env, _ = self.ensure_uv_env(
            user_id,
            workspace_id,
            env_id=env_id,
            display_name=existing.display_name if existing else "Workspace UV",
            packages=[],
            create_venv=False,
            sync=False,
        )
        env_dir = self._env_dir(workspace_dir)
        _validate_package_names(packages)
        command = ["uv", "add", *packages]
        if not sync:
            command.insert(2, "--no-sync")
        result = self._run_uv(command, cwd=env_dir)
        if not result.ok:
            raise RuntimeError(result.stderr or result.error or "uv add 失败")
        inspected = self._inspect_uv_env(workspace_dir, env)
        self._upsert_env(workspace_dir, inspected)
        return inspected, result

    def register_python_env(
        self,
        user_id: str,
        workspace_id: str,
        *,
        python_executable: str,
        env_id: str | None = None,
        display_name: str | None = None,
        source_kernel_name: str | None = None,
    ) -> WorkspaceRuntimeEnv:
        executable = str(python_executable or "").strip()
        if not executable:
            raise ValueError("Python 解释器路径不能为空")
        executable_path = Path(executable).expanduser()
        if not executable_path.is_absolute():
            raise ValueError("Python 解释器路径必须是完整绝对路径")
        if not executable_path.is_file():
            raise FileNotFoundError(f"Python 解释器不存在: {executable}")

        normalized_env_id = _normalize_registered_env_id(env_id, str(executable_path))
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        existing = self._find_env(workspace_dir, normalized_env_id)
        now = _now_iso()
        env = WorkspaceRuntimeEnv(
            env_id=normalized_env_id,
            kind="registered_python",
            display_name=(
                str(display_name or "").strip()
                or (
                    f"Python ({source_kernel_name})" if source_kernel_name else executable_path.name
                )
            ),
            status="registered",
            active=bool(existing.active if existing else False),
            material_path=str(executable_path.parent),
            python_version=self._detect_python_version(executable_path),
            python_executable=str(executable_path),
            created_at=existing.created_at if existing else now,
            updated_at=now,
            metadata={
                **(existing.metadata if existing else {}),
                "source": "registered_python",
                "source_kernel_name": source_kernel_name,
            },
        )
        inspected = self._inspect_registered_python_env(env)
        self._upsert_env(workspace_dir, inspected)
        return inspected

    def inspect_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> WorkspaceRuntimeEnv:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env = self._find_env(workspace_dir, env_id)
        if env is None:
            raise FileNotFoundError(f"环境不存在: {env_id}")
        inspected = self._inspect_env(workspace_dir, env.model_dump(mode="json"))
        self._upsert_env(workspace_dir, inspected)
        return inspected

    def bind_workspace_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> WorkspaceRuntimeEnv:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        env = self.inspect_env(user_id, workspace_id, env_id)
        workspace = self.workspace_registry.get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
        current_binding = workspace.runtime_binding
        registry = self._read_registry(workspace_dir)
        registry["active_env_id"] = env.env_id
        updated_envs = []
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item["active"] = item.get("env_id") == env.env_id
            updated_envs.append(item)
        registry["envs"] = updated_envs
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

        # 保留已有的 Node/Docker 资源，只更新 Python
        updated_resources = ExecutionResourceGroup(
            python_env_id=env.env_id,
            node_env_id=current_binding.resources.node_env_id,
            docker_resource_id=current_binding.resources.docker_resource_id,
        )
        self.workspace_registry.update_workspace(
            user_id=user_id,
            workspace_id=workspace_id,
            runtime_binding=WorkspaceRuntimeBinding(
                env_vars=current_binding.env_vars,
                resources=updated_resources,
            ),
        )
        env.active = True
        return env

    def unregister_workspace_env(
        self,
        user_id: str,
        workspace_id: str,
        env_id: str,
    ) -> WorkspaceRuntimeEnv:
        workspace_dir = self._workspace_dir(user_id, workspace_id)
        registry = self._read_registry(workspace_dir)
        removed_env: WorkspaceRuntimeEnv | None = None
        remaining_envs: list[dict[str, Any]] = []
        was_active = registry.get("active_env_id") == env_id

        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            if item.get("env_id") == env_id:
                removed_env = WorkspaceRuntimeEnv.model_validate(item)
                was_active = was_active or removed_env.active
                continue
            remaining_envs.append(item)

        if removed_env is None:
            raise FileNotFoundError(f"环境不存在: {env_id}")

        if was_active:
            for item in remaining_envs:
                item["active"] = False
            registry["active_env_id"] = None

            workspace = self.workspace_registry.get_workspace(
                user_id,
                workspace_id,
                include_conversations=False,
            )
            current_binding = workspace.runtime_binding
            # 解绑 Python 时保留 Node/Docker 资源
            updated_resources = ExecutionResourceGroup(
                python_env_id=None,
                node_env_id=current_binding.resources.node_env_id,
                docker_resource_id=current_binding.resources.docker_resource_id,
            )
            self.workspace_registry.update_workspace(
                user_id=user_id,
                workspace_id=workspace_id,
                runtime_binding=WorkspaceRuntimeBinding(
                    env_vars=current_binding.env_vars,
                    resources=updated_resources,
                ),
            )
        elif registry.get("active_env_id") == env_id:
            registry["active_env_id"] = None

        registry["envs"] = remaining_envs
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

        removed_env.active = False
        removed_env.updated_at = _now_iso()
        return removed_env

    def is_uv_available(self) -> bool:
        from app.core.uv_utils import find_uv_binary

        return find_uv_binary() is not None

    def _workspace_dir(self, user_id: str, workspace_id: str) -> Path:
        return self.workspace_registry.get_workspace_root(user_id, workspace_id)

    def _env_dir(self, workspace_dir: Path) -> Path:
        return resolve_workspace_runtime_dir(workspace_dir, create=True)

    def _env_dir_path(self, workspace_dir: Path) -> Path:
        return resolve_workspace_runtime_dir(workspace_dir)

    def _registry_path(self, workspace_dir: Path) -> Path:
        return self._env_dir_path(workspace_dir) / _REGISTRY_FILE

    def _read_registry(self, workspace_dir: Path) -> dict[str, Any]:
        path = self._registry_path(workspace_dir)
        if not os.path.exists(as_system_path(path)):
            return {
                "_schema_version": 1,
                "default_env_id": DEFAULT_UV_ENV_ID,
                "active_env_id": None,
                "envs": [],
                "updated_at": None,
            }
        try:
            data = json.loads(Path(as_system_path(path)).read_text(encoding="utf-8"))
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        envs = data.get("envs")
        return {
            "_schema_version": 1,
            "default_env_id": data.get("default_env_id") or DEFAULT_UV_ENV_ID,
            "active_env_id": data.get("active_env_id"),
            "envs": envs if isinstance(envs, list) else [],
            "updated_at": data.get("updated_at"),
        }

    def _write_registry(self, workspace_dir: Path, data: dict[str, Any]) -> None:
        path = self._registry_path(workspace_dir)
        os.makedirs(as_system_path(path.parent), exist_ok=True)
        Path(as_system_path(path)).write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _find_env(self, workspace_dir: Path, env_id: str) -> WorkspaceRuntimeEnv | None:
        registry = self._read_registry(workspace_dir)
        for item in registry.get("envs", []):
            if isinstance(item, dict) and item.get("env_id") == env_id:
                return WorkspaceRuntimeEnv.model_validate(item)
        return None

    def _upsert_env(self, workspace_dir: Path, env: WorkspaceRuntimeEnv) -> None:
        registry = self._read_registry(workspace_dir)
        envs = []
        found = False
        for item in registry.get("envs", []):
            if not isinstance(item, dict):
                continue
            if item.get("env_id") == env.env_id:
                envs.append(env.model_dump(mode="json"))
                found = True
            else:
                envs.append(item)
        if not found:
            envs.append(env.model_dump(mode="json"))
        registry["envs"] = envs
        registry["default_env_id"] = registry.get("default_env_id") or env.env_id
        if env.active:
            registry["active_env_id"] = env.env_id
        registry["updated_at"] = _now_iso()
        self._write_registry(workspace_dir, registry)

    def _inspect_env(self, workspace_dir: Path, payload: dict[str, Any]) -> WorkspaceRuntimeEnv:
        env = WorkspaceRuntimeEnv.model_validate(payload)
        if env.kind == "registered_python":
            return self._inspect_registered_python_env(env)
        return self._inspect_uv_env(workspace_dir, env)

    def _inspect_uv_env(self, workspace_dir: Path, env: WorkspaceRuntimeEnv) -> WorkspaceRuntimeEnv:
        env_dir = self._env_dir_path(workspace_dir)
        pyproject = env_dir / "pyproject.toml"
        lock_file = env_dir / "uv.lock"
        python_file = env_dir / ".python-version"
        venv_dir = env_dir / ".venv"
        python_bin = _python_bin_for_venv(venv_dir)
        packages = (
            self._list_uv_packages(python_bin) if os.path.exists(as_system_path(python_bin)) else []
        )
        env.material_path = str(env_dir)
        env.python_version = self._read_python_version(env_dir) or env.python_version
        env.python_executable = str(python_bin)
        env.package_count = len(packages)
        env.packages = packages
        env.status = (
            "ready"
            if os.path.exists(as_system_path(pyproject))
            and os.path.exists(as_system_path(python_bin))
            else "registered"
        )
        env.metadata = {
            **env.metadata,
            "pyproject_exists": os.path.exists(as_system_path(pyproject)),
            "lock_exists": os.path.exists(as_system_path(lock_file)),
            "python_version_file_exists": os.path.exists(as_system_path(python_file)),
            "venv_exists": os.path.exists(as_system_path(venv_dir)),
        }
        return env

    def _inspect_registered_python_env(self, env: WorkspaceRuntimeEnv) -> WorkspaceRuntimeEnv:
        executable_text = str(env.python_executable or "").strip()
        executable = Path(executable_text) if executable_text else None
        executable_exists = bool(executable and executable.is_file())
        packages = (
            self._list_python_packages(executable) if executable_exists and executable else []
        )
        env.material_path = (
            str(executable.parent) if executable_exists and executable else env.material_path
        )
        env.python_executable = (
            str(executable) if executable_exists and executable else env.python_executable
        )
        env.python_version = self._detect_python_version(executable) or env.python_version
        env.package_count = len(packages)
        env.packages = packages
        env.status = "ready" if executable_exists else "missing"
        env.metadata = {
            **env.metadata,
            "executable_exists": executable_exists,
        }
        return env

    def _run_uv(self, command: list[str], *, cwd: Path) -> RuntimeEnvCommandResult:
        env = dict(os.environ)
        env.setdefault("UV_CACHE_DIR", os.path.join(tempfile.gettempdir(), "uv-cache"))

        # 确保 uv 可执行文件的目录在 PATH 中，避免桌面模式下后端 PATH 被截断
        from app.core.uv_utils import find_uv_binary

        uv_binary = find_uv_binary()
        if uv_binary:
            uv_dir = str(Path(uv_binary).parent)
            path_env = env.get("PATH", "")
            # 避免重复添加
            if uv_dir not in path_env.split(os.pathsep):
                env["PATH"] = uv_dir + os.pathsep + path_env if path_env else uv_dir
            # 使用完整路径调用 uv，确保在受限 PATH 下也能执行
            command = [uv_binary] + command[1:]

        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                env=env,
                capture_output=True,
                timeout=300,
                check=False,
                **subprocess_kwargs(),
            )
        except Exception as exc:
            return RuntimeEnvCommandResult(
                ok=False,
                command=command,
                cwd=str(cwd),
                error=str(exc),
            )
        return RuntimeEnvCommandResult(
            ok=completed.returncode == 0,
            command=command,
            cwd=str(cwd),
            returncode=completed.returncode,
            stdout=_safe_tail(smart_decode(completed.stdout or b"")),
            stderr=_safe_tail(smart_decode(completed.stderr or b"")),
        )

    def _list_uv_packages(self, python_bin: Path) -> list[RuntimeEnvPackage]:
        return self._list_python_packages(python_bin)

    def _list_python_packages(self, python_bin: Path) -> list[RuntimeEnvPackage]:
        packages = self._list_python_packages_with_pip(python_bin)
        if packages:
            return packages
        return self._list_python_packages_with_metadata(python_bin)

    def _list_python_packages_with_pip(self, python_bin: Path) -> list[RuntimeEnvPackage]:
        try:
            completed = subprocess.run(
                [str(python_bin), "-m", "pip", "list", "--format=json"],
                capture_output=True,
                timeout=30,
                check=False,
                **subprocess_kwargs(),
            )
        except Exception:
            return []
        if completed.returncode != 0:
            return []
        try:
            data = json.loads(smart_decode(completed.stdout or b"[]"))
        except Exception:
            return []
        packages = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                version = str(item.get("version") or "").strip()
                if name:
                    packages.append(RuntimeEnvPackage(name=name, version=version))
        packages.sort(key=lambda item: item.name.lower())
        return packages

    def _list_python_packages_with_metadata(self, python_bin: Path) -> list[RuntimeEnvPackage]:
        script = """
import importlib.metadata as metadata
import json

packages = []
for dist in metadata.distributions():
    name = dist.metadata.get("Name") or getattr(dist, "name", "")
    version = dist.version or ""
    if name:
        packages.append({"name": name, "version": version})
packages.sort(key=lambda item: item["name"].lower())
print(json.dumps(packages))
"""
        try:
            completed = subprocess.run(
                [str(python_bin), "-c", script],
                capture_output=True,
                timeout=30,
                check=False,
                **subprocess_kwargs(),
            )
        except Exception:
            return []
        if completed.returncode != 0:
            return []
        try:
            data = json.loads(smart_decode(completed.stdout or b"[]"))
        except Exception:
            return []
        packages = []
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                version = str(item.get("version") or "").strip()
                if name:
                    packages.append(RuntimeEnvPackage(name=name, version=version))
        packages.sort(key=lambda item: item.name.lower())
        return packages

    def _detect_python_version(self, python_bin: Path) -> str | None:
        try:
            completed = subprocess.run(
                [
                    str(python_bin),
                    "-c",
                    "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')",
                ],
                capture_output=True,
                timeout=10,
                check=False,
                **subprocess_kwargs(),
            )
        except Exception:
            return None
        if completed.returncode != 0:
            return None
        return smart_decode(completed.stdout or b"").strip() or None

    def _read_python_version(self, env_dir: Path) -> str | None:
        version_file = env_dir / ".python-version"
        if not os.path.exists(as_system_path(version_file)):
            return None
        text = Path(as_system_path(version_file)).read_text(encoding="utf-8").strip()
        return text or None

    def _project_name(self, workspace_id: str) -> str:
        normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", workspace_id).strip("-").lower()
        return f"aiasys-workspace-{normalized or 'env'}"


_runtime_environment_service: RuntimeEnvironmentService | None = None


def get_runtime_environment_service() -> RuntimeEnvironmentService:
    global _runtime_environment_service
    if _runtime_environment_service is None:
        _runtime_environment_service = RuntimeEnvironmentService(WORKSPACE_DIR)
    return _runtime_environment_service
