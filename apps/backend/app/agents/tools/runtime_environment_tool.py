"""工作区运行环境管理工具。"""

from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.core.agent_tool import AiasysTool
from app.core.tool_result import ToolResult
from app.services.history import current_session_id, current_user_id, current_workspace
from app.services.runtime_environment import (
    DEFAULT_UV_ENV_ID,
    get_runtime_environment_service,
)

logger = logging.getLogger(__name__)

RuntimeEnvironmentAction = Literal[
    "list",
    "ensure_uv",
    "register_python",
    "install_packages",
    "bind",
    "inspect",
    "unregister",
]


def _split_text_items(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", "\n").splitlines() if item.strip()]


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _split_text_items(value)
    if isinstance(value, list):
        normalized: list[str] = []
        seen: set[str] = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            normalized.append(text)
            seen.add(text)
        return normalized
    return [str(value).strip()] if str(value).strip() else []


class RuntimeEnvironmentParams(BaseModel):
    action: RuntimeEnvironmentAction = Field(
        description=(
            "操作类型：list 列出环境，ensure_uv 创建或刷新 UV 环境，"
            "register_python 登记已有 Python 解释器，install_packages 安装 UV 依赖，bind 设为工作区默认环境，"
            "inspect 检查单个环境，unregister 从工作区取消登记。"
        )
    )
    workspace_id: str | None = Field(
        default=None,
        description="目标工作区 ID。默认根据当前会话解析。",
    )
    env_id: str | None = Field(
        default=None,
        description="环境 ID。UV 默认 workspace-default；bind/inspect 需要提供。",
    )
    display_name: str | None = Field(
        default=None,
        description="用户可见的环境名称。",
    )
    inspect: bool = Field(
        default=True,
        description="list 时是否刷新登记环境状态。",
    )
    activate: bool = Field(
        default=False,
        description="ensure_uv 成功后是否立即设为工作区默认环境。",
    )

    python_version: str | None = Field(
        default=None,
        description="UV 环境 Python 版本，例如 3.11。",
    )
    python_executable: str | None = Field(
        default=None,
        description="register_python 时登记的 Python 可执行文件完整路径。",
    )
    source_kernel_name: str | None = Field(
        default=None,
        description="register_python 时可记录来源 kernel 名称。",
    )
    packages: list[str] = Field(
        default_factory=list,
        description="UV 依赖包列表，可用数组或换行字符串传入。",
    )
    create_venv: bool = Field(
        default=False,
        description="ensure_uv 时是否执行 uv sync 创建 .venv。",
    )
    sync: bool = Field(
        default=False,
        description="ensure_uv/install_packages 后是否同步依赖。",
    )

    @field_validator("packages", mode="before")
    @classmethod
    def _normalize_packages(cls, value: Any) -> list[str]:
        return _normalize_string_list(value)


def _json_result(payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
    )


def _error_result(message: str) -> ToolResult:
    return ToolResult(content=message, is_error=True)


def _resolve_workspace_scope(
    ctx: dict[str, Any] | None,
    workspace_id: str | None,
) -> tuple[str, str] | str:
    service = get_runtime_environment_service()
    context = ctx or {}
    user_id = str(context.get("user_id") or current_user_id.get() or "").strip()
    if not user_id:
        return "当前工具上下文缺少 user_id，无法管理工作区运行环境。"

    explicit_workspace_id = str(workspace_id or "").strip()
    if explicit_workspace_id:
        service.workspace_registry.get_workspace(
            user_id,
            explicit_workspace_id,
            include_conversations=False,
        )
        return user_id, explicit_workspace_id

    session_id = str(context.get("session_id") or current_session_id.get() or "").strip()
    if session_id:
        resolved = service.workspace_registry.find_workspace_id_by_session_id(
            user_id,
            session_id,
        )
        if resolved:
            return user_id, resolved

    workspace_path = context.get("workspace") or current_workspace.get()
    if workspace_path is not None:
        candidate = Path(str(workspace_path)).name
        if candidate:
            service.workspace_registry.get_workspace(
                user_id,
                candidate,
                include_conversations=False,
            )
            return user_id, candidate

    return "当前会话没有绑定可解析的工作区，无法管理运行环境。"


class RuntimeEnvironment(AiasysTool):
    """管理当前工作区登记的 UV 运行环境。"""

    name: str = "RuntimeEnvironment"
    description: str = """管理当前工作区的 UV 运行环境。

可执行操作：
- list：列出当前工作区登记的运行环境，并检查 UV CLI 是否可用
- ensure_uv：创建或刷新工作区 UV 环境，可写入 pyproject.toml、.python-version，并可安装依赖
- register_python：把已登记或本机可用 Python 解释器登记到当前工作区
- install_packages：给已登记 UV 环境安装依赖
- bind：把已登记环境设为工作区默认执行环境
- inspect：检查单个登记环境状态
- unregister：从当前工作区取消登记

边界：
- 不会修改 AIASys 后端自身 Python 环境
- 新绑定的运行环境从下一轮执行或重置执行环境后生效
"""
    params: type[BaseModel] = RuntimeEnvironmentParams

    async def invoke(
        self,
        ctx: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        params = RuntimeEnvironmentParams.model_validate(kwargs)
        try:
            scope = _resolve_workspace_scope(ctx, params.workspace_id)
            if isinstance(scope, str):
                return _error_result(scope)
            user_id, workspace_id = scope
            service = get_runtime_environment_service()

            if params.action == "list":
                registry = service.list_workspace_envs(
                    user_id,
                    workspace_id,
                    inspect=params.inspect,
                )
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "registry": registry.model_dump(mode="json"),
                    }
                )

            if params.action == "ensure_uv":
                env, command_result = service.ensure_uv_env(
                    user_id,
                    workspace_id,
                    env_id=params.env_id or DEFAULT_UV_ENV_ID,
                    display_name=params.display_name or "Workspace UV",
                    python_version=params.python_version,
                    packages=params.packages,
                    create_venv=params.create_venv,
                    sync=params.sync,
                )
                refresh_required = False
                if params.activate:
                    env = service.bind_workspace_env(user_id, workspace_id, env.env_id)
                    refresh_required = True
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "workspace_id": workspace_id,
                        "env": env.model_dump(mode="json"),
                        "refresh_required": refresh_required,
                        "command_result": (
                            command_result.model_dump(mode="json")
                            if command_result is not None
                            else None
                        ),
                    }
                )

            if params.action == "register_python":
                if not params.python_executable:
                    return _error_result("register_python 需要提供 python_executable。")
                env = service.register_python_env(
                    user_id,
                    workspace_id,
                    env_id=params.env_id,
                    display_name=params.display_name,
                    python_executable=params.python_executable,
                    source_kernel_name=params.source_kernel_name,
                )
                refresh_required = False
                if params.activate:
                    env = service.bind_workspace_env(user_id, workspace_id, env.env_id)
                    refresh_required = True
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "workspace_id": workspace_id,
                        "env": env.model_dump(mode="json"),
                        "refresh_required": refresh_required,
                    }
                )

            if params.action == "install_packages":
                if not params.packages:
                    return _error_result("install_packages 需要提供 packages。")
                env, command_result = service.install_workspace_packages(
                    user_id,
                    workspace_id,
                    env_id=params.env_id or DEFAULT_UV_ENV_ID,
                    packages=params.packages,
                    sync=params.sync,
                )
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "workspace_id": workspace_id,
                        "env": env.model_dump(mode="json"),
                        "command_result": command_result.model_dump(mode="json"),
                    }
                )

            if params.action == "bind":
                if not params.env_id:
                    return _error_result("bind 需要提供 env_id。")
                env = service.bind_workspace_env(user_id, workspace_id, params.env_id)
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "workspace_id": workspace_id,
                        "env": env.model_dump(mode="json"),
                        "refresh_required": True,
                    }
                )

            if params.action == "inspect":
                if not params.env_id:
                    return _error_result("inspect 需要提供 env_id。")
                env = service.inspect_env(user_id, workspace_id, params.env_id)
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "workspace_id": workspace_id,
                        "env": env.model_dump(mode="json"),
                    }
                )

            if params.action == "unregister":
                if not params.env_id:
                    return _error_result("unregister 需要提供 env_id。")
                env = service.unregister_workspace_env(user_id, workspace_id, params.env_id)
                return _json_result(
                    {
                        "status": "success",
                        "action": params.action,
                        "workspace_id": workspace_id,
                        "env": env.model_dump(mode="json"),
                        "refresh_required": True,
                    }
                )

            return _error_result(f"未知运行环境操作: {params.action}")
        except FileNotFoundError as exc:
            return _error_result(str(exc))
        except ValueError as exc:
            return _error_result(str(exc))
        except RuntimeError as exc:
            return _error_result(str(exc))
        except Exception as exc:
            logger.exception("RuntimeEnvironment tool failed")
            return _error_result(f"运行环境工具执行失败: {exc}")
