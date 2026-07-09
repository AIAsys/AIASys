"""工作区运行环境执行适配。

该模块把工作区 runtime_binding 转成工具层可直接消费的执行计划。
Shell、RunCode 和 notebook 运行时都从这里取同一份环境解析结果，避免各自读取不同配置源。
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models.container_resource import WorkspaceContainerResource
from app.models.runtime_environment import WorkspaceRuntimeEnv
from app.services.history import (
    current_env_id,
    current_runtime_env_vars,
    current_runtime_execution_plan,
    current_workspace,
)

logger = logging.getLogger(__name__)


def _shell_quote(arg: str, shell_family: str | None = None) -> str:
    """跨平台 shell 参数引用。

    默认按当前平台推断：Windows 用 PowerShell 单引号规则，POSIX 用 shlex.quote。
    调用方可显式传入 shell_family（posix/powershell/wsl/busybox）以匹配目标解释器，
    避免 uv 包装命令与 docker exec 命令在 Windows 上因解释器不一致而转义错误。
    """
    if shell_family is None:
        shell_family = "powershell" if os.name == "nt" else "posix"
    if shell_family == "powershell":
        return "'" + arg.replace("'", "''") + "'"
    # posix / wsl / busybox 均按 POSIX shell 规则处理
    return shlex.quote(arg)


DEFAULT_SANDBOX_MODE = "plain_shell"
DEFAULT_DISPLAY_NAME = "未绑定 Python"
_DYNAMIC_KERNEL_ROOT = Path(tempfile.gettempdir()) / "aiasys-runtime-kernels"


@dataclass(frozen=True, slots=True)
class RuntimeExecutionPlan:
    sandbox_mode: str
    env_id: str | None
    display_name: str
    workspace: Path | None
    env: WorkspaceRuntimeEnv | None = None
    container_resource: WorkspaceContainerResource | None = None
    env_vars: dict[str, str] | None = None
    frozen: bool = False

    @property
    def kind(self) -> str:
        if self.sandbox_mode == "plain_shell":
            return "plain_shell"
        if self.sandbox_mode == "docker":
            return "docker"
        if self.env is not None:
            return self.env.kind
        return "local"

    @property
    def uv_project_dir(self) -> Path | None:
        if self.env is None or self.env.kind != "uv" or not self.env.material_path:
            return None
        return Path(self.env.material_path)

    @property
    def python_executable(self) -> Path | None:
        if self.env is None or not self.env.python_executable:
            return None
        return Path(self.env.python_executable)


def resolve_runtime_execution_plan(
    *,
    workspace: Path | None = None,
    env_id: str | None = None,
    frozen_plan: RuntimeExecutionPlan | None = None,
) -> RuntimeExecutionPlan:
    """解析当前执行链路的运行环境计划。"""
    if frozen_plan is not None:
        return frozen_plan

    context_plan = current_runtime_execution_plan.get()
    if isinstance(context_plan, RuntimeExecutionPlan):
        return context_plan

    raw_workspace = Path(workspace) if workspace is not None else current_workspace.get()
    resolved_workspace = Path(raw_workspace) if raw_workspace is not None else None
    context_env_id = env_id or current_env_id.get()
    context_env_vars = current_runtime_env_vars.get()

    if resolved_workspace is None:
        return RuntimeExecutionPlan(
            sandbox_mode="local" if context_env_id else DEFAULT_SANDBOX_MODE,
            env_id=context_env_id,
            display_name=DEFAULT_DISPLAY_NAME,
            workspace=None,
            env_vars=context_env_vars,
        )

    workspace_id = resolved_workspace.name
    user_id = _resolve_user_id_from_workspace(resolved_workspace)
    from app.services.workspace_registry import get_workspace_registry_service

    registry = get_workspace_registry_service()

    try:
        workspace_meta = registry.get_workspace(
            user_id,
            workspace_id,
            include_conversations=False,
        )
    except Exception:
        logger.warning("Failed to get workspace metadata", exc_info=True)
        workspace_meta = None

    binding = getattr(workspace_meta, "runtime_binding", None)
    binding_env_id = getattr(binding, "env_id", None)
    binding_sandbox_mode = getattr(binding, "sandbox_mode", None)
    sandbox_mode = _normalize_sandbox_mode(binding_sandbox_mode)
    resolved_env_id = context_env_id or binding_env_id

    if sandbox_mode == "docker":
        if not resolved_env_id:
            return RuntimeExecutionPlan(
                sandbox_mode="docker",
                env_id=None,
                display_name="未绑定 Docker 沙盒",
                workspace=resolved_workspace,
                env_vars=context_env_vars,
            )
        container_resource: WorkspaceContainerResource | None = None
        try:
            from app.services.container_resource import get_container_resource_service

            container_resource = get_container_resource_service().inspect_container(
                user_id,
                workspace_id,
                resolved_env_id,
            )
        except FileNotFoundError:
            container_resource = None
        except Exception:
            logger.warning("Failed to get container resource", exc_info=True)
            container_resource = None

        return RuntimeExecutionPlan(
            sandbox_mode="docker",
            env_id=resolved_env_id,
            display_name=(
                container_resource.name
                if container_resource is not None
                else f"Docker 沙盒 {resolved_env_id}"
            ),
            workspace=resolved_workspace,
            container_resource=container_resource,
            env_vars=context_env_vars,
        )

    env: WorkspaceRuntimeEnv | None = None
    if resolved_env_id:
        try:
            from app.services.runtime_environment import get_runtime_environment_service

            env = get_runtime_environment_service().inspect_env(
                user_id,
                workspace_id,
                resolved_env_id,
            )
        except FileNotFoundError:
            env = None
        except Exception:
            logger.warning("Failed to get runtime environment config", exc_info=True)
            env = None

    if env is not None:
        return RuntimeExecutionPlan(
            sandbox_mode="local",
            env_id=resolved_env_id,
            display_name=env.display_name,
            workspace=resolved_workspace,
            env=env,
            env_vars=context_env_vars,
        )

    return RuntimeExecutionPlan(
        sandbox_mode="local" if resolved_env_id else DEFAULT_SANDBOX_MODE,
        env_id=resolved_env_id,
        display_name=(f"{resolved_env_id} (未找到)" if resolved_env_id else DEFAULT_DISPLAY_NAME),
        workspace=resolved_workspace,
        env=None,
        env_vars=context_env_vars,
    )


def wrap_shell_command_for_runtime(
    command: str,
    *,
    plan: RuntimeExecutionPlan,
) -> tuple[str, Path | None]:
    """按运行环境包装 Shell 命令，返回实际命令与宿主侧 cwd。"""
    if plan.sandbox_mode == "docker":
        container = plan.container_resource
        if container is None:
            raise RuntimeError(f"Docker 沙盒资源不存在: {plan.env_id}")

        docker_target = (
            container.docker_container_id or container.container_name or container.container_id
        )
        if not docker_target:
            raise RuntimeError(f"Docker 沙盒资源没有可执行容器标识: {plan.env_id}")

        workdir = container.workspace_mount_path or "/workspace"
        env_args = _docker_exec_env_args(plan)
        wrapped = (
            f"docker exec -w {_shell_quote(workdir, shell_family='posix')} "
            f"{env_args}"
            f"{_shell_quote(docker_target, shell_family='posix')} sh -lc {_shell_quote(command, shell_family='posix')}"
        )
        return wrapped, plan.workspace

    if plan.env is None:
        return command, plan.workspace

    if plan.env.kind == "uv":
        project_dir = plan.uv_project_dir
        if project_dir is None:
            return command, plan.workspace
        # 兼容性与稳定性兜底：若 UV 项目目录已被删除或缺少 pyproject.toml，
        # 不要强制生成指向不存在目录的 uv run 命令，避免在 Windows 上触发
        # os error 123 等底层路径错误。回退到 plain shell，让调用方看到更
        # 清晰的环境不可用提示。
        if not project_dir.exists() or not (project_dir / "pyproject.toml").exists():
            logger.warning(
                "UV project directory %s does not exist or missing pyproject.toml; "
                "falling back to plain shell",
                project_dir,
            )
            return command, plan.workspace
        # Windows 没有 sh，uv run 会因此失败；改用 powershell -NoProfile -Command。
        # cmd.exe 已禁用，对齐 Copilot 不再使用 cmd。
        if os.name == "nt":
            wrapped = (
                f"uv run --project {_shell_quote(str(project_dir), shell_family='powershell')} "
                f"--directory {_shell_quote(str(plan.workspace or project_dir), shell_family='powershell')} "
                f"powershell -NoProfile -Command {_shell_quote(command, shell_family='powershell')}"
            )
        else:
            wrapped = (
                f"uv run --project {_shell_quote(str(project_dir), shell_family='posix')} "
                f"--directory {_shell_quote(str(plan.workspace or project_dir), shell_family='posix')} "
                f"sh -lc {_shell_quote(command, shell_family='posix')}"
            )
        return wrapped, plan.workspace

    return command, plan.workspace


def build_runtime_shell_env(
    base_env: dict[str, str], *, plan: RuntimeExecutionPlan
) -> dict[str, str]:
    env = dict(base_env)
    if plan.env_vars:
        env.update(plan.env_vars)
    if plan.env_id:
        env["AIASYS_RUNTIME_ENV_ID"] = plan.env_id
    env["AIASYS_RUNTIME_SANDBOX_MODE"] = plan.sandbox_mode
    env["AIASYS_RUNTIME_DISPLAY_NAME"] = plan.display_name
    if plan.workspace is not None:
        env["AIASYS_WORKSPACE_ROOT"] = str(plan.workspace)
    if plan.env is not None:
        env["AIASYS_RUNTIME_ENV_KIND"] = plan.env.kind
        if plan.env.material_path:
            env["AIASYS_RUNTIME_ENV_MATERIAL_PATH"] = plan.env.material_path
        if plan.env.python_executable:
            env["AIASYS_RUNTIME_PYTHON_EXECUTABLE"] = plan.env.python_executable
            python_dir = os.path.dirname(str(plan.env.python_executable))
            env["PATH"] = f"{python_dir}{os.pathsep}{env.get('PATH', '')}"
    if plan.container_resource is not None:
        container = plan.container_resource
        env["AIASYS_RUNTIME_ENV_KIND"] = "docker"
        env["AIASYS_RUNTIME_CONTAINER_ID"] = container.container_id
        env["AIASYS_RUNTIME_WORKSPACE_MOUNT_PATH"] = container.workspace_mount_path or "/workspace"
        if container.docker_container_id:
            env["AIASYS_RUNTIME_DOCKER_CONTAINER_ID"] = container.docker_container_id
        if container.container_name:
            env["AIASYS_RUNTIME_CONTAINER_NAME"] = container.container_name

    # 确保 uv 在 PATH 中：子进程默认可能看不到 uv（桌面版 AIASYS_BUNDLED_UV_PATH、
    # vendor 内置、或用户安装的 uv）。统一走 find_uv_binary() 三层检测链。
    from app.core.uv_utils import find_uv_binary

    uv_bin = find_uv_binary()
    if uv_bin:
        uv_dir = os.path.dirname(str(uv_bin))
        current_path = env.get("PATH", "")
        if uv_dir not in current_path.split(os.pathsep):
            env["PATH"] = f"{current_path}{os.pathsep}{uv_dir}"

    # Windows 中文编码兜底
    if os.name == "nt":
        env.setdefault("PYTHONIOENCODING", "utf-8")
        env.setdefault("LC_ALL", "C.UTF-8")
        env.setdefault("LANG", "C.UTF-8")

    return env


def kernel_name_for_runtime(
    requested_kernel_name: str,
    *,
    plan: RuntimeExecutionPlan,
) -> str:
    if requested_kernel_name != "python3":
        return requested_kernel_name
    if plan.env is None:
        return requested_kernel_name
    if plan.env.kind == "registered_python":
        return ensure_registered_python_kernel_spec(plan)
    if plan.env.kind != "uv":
        return requested_kernel_name
    return ensure_uv_kernel_spec(plan)


def ensure_uv_kernel_spec(plan: RuntimeExecutionPlan) -> str:
    project_dir = plan.uv_project_dir
    if project_dir is None:
        raise RuntimeError("UV 环境缺少 material_path，无法创建 kernel spec")
    if not plan.env_id:
        raise RuntimeError("UV 环境缺少 env_id，无法创建 kernel spec")

    kernel_name = _kernel_name_for_env(plan.env_id)
    spec_dir = _DYNAMIC_KERNEL_ROOT / kernel_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    kernel_json = {
        "argv": [
            "uv",
            "run",
            "--project",
            str(project_dir),
            # kernel 进程的 cwd 也指向 UV 项目目录，避免把工作区根目录当作包搜索路径
            "--directory",
            str(project_dir),
            "--with",
            "ipykernel",
            "python",
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ],
        "display_name": f"AIASys UV ({plan.env_id})",
        "language": "python",
        "metadata": {
            "aiasys": {
                "env_id": plan.env_id,
                "kind": "uv",
                "material_path": str(project_dir),
            }
        },
    }
    target = spec_dir / "kernel.json"
    existing = None
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            existing = None
    if existing != kernel_json:
        target.write_text(
            json.dumps(kernel_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return kernel_name


def ensure_registered_python_kernel_spec(plan: RuntimeExecutionPlan) -> str:
    if not plan.env_id:
        raise RuntimeError("Python 环境缺少 env_id，无法创建 kernel spec")
    python_bin = plan.python_executable
    if python_bin is None:
        raise RuntimeError("Python 环境缺少解释器路径，无法创建 kernel spec")

    kernel_name = _kernel_name_for_registered_python(plan.env_id)
    spec_dir = _DYNAMIC_KERNEL_ROOT / kernel_name
    spec_dir.mkdir(parents=True, exist_ok=True)
    kernel_json = {
        "argv": [
            str(python_bin),
            "-m",
            "ipykernel_launcher",
            "-f",
            "{connection_file}",
        ],
        "display_name": f"AIASys Python ({plan.env_id})",
        "language": "python",
        "metadata": {
            "aiasys": {
                "env_id": plan.env_id,
                "kind": "registered_python",
                "python_executable": str(python_bin),
            }
        },
    }
    target = spec_dir / "kernel.json"
    existing = None
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            existing = None
    if existing != kernel_json:
        target.write_text(
            json.dumps(kernel_json, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    return kernel_name


def runtime_kernel_dirs() -> list[str]:
    _DYNAMIC_KERNEL_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        from jupyter_client.kernelspec import KernelSpecManager

        default_dirs = [
            path for path in KernelSpecManager().kernel_dirs if path != str(_DYNAMIC_KERNEL_ROOT)
        ]
    except Exception:
        default_dirs = []
    return [str(_DYNAMIC_KERNEL_ROOT), *default_dirs]


def plan_for_python_execution(plan: RuntimeExecutionPlan) -> RuntimeExecutionPlan:
    if plan.sandbox_mode == "docker":
        raise RuntimeError(
            "Docker 沙盒当前不支持持久 Notebook/IPython 内核。"
            "请把代码保存为脚本后通过 Shell 或 Monitor 执行，或切回工作区 Python 环境。"
        )
    if plan.env is None and plan.env_id is None:
        raise RuntimeError(
            "当前工作区未启用 Python 环境。"
            "调用 RuntimeEnvironment(action='ensure_uv', activate=true) 可自动创建并绑定默认 Python 环境，"
            "然后重试代码执行。"
        )
    if plan.env is None:
        raise RuntimeError(
            f"当前工作区绑定的 Python 环境不可用: {plan.env_id}。请重新启用或修复 Python 环境。"
        )
    return plan


def runtime_summary(plan: RuntimeExecutionPlan) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "sandbox_mode": plan.sandbox_mode,
        "env_id": plan.env_id,
        "display_name": plan.display_name,
        "kind": plan.kind,
    }
    if plan.env is not None:
        payload["status"] = plan.env.status
        payload["material_path"] = plan.env.material_path
    if plan.container_resource is not None:
        payload["status"] = plan.container_resource.status
        payload["container_id"] = plan.container_resource.container_id
        payload["docker_container_id"] = plan.container_resource.docker_container_id
        payload["container_name"] = plan.container_resource.container_name
        payload["workspace_mount_path"] = plan.container_resource.workspace_mount_path
    if plan.frozen:
        payload["frozen"] = True
    return payload


def _resolve_user_id_from_workspace(workspace: Path) -> str:
    parts = workspace.resolve().parts
    for index, part in enumerate(parts):
        if part == "workspaces" and index + 1 < len(parts):
            return parts[index + 1]
    return "local_default"


def _normalize_sandbox_mode(value: str | None) -> str:
    text = str(value or "").strip().lower()
    return text or DEFAULT_SANDBOX_MODE


def _docker_exec_env_args(plan: RuntimeExecutionPlan) -> str:
    env_vars = {
        "AIASYS_RUNTIME_SANDBOX_MODE": plan.sandbox_mode,
        "AIASYS_RUNTIME_DISPLAY_NAME": plan.display_name,
        **(plan.env_vars or {}),
    }
    if plan.env_id:
        env_vars["AIASYS_RUNTIME_ENV_ID"] = plan.env_id
    if plan.container_resource is not None:
        env_vars["AIASYS_WORKSPACE_ROOT"] = (
            plan.container_resource.workspace_mount_path or "/workspace"
        )
        env_vars["AIASYS_RUNTIME_WORKSPACE_MOUNT_PATH"] = (
            plan.container_resource.workspace_mount_path or "/workspace"
        )
    parts: list[str] = []
    for key, value in env_vars.items():
        if value is None:
            continue
        key_text = str(key).strip()
        if not key_text or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key_text):
            continue
        parts.append(
            f"-e {_shell_quote(key_text, shell_family='posix')}={_shell_quote(str(value), shell_family='posix')}"
        )
    return "".join(f"{part} " for part in parts)


def _kernel_name_for_env(env_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", env_id).strip("-").lower()
    return f"aiasys-uv-{normalized or 'workspace'}"


def _kernel_name_for_registered_python(env_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", env_id).strip("-").lower()
    return f"aiasys-python-{normalized or 'registered'}"
